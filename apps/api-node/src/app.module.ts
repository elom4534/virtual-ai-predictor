import { Module, MiddlewareConsumer, NestModule } from '@nestjs/common';
import { APP_FILTER, APP_INTERCEPTOR } from '@nestjs/core';
import { EventsModule } from './modules/events/events.module';
import { ScanModule } from './modules/scan/scan.module';
import { PicksModule } from './modules/picks/picks.module';
import { CouponsModule } from './modules/coupons/coupons.module';
import { BookmakerModule } from './modules/bookmaker/bookmaker.module';
import { AuthModule } from './modules/auth/auth.module';
import { PreferencesModule } from './modules/preferences/preferences.module';
import { HistoryModule } from './modules/history/history.module';
import { HealthModule } from './modules/health/health.module';

import { MegaPariModule } from './modules/bookmaker/megapari.module';
import { SoccerSyncModule } from './workers/soccer-sync.module';

import { FailClosedFilter } from './common/filters/fail-closed.filter';
import { AuditInterceptor } from './common/interceptors/audit.interceptor';
import { MetricsInterceptor } from './common/interceptors/metrics.interceptor';
import { MetricsRegistry } from './common/metrics.service';
import { RateLimitMiddleware } from './common/middleware/rate-limit.middleware';

/**
 * Les garde-fous existaient dans common/ mais n'étaient montés sur AUCUNE route
 * (constat d'audit, spec §0.14 et §14 : obligations bloquantes).
 * Ils sont désormais enregistrés globalement :
 *  - FailClosedFilter  → aucune fuite de stack trace en production
 *  - AuditInterceptor  → audit log sur TOUTES les routes (user_id, provider,
 *                        model_version, as_of, reason_codes)
 *  - MetricsInterceptor→ métriques Prometheus (/api/v1/metrics)
 *  - RateLimitMiddleware→ rate limiting global (spec §14)
 */
@Module({
  imports: [
    AuthModule, EventsModule, ScanModule, PicksModule, CouponsModule,
    BookmakerModule, MegaPariModule, SoccerSyncModule, PreferencesModule,
    HistoryModule, HealthModule,
  ],
  controllers: [],
  providers: [
    { provide: APP_FILTER, useClass: FailClosedFilter },
    { provide: APP_INTERCEPTOR, useClass: AuditInterceptor },
    {
      provide: APP_INTERCEPTOR,
      useFactory: (registry: MetricsRegistry) => new MetricsInterceptor(registry),
      inject: [MetricsRegistry],
    },
    RateLimitMiddleware,
  ],
})
export class AppModule implements NestModule {
  configure(consumer: MiddlewareConsumer) {
    consumer.apply(RateLimitMiddleware).forRoutes('*');
  }
}
