FROM node:26-slim

# Agente de integração: processo Node puro (sem Chromium, sem bindings
# nativos). Imagem slim basta; curl é necessário ao healthcheck do compose.
#
# Node 26 (e não 24): paridade com o serviço whatsapp. O histórico da
# escolha pelo npm embutido (tar/brace-expansion/ip-address vendorizados)
# ficou obsoleto: em produção o npm é REMOVIDO da imagem (ver RUN final),
# então CVEs do CLI embutido não são mais superfície de scan.
# `apt-get upgrade`: mantém a base Debian patcheada para o scan do Trivy
# (exit-code 1 em CRITICAL/HIGH) — mesma regra do backend/whatsapp.
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get upgrade -y -o Dpkg::Options::="--force-confold" \
    && apt-get install -y --no-install-recommends curl \
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

# Produção sem npm e sem devDeps — mesma regra do serviço whatsapp:
# o npm vendorizado do base image (brace-expansion 5.0.9, undici 6.28.0)
# tem CVEs que só a Docker Hub corrige, e o runtime só executa
# `node dist/index.js`.
RUN npm prune --omit=dev \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx

ENV NODE_ENV=production

# Poll loop: GASFLOW_API_URL, GASFLOW_SERVICE_TOKEN e
# AGENT_POLL_INTERVAL_SEC vêm do ambiente (compose/.env).
CMD ["node", "dist/index.js"]
