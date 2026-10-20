import { Module } from '@nestjs/common';
import { BookmakerController } from './bookmaker.controller';
import { CircuitBreakerService } from '../../common/circuit-breaker.service';

@Module({
  controllers: [BookmakerController],
  providers: [CircuitBreakerService],
})
export class BookmakerModule {}
