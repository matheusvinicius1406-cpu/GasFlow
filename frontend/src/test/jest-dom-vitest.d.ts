// Compatibilidade de tipos: `@testing-library/jest-dom` 7.x declara
// `interface Assertion<T = any>` em `declare module 'vitest'`, mas o vitest 5
// declara `Assertion<R, T>` (retorno + valor). Como a mesclagem de interfaces
// exige parâmetros de tipo idênticos, a declaração do jest-dom deixa de valer e
// os matchers (`toBeInTheDocument`, `toHaveFocus`, ...) somem do `expect`.
//
// Este shim redeclara a augmentation com a assinatura do vitest 5, mantendo os
// tipos do jest-dom. Remover quando o jest-dom publicar suporte ao vitest 5.
/* eslint-disable @typescript-eslint/no-empty-object-type, @typescript-eslint/no-unused-vars --
   o shim precisa espelhar exatamente a assinatura de `Assertion` do vitest 5. */
import type { TestingLibraryMatchers } from '@testing-library/jest-dom/matchers'

declare module 'vitest' {
  interface Assertion<R extends void | Promise<void> = void, T = unknown>
    extends TestingLibraryMatchers<unknown, R> {}

  interface AsymmetricMatchersContaining
    extends TestingLibraryMatchers<unknown, unknown> {}
}
