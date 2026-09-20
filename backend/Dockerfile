FROM python:3.14-slim

# Security: non-root user
RUN groupadd -r gasflow && useradd -r -g gasflow -d /app -s /sbin/nologin gasflow

WORKDIR /app

# Install system dependencies
#
# `apt-get upgrade` é obrigatório aqui: `python:3.14-slim` é um snapshot que
# atrasa em relação ao point release do Debian (trixie), e o job Trivy roda
# com `exit-code: 1` em CRITICAL/HIGH — sem atualizar, a imagem reprova no
# scan por pacotes da base (perl-base, gzip, libsqlite3-0, libpcre2, ...)
# mesmo quando não há CVE nenhum no código. `--force-confold` evita prompt
# interativo de conffile em build não interativo.
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get upgrade -y -o Dpkg::Options::="--force-confold" \
    && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# pip fora da imagem de runtime.
#
# O container sobe `alembic` + `uvicorn` (entrypoints diretos, que não usam
# pip). O pip carrega dependências vendorizadas que o Trivy reporta como HIGH
# sem caminho de correção: `pip/_vendor/vendor.txt` declara
# `msgpack==1.1.2` (GHSA-6v7p-g79w-8964) e `setuptools==70.3.0`
# (CVE-2025-47273), versões fixadas dentro do próprio pip — não há como
# atualizá-las sem trocar o pip, e o pip 26.2.1 (mais novo) ainda as traz.
# Remover o pip tira o código vulnerável do que vai para produção e ainda
# enxuga a imagem. O `ensurepip` sai junto: ele guarda os mesmos wheels
# empacotados (setuptools 70.3.0).
RUN rm -rf \
        /usr/local/lib/python3.14/site-packages/pip \
        /usr/local/lib/python3.14/site-packages/pip-*.dist-info \
        /usr/local/lib/python3.14/ensurepip \
        /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.14 \
        /root/.cache

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/backups /app/logs && \
    chown -R gasflow:gasflow /app

# Switch to non-root user
USER gasflow

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
