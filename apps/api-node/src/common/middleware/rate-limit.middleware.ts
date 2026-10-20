import { Injectable, NestMiddleware } from '@nestjs/common';
import { Request, Response, NextFunction } from 'express';

// Simple in-memory rate limit (prod: Redis)
// 10 coupons/min/user, 100 req/min/IP
const buckets = new Map<string, {count:number, reset:number}>();

@Injectable()
export class RateLimitMiddleware implements NestMiddleware {
  use(req: Request, res: Response, next: NextFunction) {
    // Les endpoints de supervision ne sont jamais rate-limités :
    // un moniteur qui se fait bloquer fausse le diagnostic.
    const p = req.path || '';
    if (p.endsWith('/health') || p.endsWith('/metrics') || p.startsWith('/docs')) {
      return next();
    }
    const key = (req as any).user?.sub ? `user:${(req as any).user.sub}` : `ip:${req.ip}`;
    const path = req.path;
    const limit = path.includes('coupon/create') ? 10 : 100;
    const windowMs = 60*1000;
    const now = Date.now();
    let b = buckets.get(key);
    if (!b || now > b.reset) {
      b = {count:1, reset: now+windowMs};
      buckets.set(key, b);
    } else {
      b.count++;
    }
    if (b.count > limit) {
      return res.status(429).json({ error: 'RATE_LIMITED', reason_code:'RATE_LIMITED', details:`${limit}/min` });
    }
    res.setHeader('X-RateLimit-Remaining', String(limit - b.count));
    next();
  }
}
