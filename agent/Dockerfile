FROM node:24-slim

# Agente de integração: processo Node puro (sem Chromium, sem bindings
# nativos). Imagem slim basta; curl é necessário ao healthcheck do compose.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala dependências
COPY package.json package-lock.json ./
RUN npm ci

# Copia o código
COPY . .

# Compila TypeScript -> dist (dist/ é gitignored, então o build é
# obrigatório na imagem; sem isso `node dist/index.js` falharia)
RUN npm run build

ENV NODE_ENV=production

# Poll loop: GASFLOW_API_URL, GASFLOW_SERVICE_TOKEN e
# AGENT_POLL_INTERVAL_SEC vêm do ambiente (compose/.env).
CMD ["node", "dist/index.js"]
