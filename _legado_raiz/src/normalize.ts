/**
 * Normalizes a phone number to a digits-only string (E.164 without the '+'),
 * or null when no usable number can be extracted.
 *
 * Conservative approach: strip everything that is not a digit and drop
 * leading zeros. No country code is invented — WhatsApp's `number` field
 * already comes with the country code.
 */
export function normalizePhone(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const digits = raw.replace(/\D/g, '');
  const trimmed = digits.replace(/^0+/, '');
  return trimmed.length >= 8 ? trimmed : null;
}

/**
 * Extracts the "user" part of a JID (before '@').
 * e.g. "5511999999999@c.us" -> "5511999999999"
 *      "123abc@lid"         -> "123abc"
 */
export function jidUser(jid: string): string {
  const at = jid.indexOf('@');
  return at === -1 ? jid : jid.slice(0, at);
}

export function isGroupJid(jid: string): boolean {
  return jid.endsWith('@g.us');
}
