FROM node:26-slim

# Agente de integração: processo Node puro (sem Chromium, sem bindings
# nativos). Imagem slim basta; curl é necessário ao healthcheck do compose.
#
# Node 26 (e não 24) por dois motivos: paridade com o serviço whatsapp e,
# principalmente, o npm embutido. O `node:24-slim` traz npm 11.19.0, cujas
# dependências vendorizadas aparecem no scan do Trivy sem correção possível
# pelo projeto — tar 7.5.19 (CVE-2026-73566), brace-expansion 5.0.7
# (CVE-2026-14257/69152) e ip-address 10.2.0 (CVE-2026-69192). O
# `node:26-slim` traz npm 11.19.1 já com tar 7.5.22, brace-expansion 5.0.9
# e ip-address 10.5.0.
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

ENV NODE_ENV=production

# Poll loop: GASFLOW_API_URL, GASFLOW_SERVICE_TOKEN e
# AGENT_POLL_INTERVAL_SEC vêm do ambiente (compose/.env).
CMD ["node", "dist/index.js"]
