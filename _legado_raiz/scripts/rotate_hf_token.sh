#!/usr/bin/env bash
#
# rotate_hf_token.sh — rotação segura do HF_TOKEN (Hugging Face)
#
#   [1/8] pré-checagens  (raiz do monorepo, git, .gitignore, HF_TOKEN, escrita)
#   [2/8] backup do GasFlow/.env (chmod 600)
#   [3/8] revogação manual do token antigo (painel HF — não há API estável)
#   [4/8] geração manual do token novo (fine-grained, escopo mínimo)
#   [5/8] validação HTTP do token novo ANTES de gravar
#   [6/8] gravação do novo valor no .env (sed portátil, sem expor o token)
#   [7/8] revalidação pós-gravação + varredura de segredos (gitleaks/grep)
#   [5]   relatório final + entrada em CHANGELOG-seguranca.md
#
# Uso:   bash scripts/rotate_hf_token.sh        (chmod +x opcional)
#
# Mexe APENAS na chave HF_TOKEN de GasFlow/.env. Nunca commita, nunca imprime
# token completo, nunca continua se a validação HTTP não retornar 200.
# Portável GNU/BSD (usa `sed -i.bak`). NUNCA habilite `set -x` (vaza token).

set -euo pipefail
IFS=$'\n\t'

# ── Constantes ──────────────────────────────────────────────────────────────
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/GasFlow/.env"
REL_ENV="GasFlow/.env"
HF_URL="${HF_URL:-https://huggingface.co}"   # override só para testes/stub
TS="$(date +%Y%m%d_%H%M%S)"

