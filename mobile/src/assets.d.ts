/**
 * Declarações de módulo para assets que o Metro resolve em runtime.
 * Sem isso o `tsc --noEmit` reprova o `require("*.png")` das telas.
 */

declare module "*.png" {
  const source: number;
  export default source;
}

declare module "*.jpg" {
  const source: number;
  export default source;
}
