import { Module } from '@nestjs/common';
import { HealthController } from './health.controller';
import { MetricsController } from './metrics.controller';
import { MetricsRegistry } from '../../common/metrics.service';

@Module({
  controllers: [HealthController, MetricsController],
  providers: [MetricsRegistry],
  exports: [MetricsRegistry],
})
export class HealthModule {}