# ── Cores (apenas se stdout for TTY) ────────────────────────────────────────
if [ -t 1 ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; BOLD=''; RESET=''
fi

# ── Limpeza de segredos em QUALQUER saída (sucesso, erro, Ctrl-C) ───────────
NOVO_TOKEN=''
trap 'unset NOVO_TOKEN OLD_TOKEN LIDO TOKEN_TMP 2>/dev/null || true' EXIT

# ── Utilidades ──────────────────────────────────────────────────────────────
die()  { printf '%s[ERRO]%s %s\n' "$RED" "$RESET" "$*" >&2; exit 1; }
ok()   { printf '%s[OK]%s   %s\n' "$GREEN" "$RESET" "$*"; }
warn() { printf '%s[!]%s   %s\n' "$YELLOW" "$RESET" "$*"; }
step() { printf '\n%s==> [%s/8] %s%s\n' "$BOLD" "$1" "$2" "$RESET"; }

mask_token() {
  # hf_***...***XXXX — primeiros 6 + últimos 4. Nunca o valor inteiro.
  # (local em comandos separados: expansions de um único `local` avaliam
  #  antes de qualquer atribuição — `local t=.. n=${#t}` estouraria set -u)
  local t="${1:-}"
  local n="${#t}"
  if [ "$n" -ge 10 ]; then
    printf '%s***...***%s' "${t:0:6}" "${t: -4}"
  elif [ "$n" -gt 0 ]; then
    printf 'hf_***...***'
  else
    printf '(vazio)'
  fi
}

http_code() { # $1 = token | $2 = URL  → imprime só o status (000 = falha)
  # Token vai por STDIN (-K -), nunca em argv (ps não mostra segredo).
  local code
  code=$(printf 'header = "Authorization: Bearer %s"\n' "$1" |
    curl -sS -K - -o /dev/null -w '%{http_code}' --max-time 20 "$2" 2>/dev/null) || code=''
  printf '%s' "${code:-000}"
}

validar_token() { # $1 = token → "whoami=NNN models=NNN"; exit 0 só se 200+200
  local c1 c2
  c1=$(http_code "$1" "$HF_URL/api/whoami-v2")          # prova que o token é válido
  c2=$(http_code "$1" "$HF_URL/api/models?limit=1")     # prova leitura (read:models)
  printf 'whoami=%s models=%s' "$c1" "$c2"
  [ "$c1" = "200" ] && [ "$c2" = "200" ]
}

ler_hf_token() { # lê HF_TOKEN do .env sem imprimir; saída = valor (sem CR/espaço)
  grep -E '^HF_TOKEN=' "$ENV_FILE" | head -n1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//' || true
}

abrir_url() { # melhor esforço — se não houver opener, a URL já foi impressa
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$1" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open "$1" >/dev/null 2>&1 || true
  fi
}

# ════════════════════════════════════════════════════════════════════════════
# [1/8] Pré-checagens
# ════════════════════════════════════════════════════════════════════════════
step 1 "Pré-checagens"

for cmd in curl sed grep chmod cp date cut head; do
  command -v "$cmd" >/dev/null 2>&1 || die "comando obrigatório ausente: $cmd"
done

[ -f "$ENV_FILE" ] || die "não encontrei $ENV_FILE — rode como  bash scripts/rotate_hf_token.sh  a partir da raiz do monorepo."
[ -w "$ENV_FILE" ] || die "sem permissão de escrita em $ENV_FILE"
[ -w "$ROOT_DIR/GasFlow" ] || die "sem permissão de escrita no diretório $ROOT_DIR/GasFlow"

if command -v git >/dev/null 2>&1 && git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  # Regra: nunca rodar `git add .env` — aborta se já estiver staged.
  if [ -n "$(git -C "$ROOT_DIR" diff --cached --name-only -- "$REL_ENV")" ]; then
    die "$REL_ENV está staged. Desfaça antes:  git restore --staged $REL_ENV"
  fi
  git -C "$ROOT_DIR" check-ignore -q "$REL_ENV" ||
    die "$REL_ENV NÃO está no .gitignore — adicione (nunca commitar .env) e rode de novo."
  # Os backups que vamos criar também não podem ser commitáveis.
  git -C "$ROOT_DIR" check-ignore -q "$REL_ENV.bak.00000000_000000" ||
    warn "backups .env.bak.* não estão ignorados — sugestão:  echo 'GasFlow/.env*' >> .gitignore"
elif [ -f "$ROOT_DIR/GasFlow/.gitignore" ] || [ -f "$ROOT_DIR/.gitignore" ]; then
  grep -qE '^\.env$' "$ROOT_DIR/GasFlow/.gitignore" 2>/dev/null ||
    grep -qE '(^|/)\.env$' "$ROOT_DIR/.gitignore" 2>/dev/null ||
    die ".env não está coberto pelo .gitignore — adicione antes de continuar."
  warn "sem repositório git ativo — checagem de staged pulada (.gitignore confirmado)."
else
  die "sem git e sem .gitignore — não posso garantir que o .env jamais será commitado."
fi

grep -qE '^HF_TOKEN=' "$ENV_FILE" ||
  die "linha HF_TOKEN= (sem #) não encontrada em $ENV_FILE — descomente/crie a linha e rode de novo."

OLD_TOKEN="$(ler_hf_token)"
OLD_MASK="(nenhum token anterior em $REL_ENV)"
[ -n "$OLD_TOKEN" ] && OLD_MASK="$(mask_token "$OLD_TOKEN")"

ok "raiz: $ROOT_DIR"
ok "alvo: $REL_ENV   token atual: $OLD_MASK"

# ════════════════════════════════════════════════════════════════════════════
# [2/8] Backup
# ════════════════════════════════════════════════════════════════════════════
step 2 "Backup do .env"

BACKUP="$ENV_FILE.bak.$TS"
cp -p "$ENV_FILE" "$BACKUP" || die "falha ao criar backup $BACKUP"
chmod 600 "$BACKUP" 2>/dev/null || warn "chmod 600 no backup não disponível neste SO"
chmod 600 "$ENV_FILE" 2>/dev/null || warn "chmod 600 no .env não disponível neste SO"
[ -f "$BACKUP" ] || die "backup não foi criado: $BACKUP"
ok "backup criado: $BACKUP"

# ════════════════════════════════════════════════════════════════════════════
# [3/8] Revogação do token antigo (manual assistida)
# ════════════════════════════════════════════════════════════════════════════
step 3 "Revogação do token antigo (manual)"

printf 'Token a revogar (%s): %s\n' "$REL_ENV" "$OLD_MASK"
printf 'Painel: %s/settings/tokens\n' "$HF_URL"
abrir_url "$HF_URL/settings/tokens"
printf 'No painel: localize o token acima, clique em "Manage"/"Revoke" e confirme.\n'
printf '(A HF não expõe endpoint estável de revogação via API — por isso é manual.)\n'
read -r -p "Revogue o token $OLD_MASK e pressione ENTER para continuar... " _ ||
  die "entrada interrompida — rotação abortada (nada foi alterado)."
ok "revogação confirmada pelo operador"

# ════════════════════════════════════════════════════════════════════════════
# [4/8] Geração do token novo (manual assistida)
# ════════════════════════════════════════════════════════════════════════════
step 4 "Geração do token novo (manual)"

printf 'Crie um token FINE-GRAINED em: %s/settings/tokens\n' "$HF_URL"
printf '  - Nome:   gasflow-prod-%s\n' "$TS"
printf '  - Escopo: read:models (mínimo). write:models APENAS se o pipeline\n'
printf '            realmente precisar subir arquivos para o Hub.\n'
printf '  - Expiração: defina uma (ex.: 90 dias) em vez de "sem expiração".\n'
abrir_url "$HF_URL/settings/tokens"

tentativa=0
while [ "$tentativa" -lt 3 ]; do
  tentativa=$((tentativa + 1))
  NOVO_TOKEN=''
  read -r -s -p "Cole o novo token HF_TOKEN: " NOVO_TOKEN ||
    die "entrada interrompida — rotação abortada (nada foi alterado)."
  printf '\n'
  # cola comum: remove aspas e qualquer espaço/CR em volta
  NOVO_TOKEN="${NOVO_TOKEN//\"/}"
  NOVO_TOKEN="${NOVO_TOKEN//\'/}"
  NOVO_TOKEN="${NOVO_TOKEN//[[:space:]]/}"
  if [ -z "$NOVO_TOKEN" ]; then
    die "token vazio — rotação abortada (nada foi alterado)."
  fi
  if [[ "$NOVO_TOKEN" =~ ^hf_[A-Za-z0-9]{30,}$ ]]; then
    break
  fi
  warn "formato inválido (esperado ^hf_[A-Za-z0-9]{30,}\$) — tentativa $tentativa/3."
  NOVO_TOKEN=''
done
[[ "$NOVO_TOKEN" =~ ^hf_[A-Za-z0-9]{30,}$ ]] ||
  die "token não passou na validação de formato após 3 tentativas."

NEW_MASK="$(mask_token "$NOVO_TOKEN")"
if [ -n "$OLD_TOKEN" ] && [ "$NOVO_TOKEN" = "$OLD_TOKEN" ]; then
  die "o token novo é IGUAL ao antigo — gere outro (o antigo deve estar revogado)."
fi
ok "token novo aceito: $NEW_MASK"

# ════════════════════════════════════════════════════════════════════════════
# [5/8] Validação do token novo ANTES de gravar
# ════════════════════════════════════════════════════════════════════════════
step 5 "Validação do token novo (antes de gravar)"

RES="$(validar_token "$NOVO_TOKEN")" ||
  die "token novo recusado ($RES) — nada foi gravado. Confira revogação/escopo e rode de novo."
ok "validação HTTP: $RES"

# ════════════════════════════════════════════════════════════════════════════
# [6/8] Atualização do .env
# ════════════════════════════════════════════════════════════════════════════
step 6 "Atualização do .env"

[ -e "$ENV_FILE.bak" ] &&
  die "$ENV_FILE.bak já existe (resquício de execução anterior) — renomeie/apague e rode de novo; não vou sobrescrever."

# backup adicional inline, colado na hora da edição
INLINE_BAK="$ENV_FILE.pre.$TS"
cp -p "$ENV_FILE" "$INLINE_BAK" || die "falha no backup inline $INLINE_BAK"
chmod 600 "$INLINE_BAK" 2>/dev/null || true
ok "backup inline: $INLINE_BAK"

# sed -i.bak: único formato portátil GNU + BSD. Delimitador | (o valor é
# validado como ^hf_[A-Za-z0-9]{30,}$ — sem |, / ou & que quebrariam o sed).
sed -i.bak "s|^HF_TOKEN=.*|HF_TOKEN=${NOVO_TOKEN}|" "$ENV_FILE" ||
  die "sed falhou — restaure com:  cp '$BACKUP' '$ENV_FILE'"
rm -f "$ENV_FILE.bak"   # artefato do sed (cópia do token antigo) — já temos os backups

N_LINHAS=$(grep -cE '^HF_TOKEN=' "$ENV_FILE" || true)
[ "$N_LINHAS" -gt 1 ] && warn "$N_LINHAS linhas HF_TOKEN= no .env — edite para manter apenas uma."

LIDO="$(ler_hf_token)"
if [ "$LIDO" != "$NOVO_TOKEN" ]; then
  die "valor gravado não bate com o token novo — restaure o backup:  cp '$BACKUP' '$ENV_FILE'"
fi
chmod 600 "$ENV_FILE" 2>/dev/null || warn "chmod 600 no .env não disponível neste SO"
ok "gravado: HF_TOKEN=$NEW_MASK"

# ════════════════════════════════════════════════════════════════════════════
# [7/8] Verificação pós-gravação
# ════════════════════════════════════════════════════════════════════════════
step 7 "Verificação pós-gravação"

RES="$(validar_token "$LIDO")" ||
  die "token gravado não passa na validação ($RES) — restaure:  cp '$BACKUP' '$ENV_FILE'"
ok "token no .env validado: $RES"

unset NOVO_TOKEN LIDO          # limpeza imediata (o trap repete na saída)

# Varredura de segredos: gitleaks se existir, senão grep com exclusões.
SCAN_MODO="gitleaks"
LEAK_REPORT="${TMPDIR:-/tmp}/hf_rotate_leaks.$$.json"
achados_fora=''
if command -v gitleaks >/dev/null 2>&1; then
  gitleaks detect --no-git --source "$ROOT_DIR" --report-format json \
    --report-path "$LEAK_REPORT" --no-banner >/dev/null 2>&1 || true
  if [ -s "$LEAK_REPORT" ]; then
    arquivos=$(grep -oE '"File":[[:space:]]*"[^"]+"' "$LEAK_REPORT" 2>/dev/null |
      sed -E 's/^.*"File":[[:space:]]*"//; s/"$//' || true)
    if [ -z "$arquivos" ]; then
      rm -f "$LEAK_REPORT"
      die "gitleaks achou algo mas não consegui ler o relatório — rode manualmente:  gitleaks detect --no-git --source ."
    fi
    while IFS= read -r arquivo; do
      [ -z "$arquivo" ] && continue
      base="${arquivo##*/}"
      case "$base" in
        .env | .env.* | *.env | *.env.*) ;; # segredos dentro de .env* são esperados
        *) achados_fora="${achados_fora}${arquivo}"$'\n' ;;
      esac
    done <<<"$arquivos"
    rm -f "$LEAK_REPORT"
  fi
