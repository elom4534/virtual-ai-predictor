/**
 * Base connector BetB2B — utilisé à l'identique pour MegaPari et 1xBet
 * Seuls client_id / client_secret / ref changent.
 * Gateway unique: https://cpservm.com/gateway/marketing
 * Token: POST https://cpservm.com/gateway/token (OAuth2 client_credentials, form-urlencoded, --data-urlencode)
 */
import axios from 'axios';
import { createClient } from 'redis';

const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
const GATEWAY_BASE = (process.env.BOOKMAKER_API_BASE || 'https://cpservm.com/gateway/marketing').replace(/\/$/, '');
const TOKEN_URL = process.env.BOOKMAKER_TOKEN_URL || 'https://cpservm.com/gateway/token';

let redis: any = null;
let redisUnavailable = false;

/**
 * Connexion Redis partagée (cache du token OAuth2).
 *
 * ⚠️ Deux pièges corrigés ici (constatés en conditions réelles) :
 *  1. le client ne doit PAS être mémorisé si la connexion a échoué — sinon
 *     l'appel suivant renvoie un client mort et le cache token devient
 *     inopérant ;
 *  2. un client Redis sans écouteur 'error' fait crasher le process au
 *     moment de l'échec (événement 'error' non géré sur un EventEmitter).
 */
async function getRedis() {
  if (redis) return redis;
  if (redisUnavailable) return null;
  try {
    const client = createClient({
      url: REDIS_URL,
      socket: {
        // Reconnexions limitées : sans Redis le service doit rester
        // opérationnel (le cache du token OAuth2 est un accélérateur,
        // pas une dépendance dure) et ne pas saturer les logs.
        reconnectStrategy: (retries: number) =>
          retries > 3 ? false : Math.min(retries * 200, 2000),
      },
    });
    let logged = false;
    client.on('error', (err: any) => {
      // On log une seule fois mais on ne laisse pas remonter : sans
      // écouteur, l'événement 'error' non géré tue le process Node.
      if (logged) return;
      logged = true;
      console.warn(`[bookmaker] Redis indisponible: ${err?.message || 'erreur inconnue'}`);
    });
    await client.connect();
    redis = client;
    return redis;
  } catch (e: any) {
    redisUnavailable = true;
    console.warn(`[bookmaker] Connexion Redis impossible: ${e?.message} — cache token désactivé`);
    return null;
  }
}

export interface ProviderConfig {
  name: '1xBet' | 'Méga Pari';
  client_id: string;
  client_secret: string;
  ref: number;
}

/**
 * Le secret fourni par le bookmaker arrive avec les entités HTML (`&amp;`).
 * Envoyé tel quel → 400 {"error":"invalid_client"} (vérifié en ligne le 20/10/2026).
 * On décode avant l'envoi, et on conserve la valeur brute pour le cache Redis.
 */
