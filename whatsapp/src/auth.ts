/**
 * API Key authentication middleware.
 *
 * Uses MARCOS_GAS_API_KEY from environment. Authentication can only be
 * bypassed when ALLOW_INSECURE_AUTH=true outside production.
 *
 * All sensitive endpoints (campaign start/pause/cancel, customer updates,
 * opt-in/out, list modifications, WhatsApp logout) require auth.
 * Public endpoints (health, ready) remain open.
 */

import { timingSafeEqual } from 'node:crypto';
import type { Request, Response, NextFunction } from 'express';
import { logger } from './log';

const API_KEY = process.env.MARCOS_GAS_API_KEY;
const ALLOW_INSECURE_AUTH = process.env.ALLOW_INSECURE_AUTH === 'true'
  && process.env.ENVIRONMENT !== 'production';

/** Falha rápido se o serviço subir sem proteção explícita. */
if (!API_KEY && !ALLOW_INSECURE_AUTH) {
  logger.error('auth.missing_api_key');
  process.exit(1);
}

/** Comparação em tempo constante (evita timing attack na API key). */
function safeEqual(a: string, b: string): boolean {
  const bufA = Buffer.from(a, 'utf-8');
  const bufB = Buffer.from(b, 'utf-8');
  if (bufA.length !== bufB.length) {
    // Compara mesmo assim com dummies para manter o tempo estável.
    timingSafeEqual(bufA, bufA);
    return false;
  }
  return timingSafeEqual(bufA, bufB);
}

/**
 * Express middleware that validates Bearer token against MARCOS_GAS_API_KEY.
 * A bypass is allowed only when ALLOW_INSECURE_AUTH=true outside production.
 */
export function requireAuth(req: Request, res: Response, next: NextFunction): void {
  if (!API_KEY && ALLOW_INSECURE_AUTH) {
    next();
    return;
  }

  if (!API_KEY) {
    res.status(503).json({ error: 'Autenticação do serviço não configurada.' });
    return;
  }

  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    res.status(401).json({ error: 'Token de autenticação ausente. Use: Authorization: Bearer <API_KEY>' });
    return;
  }

  const token = authHeader.slice(7); // Remove "Bearer "
  if (!safeEqual(token, API_KEY)) {
    res.status(401).json({ error: 'Token de autenticação inválido.' });
    return;
  }

  next();
}

/** Returns whether API key auth is active. */
export function isAuthEnabled(): boolean {
  return !!API_KEY;
}
