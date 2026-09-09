/**
 * API Key authentication middleware.
 *
 * Uses MARCOS_GAS_API_KEY from environment. When the env var is not set,
 * authentication is DISABLED (for local development convenience) — mas em
 * produção (ENVIRONMENT=production) a ausência da chave DERRUBA o boot:
 * sem auth, o QR code e os dados de clientes ficam expostos na rede.
 *
 * All sensitive endpoints (campaign start/pause/cancel, customer updates,
 * opt-in/out, list modifications, WhatsApp logout) require auth.
 * Public endpoints (health, ready) remain open.
 */

import { timingSafeEqual } from 'node:crypto';
import type { Request, Response, NextFunction } from 'express';

const API_KEY = process.env.MARCOS_GAS_API_KEY;

/** Falha rápido se produção subir sem chave (QR/contatos expostos = sequestro de sessão). */
if (process.env.ENVIRONMENT === 'production' && !API_KEY) {
  console.error('❌ MARCOS_GAS_API_KEY é obrigatória em produção (ENVIRONMENT=production). Abortando boot.');
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
 * If MARCOS_GAS_API_KEY is not set, authentication is bypassed (dev mode).
 */
export function requireAuth(req: Request, res: Response, next: NextFunction): void {
  // If no API key configured, allow all (development mode)
  if (!API_KEY) {
    next();
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
