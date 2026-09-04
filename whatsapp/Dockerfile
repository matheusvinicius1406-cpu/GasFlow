FROM node:24-slim

# Node >= 24: src/db.ts usa node:sqlite (nativo só a partir do Node 22.5+,
# estável no 24). Node 20 quebra com ERR_UNKNOWN_BUILTIN_MODULE.

# Instala Chromium, curl (healthcheck) e dependências do Puppeteer
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    curl \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgdk-pixbuf2.0-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Configura o Chromium como navegador do Puppeteer
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV WHATSAPP_EXECUTABLE_PATH=/usr/bin/chromium

WORKDIR /app

# Instala dependências
COPY package.json package-lock.json ./
RUN npm ci

# Copia o código
COPY . .

# Compila TypeScript -> dist (dist/ é gitignored, então o build é
# obrigatório na imagem; sem isso `node dist/server.js` falharia)
RUN npm run build

# Cria diretórios de dados
RUN mkdir -p data wwebjs_auth

EXPOSE 3000

CMD ["node", "dist/server.js"]
