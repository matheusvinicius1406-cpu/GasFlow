/**
 * API Key authentication middleware.
 *
 * Uses MARCOS_GAS_API_KEY from environment. When the env var is not set,
 * authentication is DISABLED (for local development convenience).
 *
 * All sensitive endpoints (campaign start/pause/cancel, customer updates,
 * opt-in/out, list modifications, WhatsApp logout) require auth.
 * Public endpoints (health, status) remain open.
 */

import type { Request, Response, NextFunction } from 'express';

const API_KEY = process.env.MARCOS_GAS_API_KEY;

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
  if (token !== API_KEY) {
    res.status(401).json({ error: 'Token de autenticação inválido.' });
    return;
  }

  next();
}

/** Returns whether API key auth is active. */
export function isAuthEnabled(): boolean {
  return !!API_KEY;
}
