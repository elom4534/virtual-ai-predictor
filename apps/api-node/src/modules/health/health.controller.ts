import { Controller, Get } from '@nestjs/common';
import axios from 'axios';
import { Pool } from 'pg';
import { createClient } from 'redis';

/**
 * Health check RÉEL (spec §9 : observabilité).
 * Avant, la route retournait un objet codé en dur (postgres/redis/ml: "up")
 * sans vérifier quoi que ce soit — ce qui masque les pannes en production.
 */
let pool: Pool | null = null;
function getPool(url: string): Pool {
  if (!pool) {
    pool = new Pool({ connectionString: url, connectionTimeoutMillis: 2000, max: 2 });
    pool.on('error', () => { /* fail-closed silencieux, la vérif suivante le montrera */ });
  }
  return pool;
}

async function checkPostgres(url: string): Promise<string> {
  try {
    await getPool(url).query('SELECT 1');
    return 'up';
  } catch {
    return 'down';
  }
}

async function checkRedis(url: string): Promise<string> {
  let client: any = null;
  try {
    client = createClient({ url, socket: { connectTimeout: 2000 } });
    client.on('error', () => { /* ignore */ });
    await client.connect();
    await client.ping();
    return 'up';
  } catch {
    return 'down';
  } finally {
    try { await client?.quit(); } catch { /* ignore */ }
  }
}

async function checkMl(url: string): Promise<string> {
  try {
    const res = await axios.get(`${url}/health`, {
      timeout: 2500,
      validateStatus: () => true,
      // Le service ML est local : on passe par l'IPv6 de la plateforme.
      // L'URL est déjà complète (ML_PYTHON_URL=http://[fd00::7:c7ec]:8100).
    });
    return res.status === 200 ? 'up' : 'down';
  } catch {
    return 'down';
  }
}

@Controller()
export class HealthController {
  @Get('health')
  async health() {
    const dbUrl = process.env.DATABASE_URL;
    const redisUrl = process.env.REDIS_URL;
    const mlUrl = process.env.ML_PYTHON_URL;

    const checks: Record<string, string> = {
      postgres: dbUrl ? 'down' : 'not_configured',
      redis: redisUrl ? 'down' : 'not_configured',
      ml: mlUrl ? 'down' : 'not_configured',
    };

    const [pg, redis, ml] = await Promise.all([
      dbUrl ? checkPostgres(dbUrl) : Promise.resolve('not_configured'),
      redisUrl ? checkRedis(redisUrl) : Promise.resolve('not_configured'),
      mlUrl ? checkMl(mlUrl) : Promise.resolve('not_configured'),
    ]);
    checks.postgres = pg;
    checks.redis = redis;
    checks.ml = ml;

    const down = Object.entries(checks).filter(([, v]) => v === 'down').map(([k]) => k);
    return {
      status: down.length ? 'degraded' : 'ok',
      service: 'pred-api-node',
      version: '0.3.0',
      checks,
      degraded: down,
      timestamp: new Date().toISOString(),
    };
  }
}
