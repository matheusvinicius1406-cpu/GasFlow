/**
 * Gaussian random helpers — humanized pacing.
 *
 * Box-Muller transform. Used to replace uniform send delays with a
 * bell-curve distribution (média 3s, desvio 1s por padrão).
 */

/** Sample from a normal distribution with the given mean and standard deviation. */
export function gaussianRandom(mean: number, stdev: number): number {
  if (stdev <= 0) return mean;
  const u = 1 - Math.random(); // (0, 1] — evita log(0)
  const v = Math.random();
  const z = Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
  return z * stdev + mean;
}

/** Gaussian delay in ms, clamped to a floor (default 500ms). */
export function gaussianDelayMs(meanMs: number, stdevMs: number, floorMs = 500): number {
  return Math.max(floorMs, Math.round(gaussianRandom(meanMs, stdevMs)));
}