else
  SCAN_MODO="grep"
  warn "gitleaks não encontrado — varredura de fallback com grep (menos abrangente)."
  achados_fora=$(grep -RIl --binary-files=without-match -E 'hf_[A-Za-z0-9]{30,}' \
    --exclude='.env' --exclude='.env.*' --exclude='*.env' --exclude='*.env.*' \
    --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv \
    --exclude-dir=venv --exclude-dir=__pycache__ --exclude-dir=dist \
    --exclude-dir=build --exclude-dir=logs --exclude-dir=.pytest_cache \
    "$ROOT_DIR" 2>/dev/null || true)
fi

if [ -n "$achados_fora" ]; then
  printf '%s' "$achados_fora" >&2
  die "token hf_ em texto plano FORA de .env (arquivos acima) — corrija/limpe e rode de novo."
fi
ok "varredura de segredos limpa ($SCAN_MODO) — nada de hf_ fora de .env*"

# ════════════════════════════════════════════════════════════════════════════
# [8/8] Relatório final + CHANGELOG-seguranca.md
# ════════════════════════════════════════════════════════════════════════════
step 8 "Relatório final"

RESP="${SRE_OWNER:-}"
if [ -z "$RESP" ]; then RESP="$(git config user.name 2>/dev/null || true)"; fi
if [ -z "$RESP" ]; then RESP="${USER:-${USERNAME:-não informado}}"; fi

