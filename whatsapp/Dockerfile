FROM node:24-slim

# Node >= 24: src/db.ts usa node:sqlite (nativo só a partir do Node 22.5+,
# estável no 24). Node 20 quebra com ERR_UNKNOWN_BUILTIN_MODULE.
#
# Motor padrão: Baileys (WebSocket puro) — sem Chromium/Puppeteer.
# Rollback para wwebjs: WA_ENGINE=wwebjs (mantido como dependência) + imagem
# com Chromium (git revert do Dockerfile ou build arg BUILD_WWEBJS=1).

ARG BUILD_WWEBJS=0

# curl é necessário ao healthcheck do compose.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dependências do Chromium apenas no build de rollback (BUILD_WWEBJS=1).
RUN if [ "$BUILD_WWEBJS" = "1" ]; then \
      apt-get update && apt-get install -y --no-install-recommends \
      chromium fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 \
      libcups2 libdbus-1-3 libgdk-pixbuf2.0-0 libnspr4 libnss3 \
      libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 xdg-utils \
      && rm -rf /var/lib/apt/lists/*; \
    fi

ENV PUPPETEER_SKIP_DOWNLOAD=true
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true

WORKDIR /app

# Instala dependências
COPY package.json package-lock.json ./
RUN npm ci

# Copia o código
COPY . .

# Compila TypeScript -> dist (dist/ é gitignored, então o build é
# obrigatório na imagem; sem isso `node dist/server.js` falharia)
RUN npm run build

# Cria diretórios de dados (sessão Baileys + SQLite)
RUN mkdir -p data baileys_auth wwebjs_auth

EXPOSE 3000

CMD ["node", "dist/server.js"]
