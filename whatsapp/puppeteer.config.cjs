/**
 * Puppeteer (dependência do whatsapp-web.js) baixa o Chrome no postinstall
 * de storage.googleapis.com — falha (403) em CI/redes com allowlist de domínios.
 *
 * skipDownload: o Chrome NÃO é necessário no default — o motor padrão é
 * Baileys (WebSocket puro, sem Chromium). O rollback para wwebjs
 * (WA_ENGINE=wwebjs) usa a imagem Docker com Chromium instalado
 * (BUILD_WWEBJS=1) ou define PUPPETEER_EXECUTABLE_PATH.
 */
module.exports = {
  skipDownload: true,
};
