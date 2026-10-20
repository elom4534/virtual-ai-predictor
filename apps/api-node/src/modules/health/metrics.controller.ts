import { Controller, Get, Res } from '@nestjs/common';
import { Response } from 'express';
import { MetricsRegistry } from '../../common/metrics.service';

/**
 * Endpoint Prometheus (spec §9 : observabilité).
 * GET /api/v1/metrics → exposition texte format Prometheus.
 */
@Controller()
export class MetricsController {
  constructor(private readonly registry: MetricsRegistry) {}

  @Get('metrics')
  metrics(@Res() res: Response) {
    res.setHeader('Content-Type', 'text/plain; version=0.0.4; charset=utf-8');
    return res.send(this.registry.render());
  }
}
