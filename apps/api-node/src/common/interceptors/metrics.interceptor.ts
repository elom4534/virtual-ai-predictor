import { Injectable, NestInterceptor, ExecutionContext, CallHandler } from '@nestjs/common';
import { Observable, tap } from 'rxjs';
import { MetricsRegistry } from '../metrics.service';

/**
 * Collecte les métriques HTTP (compteur + durée) pour l'endpoint /metrics.
 * Spec §9 : "Observabilité : logs structurés + métriques + alerting".
 */
@Injectable()
export class MetricsInterceptor implements NestInterceptor {
  constructor(private readonly registry: MetricsRegistry) {}

  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const http = context.switchToHttp();
    const req = http.getRequest();
    const res = http.getResponse();
    const start = Date.now();
    const route = req.route?.path || req.path || 'unknown';
    const labels = { method: req.method, route };

    return next.handle().pipe(
      tap({
        next: () => {
          this.registry.inc('http_requests_total', { ...labels, status: String(res.statusCode) });
          this.registry.observe('http_request_duration_ms', Date.now() - start, labels);
        },
        error: () => {
          this.registry.inc('http_requests_total', { ...labels, status: 'error' });
          this.registry.observe('http_request_duration_ms', Date.now() - start, labels);
        },
      }),
    );
  }
}