CHANGELOG="$ROOT_DIR/CHANGELOG-seguranca.md"
if [ ! -f "$CHANGELOG" ]; then
  printf '# CHANGELOG de Segurança\n\n' >"$CHANGELOG"
fi
{
  printf '## %s — Rotação HF_TOKEN\n' "$(date +%Y-%m-%d)"
  printf -- '- Motivo: vazamento em chat\n'
  printf -- '- Responsável: %s\n' "$RESP"
  printf -- '- Token antigo: %s (revogado)\n' "$OLD_MASK"
  printf -- '- Token novo: %s (ativo)\n' "$NEW_MASK"
  printf -- '- Escopo: read:models\n\n'
} >>"$CHANGELOG"
ok "registro gravado em CHANGELOG-seguranca.md (sem valores — só mascarados)"

printf '\n%sChecklist:%s\n' "$BOLD" "$RESET"
printf ' [x] Token antigo revogado manualmente (%s)\n' "$OLD_MASK"
printf ' [x] Token novo gravado em %s (%s)\n' "$REL_ENV" "$NEW_MASK"
printf ' [x] .env com permissão 600 (ou melhor disponível no SO)\n'
printf ' [x] Backup em %s\n' "${BACKUP#"$ROOT_DIR/"}"
printf ' [x] Token novo validado (HTTP 200: whoami + models)\n'
if [ "$SCAN_MODO" = "gitleaks" ]; then
  printf ' [x] gitleaks limpo\n'
else
  printf ' [x] varredura grep limpa (gitleaks indisponível)\n'
fi

printf '\n%sLembretes manuais:%s\n' "$BOLD" "$RESET"
printf -- '- CI/CD: atualizar o segredo em GitHub (Settings > Secrets and variables\n'
printf -- '  > Actions) ou GitLab (Settings > CI/CD > Variables) com o token novo.\n'
printf -- '- Docker/K8s: atualizar o Secret que embute HF_TOKEN e reiniciar os pods.\n'
printf -- '- Qualquer outra cópia do token antigo (notebook, outro .env, automation)\n'
printf -- '  deve receber o MESMO tratamento — o antigo já está revogado.\n'
printf -- '- Backups .env.bak.* guardam o token ANTIGO (revogado): pode mantê-los\n'
printf -- '  para auditoria ou apagá-los quando não forem mais necessários.\n'

exit 0
