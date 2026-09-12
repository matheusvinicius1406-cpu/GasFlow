/**
 * afterPack (electron-builder) — restaura node_modules de produção dos
 * módulos Node embutidos (agent, whatsapp) dentro do pacote.
 *
 * O electron-builder 26 ignora pastas node_modules nos filtros de
 * extraResources, mas os módulos rodam como subprocessos Node a partir
 * de <resources>/<módulo>/ e precisam das deps de runtime no lugar.
 */
const { execSync } = require('child_process');
const path = require('path');

const MODULES = ['agent', 'whatsapp'];

module.exports = async function afterPack(context) {
  const resourcesRoot = context.appOutDir; // .../win-unpacked
  for (const mod of MODULES) {
    const dest = path.join(resourcesRoot, 'resources', mod);
    const hasPkg = require('fs').existsSync(path.join(dest, 'package.json'));
    if (!hasPkg) {
      throw new Error(`afterPack: ${mod} não encontrado em ${dest}`);
    }
    process.stdout.write(`afterPack: instalando deps de produção de ${mod}…\n`);
    // --omit=dev instala só as deps de runtime (package-lock respeitado);
    // --ignore-scripts evita postinstalls (ex.: download do Chromium).
    execSync('npm install --omit=dev --ignore-scripts --no-audit --no-fund', {
      cwd: dest,
      stdio: 'inherit',
    });
  }
};
