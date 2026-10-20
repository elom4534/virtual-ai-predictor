import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { SwaggerModule, DocumentBuilder } from '@nestjs/swagger';
import { AppModule } from './app.module';
import helmet from 'helmet';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.use(helmet());
  app.enableCors({ origin: true, credentials: true });
  app.setGlobalPrefix('api/v1');
  app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true, forbidNonWhitelisted: false }));

  const config = new DocumentBuilder()
    .setTitle('Pred API (NestJS BFF)')
    .setDescription('BFF: auth, country gate, coupon orchestration, bookmaker proxy — fail-closed, sans cotes exposées')
    .setVersion('0.3.0')
    .addBearerAuth()
    .build();
  const document = SwaggerModule.createDocument(app, config);
  SwaggerModule.setup('docs', app, document);

  // ⚠️ Alwaysdata injecte PORT=8100 et IP=fd00::... dans l'environnement du site.
  //    Le service NestJS est INTERNE (relayé par l'edge FastAPI sur le port
  //    public) : il ne doit donc JAMAIS prendre le port public, sinon
  //    « address already in use » et le site tombe.
  //    → On n'utilise plus PORT/IP de la plateforme, mais des variables
  //      dédiées (NODE_API_PORT / NODE_API_HOST), overridables.
  const port = parseInt(process.env.NODE_API_PORT || '3000', 10);
  const host = process.env.NODE_API_HOST || '127.0.0.1';
  await app.listen(port, host);
  console.log(`NestJS API listening on ${host}:${port} — docs at /docs`);
}
bootstrap();