export function decodeSecret(raw: string): string {
  return (raw || '')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

export function loadConfig(name: '1xBet' | 'Méga Pari'): ProviderConfig {
  if (name === 'Méga Pari') {
    return {
      name: 'Méga Pari',
      client_id: process.env.MEGAPARI_CLIENT_ID || process.env.BOOKMAKER_CLIENT_ID || 'partners-c2b75a07c454fcd96f0453a0f79e1ead',
      client_secret: process.env.MEGAPARI_CLIENT_SECRET || process.env.BOOKMAKER_CLIENT_SECRET || '',
      ref: parseInt(process.env.MEGAPARI_REF || '192', 10),
    };
  }
  return {
    name: '1xBet',
    client_id: process.env.XBET_CLIENT_ID || 'partners-592d3a39b56e7ca211a846129d6fc5e3',
    client_secret: process.env.XBET_CLIENT_SECRET || '',
    ref: parseInt(process.env.XBET_REF || '1', 10),
  };
}

export class BaseBetB2BConnector {
  constructor(public provider: '1xBet' | 'Méga Pari') {}

  get cfg() { return loadConfig(this.provider); }
  get base() { return GATEWAY_BASE; }

  /** OAuth2 client_credentials — IDENTIQUE pour les 2 providers */
  async getAccessToken(): Promise<string> {
    const c = this.cfg;
    if (!c.client_id || !c.client_secret) throw new Error(`[${c.name}] client_id/client_secret manquants`);
    const cacheKey = `bookmaker:token:${c.name}:${c.ref}:${c.client_id.slice(-6)}`;
    const r = await getRedis();
    if (r) { const cached = await r.get(cacheKey).catch(()=>null); if (cached) return cached; }

    const { data } = await axios.post(TOKEN_URL,
      new URLSearchParams({ client_id: c.client_id, client_secret: decodeSecret(c.client_secret) }).toString(),
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, timeout: 8000 }
    );
    const token = data.access_token;
    const exp = data.expires_in || 3600;
    if (!token) throw new Error(`[${c.name}] pas de token`);
    if (r) await r.setEx(cacheKey, token, { EX: Math.max(60, exp - 60) });
    return token;
  }

  /** Helper GET avec Bearer — headers identiques */
  private async get(path: string, params: Record<string, any>, token: string) {
    const url = `${this.base}${path}`;
    return axios.get(url, { params, headers: { Authorization: `Bearer ${token}` }, timeout: 10000 });
  }

  // ---- LoadList (prematch) — MÊME signatures, MÊME ordre params ----
  async getGameIds(lastUpdate = 0) {
    const c = this.cfg;
    const token = await this.getAccessToken();
    const { data } = await this.get('/datafeed/loadlist/prematch/api/v1/getGameIds', { ref: c.ref, lastUpdate }, token);
    return data; // {count, lastIndex, items}
  }

  async getDetailsGame(gameId: number, gr = 0, cnt = 0) {
    const c = this.cfg;
    const token = await this.getAccessToken();
    // ORDRE STRICT ref, gr, cnt, gameId, languages, languageForLink
    const params = { ref: c.ref, gr, cnt, gameId, languages: 'en', languageForLink: 'en' };
    const { data } = await this.get('/datafeed/loadlist/prematch/api/v1/getDetailsGame', params, token);
    return data;
  }

  async getMarketsGame(gameId: number, cnt = 0) {
    const c = this.cfg;
    const token = await this.getAccessToken();
    // ORDRE STRICT cnt, ref, gameId
    const { data } = await this.get('/datafeed/loadlist/prematch/api/v1/getMarketsGame', { cnt, ref: c.ref, gameId }, token);
    return data;
  }

  // ---- LoadTree (prematch) ----
  async sportList() {
    const c = this.cfg;
    const token = await this.getAccessToken();
    const { data } = await this.get('/datafeed/loadtree/prematch/api/v1/sportList', { ref: c.ref }, token);
    return data;
  }

  async tournaments(sportId: number) {
    const c = this.cfg;
    const token = await this.getAccessToken();
    const { data } = await this.get('/datafeed/loadtree/prematch/api/v1/tournaments', { ref: c.ref, sportId }, token);
    return data;
  }

  async sporteventIds(tournamentId: number) {
    const c = this.cfg;
    const token = await this.getAccessToken();
    const { data } = await this.get('/datafeed/loadtree/prematch/api/v1/sporteventIds', { ref: c.ref, tournamentId }, token);
    return data;
  }

  async sporteventDetail(sportEventId: number, withSubGames = true) {
    const c = this.cfg;
    const token = await this.getAccessToken();
    const params: any = { ref: c.ref, gr: 0, cnt: 0, sportEventId, withSubGames, schemeOfGettingOdds: 'GetAllOdds' };
    const { data } = await this.get('/datafeed/loadtree/prematch/api/v1/sporteventDetail', params, token);
    return data;
  }

  // ---- LoadSingle (fallback si LoadList 403) — ouvert aux deux providers ----
  /**
   * LoadSingle v2 — noms de paramètres conformes à la spec OpenAPI BetB2B
   * (ref, lng, sportIds, schemeOfGettingOddsOperations, count).
   *
   * ⚠️ `schemeOfGettingOddsOperations` est INDISPENSABLE pour obtenir les
   * cotes : sans lui, `oddsLocalization` est vide (vérifié en ligne le
   * 20/10/2026). Valeurs : GetAllOdds | GetMainOdds | Get1X2Odds | null.
   * Le gateway accepte aussi la variante capitalisée (Ref, Lng, …).
   */
  async loadSinglePreMatch(count = 5, sportIds?: string, schemeOfGettingOddsOperations = 'GetAllOdds') {
    const c = this.cfg;
    const token = await this.getAccessToken();
    const params: any = { ref: c.ref, count, lng: 'en', schemeOfGettingOddsOperations };
    if (sportIds) params.sportIds = sportIds;
    const { data } = await this.get('/datafeed/prematch/api/v2/sportevents', params, token);
    return data; // {count, items: [sportEvent... avec oddsLocalization]}
  }

  /** Wrapper unifié avec fallback LoadList → LoadSingle si 403 */
  async getGameIdsWithFallback(lastUpdate = 0) {
    try {
      return await this.getGameIds(lastUpdate);
    } catch (e: any) {
      if (e?.response?.status === 403) {
        console.warn(`[${this.cfg.name}] LoadList 403 → fallback LoadSingle (scopes manquants, voir manager)`);
        const single = await this.loadSinglePreMatch(100);
        // Normalise en même format {count, items: [sportEventId]}
        const items = (single.items || []).map((ev: any) => ev.sportEventId);
        return { count: items.length, lastIndex: Date.now(), items, fallback: 'LoadSingle' };
      }
      throw e;
    }
  }
}
