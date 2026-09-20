FROM node:26-slim AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine

# Security: o job Trivy roda com `exit-code: 1` em CRITICAL/HIGH e as imagens
# oficiais atrasam em relação ao point release da Alpine — sem atualizar, o
# scan reprova por pacote da base (libcrypto, zlib, ...) mesmo sem CVE no
# código. O builder (node, descartado) não precisa disso.
RUN apk upgrade --no-cache

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
