import { Injectable, HttpException, HttpStatus } from '@nestjs/common';

/**
 * Circuit breaker minimal (spec §14 : "Rate limiting + timeouts + circuit breaker").
 *
 * États : closed → open → half_open → closed
 * - closed   : tout passe, on compte les échecs
 * - open     : tout est rejeté immédiatement (fail-closed, pas d'appel sortant)
 * - half_open: une requête de test est autorisée ; succès → closed, échec → open
 */
@Injectable()
export class CircuitBreakerService {
  private states = new Map<string, { state: 'closed' | 'open' | 'half_open'; failures: number; openedAt: number }>();

  // Pas de constructeur : Nest tenterait d'injecter des primitifs (Number)
  // et échouerait au démarrage. Les seuils restent configurables par env.
  private readonly failureThreshold = parseInt(process.env.CIRCUIT_FAILURE_THRESHOLD || '5', 10);
  private readonly cooldownMs = parseInt(process.env.CIRCUIT_COOLDOWN_MS || '30000', 10);

  private get(key: string) {
    let s = this.states.get(key);
    if (!s) {
      s = { state: 'closed', failures: 0, openedAt: 0 };
      this.states.set(key, s);
    }
    return s;
  }

  getState(key: string): string {
    const s = this.get(key);
    if (s.state === 'open' && Date.now() - s.openedAt > this.cooldownMs) {
      s.state = 'half_open';
    }
    return s.state;
  }

  async execute<T>(key: string, fn: () => Promise<T>): Promise<T> {
    const s = this.get(key);
    if (s.state === 'open') {
      if (Date.now() - s.openedAt > this.cooldownMs) {
        s.state = 'half_open';
      } else {
        throw new HttpException(
          {
            error: 'CIRCUIT_OPEN',
            reason_code: 'BOOKMAKER_CIRCUIT_OPEN',
            details: `Circuit ouvert pour ${key} — appel bookmaker non effectué (fail-closed)`,
          },
          HttpStatus.SERVICE_UNAVAILABLE,
        );
      }
    }

    try {
      const result = await fn();
      s.failures = 0;
      s.state = 'closed';
      return result;
    } catch (err) {
      s.failures += 1;
      if (s.state === 'half_open' || s.failures >= this.failureThreshold) {
        s.state = 'open';
        s.openedAt = Date.now();
      }
      throw err;
    }
  }
}
