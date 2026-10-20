import { CanActivate, ExecutionContext, Injectable, ForbiddenException } from '@nestjs/common';

/**
 * Country Policy Gate — fail-closed (spec §0.14 et §14).
 *
 * Source de vérité du pays : le JWT de l'utilisateur (req.user.country_code).
 * Le header X-Country-Code est contrôlé par le client → Spoofable.
 * Il n'est donc accepté QUE si ALLOW_COUNTRY_HEADER_FALLBACK=true
 * (mode démo explicite, à retirer dès que l'authentification est en place).
 *
 * Règles (toutes fail-closed) :
 *  - pays absent          → BLOQUÉ
 *  - pays blacklisté      → BLOQUÉ
 *  - whitelist non config → BLOQUÉ (on ne devine pas la liste des pays autorisés)
 *  - pays hors whitelist  → BLOQUÉ
 */
@Injectable()
export class CountryPolicyGuard implements CanActivate {
  private allowed: Set<string>;
  private blocked: Set<string>;
  private trustHeader: boolean;

  constructor() {
    const allowedRaw = process.env.ALLOWED_COUNTRIES || '';
    const blockedRaw = process.env.BLOCKED_COUNTRIES || '';
    this.allowed = new Set(allowedRaw.split(',').map(s => s.trim().toUpperCase()).filter(Boolean));
    this.blocked = new Set(blockedRaw.split(',').map(s => s.trim().toUpperCase()).filter(Boolean));
    this.trustHeader = String(process.env.ALLOW_COUNTRY_HEADER_FALLBACK || '').toLowerCase() === 'true';
  }

  canActivate(context: ExecutionContext): boolean {
    const req = context.switchToHttp().getRequest();

    // 1. Source fiable : le pays porté par le JWT (req.user rempli par le guard JWT)
    const fromJwt = (req.user?.country_code || req.user?.country || '').toString().toUpperCase();

    // 2. Source non fiable : header client — uniquement en mode démo opt-in
    const fromHeader = this.trustHeader
      ? (req.headers['x-country-code'] || '').toString().toUpperCase()
      : '';

    const country = fromJwt || fromHeader;

    if (!country) {
      throw new ForbiddenException({
        error: 'COUNTRY_NOT_CONFIGURED',
        reason_code: 'COUNTRY_GATE_BLOCKED',
        details: this.trustHeader
          ? 'Missing X-Country-Code or user.country_code'
          : 'Missing user.country_code (JWT) — ALLOW_COUNTRY_HEADER_FALLBACK=false',
      });
    }

    if (this.blocked.has(country)) {
      throw new ForbiddenException({
        error: 'COUNTRY_BLOCKED',
        reason_code: 'COUNTRY_GATE_BLOCKED',
        country,
      });
    }

    // Whitelist non configurée → fail-closed : on ne devine pas les pays autorisés
    if (this.allowed.size === 0) {
      throw new ForbiddenException({
        error: 'COUNTRY_NOT_CONFIGURED',
        reason_code: 'COUNTRY_GATE_BLOCKED',
        country,
        details: 'ALLOWED_COUNTRIES non configuré — blocage par défaut (fail-closed)',
      });
    }

    if (!this.allowed.has(country)) {
      throw new ForbiddenException({
        error: 'COUNTRY_NOT_CONFIGURED',
        reason_code: 'COUNTRY_GATE_BLOCKED',
        country,
        details: `Country ${country} not in ALLOWED_COUNTRIES (fail-closed)`,
      });
    }

    return true;
  }
}
