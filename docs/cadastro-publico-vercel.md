# Cadastro público por convite (Vercel) + orquestrador — F10

Canal web público do auto-cadastro por indicação: o cliente indicado
recebe um **link** e se cadastra numa **página pública** que fala direto
com a API central. É o fallback **(b) do §5** do spec
(`docs/entregas-cupons-spec.md`), agora o canal preferido do dono — o
cadastro capturado pela IA na conversa (canal (a)) **continua existindo**;
os dois usam exatamente o mesmo `ReferralService`.

## Arquitetura

```
┌──────────────── Vercel (SPA estática, frontend/) ────────────────┐
│  /cadastro?token=GF-INV-…   ← rota pública, sem login            │
└───────────────┬──────────────────────────────────────────────────┘
                │  VITE_API_URL (build-time) → HTTPS público
                ▼
        Cloudflare Tunnel (mesmo padrão do relay)
                │
                ▼
┌──────────────── Electron (app aberto = tudo vivo) ───────────────┐
│  Orquestrador (F10.3): health loop + restart com backoff         │
│    ├─ backend  (FastAPI — a API central)                         │
│    ├─ whatsapp (Baileys)                                         │
│    └─ agent                                                      │
└──────────────────────────────────────────────────────────────────┘
```

Ponto-chave: **a Vercel hospeda a página, não a API.** A API central roda
no desktop; quem a torna alcançável é o túnel. Por isso a página funciona
"enquanto o app estiver aberto".

## Fluxo

1. Operador gera o convite em **Promoções** → `POST /coupons/generate-invite-token`.
   Com a setting `referral.signup_base_url` configurada, a resposta traz
   `signup_url = {base}/cadastro?token=GF-INV-…` (copiar e enviar ao cliente).
   Sem a setting, o frontend mantém o link `wa.me` legado.
2. Cliente abre a página (rota pública `/cadastro`, sem login). Antes de
   mostrar o formulário, a página **consulta o convite**
   (`GET /public/referral/invite/{token}`): link já usado ou inexistente é
   avisado na hora, sem pedir nenhum dado. Se a consulta não responder (loja
   fora do ar), o formulário aparece mesmo assim — o envio tem a fila local.
3. `POST {VITE_API_URL}/public/referral/signup` → endpoint público
   (`app/presentation/api/public_signup.py`) → `ReferralService.complete_signup`
   (token single-use, upsert por telefone, cupom para os dois, teto de
   10 indicações/mês por indicador).
4. A tela de sucesso mostra **o cupom do próprio indicado**.

### Consulta do convite (antes do formulário)

`GET /public/referral/invite/{token}` responde **200 sempre**, com
`{valid, reason, coupon_value, coupon_type, validity_days}` — é uma consulta,
não uma ação, então "já usado" é resposta esperada (e não enche log/monitor de
4xx à toa):

| `reason` | O que a página faz |
| --- | --- |
| `ok` | Mostra o formulário, já com o valor do cupom ("você ganha R$ 10,00") |
| `already_used` | Avisa que o link já foi usado + atalho para reaver o cupom |
| `not_found` | Convite não encontrado — pede um link novo |
| `malformed` | Token fora do padrão `GF-INV-…` |

Sem PII: nunca devolve o nome nem dados de quem indicou (LGPD) — só o que o
próprio indicado ganha. Limite de 60 consultas por IP por hora.

Quem se cadastrou e não anotou o cupom usa o atalho **"Já preenchi meus
dados — quero ver meu cupom"**: informando o **mesmo WhatsApp**, o envio cai no
replay idempotente (acima) e devolve o cupom original.

Com cadastro **pendente** na fila local a consulta é pulada de propósito: o
token pode ter sido consumido pelo próprio reenvio, e um "já usado" esconderia
justamente a recuperação do cupom.

## Deploy do frontend na Vercel

1. Importar este repositório na Vercel.
2. **Root Directory = `frontend`** (o `frontend/vercel.json` define framework
   `vite`, build `npm run build`, output `dist`, rewrites de SPA para as rotas
   e headers de segurança).
3. Variável de ambiente (Production):
   - `VITE_API_URL` = URL pública da API central (ex.: `https://api.seudominio.com`),
     **sem barra final**. Ela é embutida no build — mudar o valor exige redeploy.
4. Domínio próprio é opcional (ex.: `convite.seudominio.com`).

## Expor a API central (túnel)

O mesmo padrão do relay (ver `relay/DEPLOY.md`):

- **Teste:** `cloudflared tunnel --url http://127.0.0.1:8000` (URL
  `trycloudflare.com` — muda a cada execução, então exige redeploy da Vercel).
- **Produção:** túnel nomeado com domínio estável (ex.: `api.seudominio.com`),
  apontando para a porta do backend do desktop.

> Use túnel nomeado em produção. A URL do quick tunnel muda e a página na
> Vercel passa a apontar para um endereço morto.

## Configuração (variáveis e settings)

| Onde | Nome | Exemplo |
| --- | --- | --- |
| Vercel (build) | `VITE_API_URL` | `https://api.seudominio.com` |
| Backend (env do desktop/compose) | `PUBLIC_SIGNUP_ORIGINS` | `https://gasflow.vercel.app` |
| Admin → Configurações | `referral.signup_base_url` | `https://gasflow.vercel.app` |

`PUBLIC_SIGNUP_ORIGINS` é somada a `CORS_ORIGINS` na hora de montar o CORS
(a página chama a API a partir de **outra origem**). Vários domínios:
separados por vírgula. Liberar só o domínio público evita abrir o CORS do
admin inteiro.

## Teste rápido

```bash
API=https://api.seudominio.com

curl -i -X POST "$API/public/referral/signup" \
  -H 'Content-Type: application/json' \
  -d '{"inviteToken":"GF-INV-xxxxxxxxxxxxxxxxxxxx","name":"Maria Souza",
       "phone":"11988887777","rua":"Rua das Flores","numero":"120",
       "bairro":"Centro","lgpdConsent":true}'
```

Esperado: `200` com `coupon_code` (e `coupon_value`/`coupon_valid_until`).
Token repetido com **outro** telefone → `409`; repetido com o **mesmo**
telefone → `200` com `status: "replayed"` e o mesmo cupom; 4ª tentativa no
mesmo telefone em 1h ou 6ª no mesmo IP em 1h → `429`; sem `lgpdConsent` →
`422`.

Consulta antes do formulário:

```bash
curl -s "$API/public/referral/invite/GF-INV-xxxxxxxxxxxxxxxxxxxx"
# {"valid":true,"reason":"ok","coupon_value":10.0,"coupon_type":"PERCENTUAL","validity_days":90}
# link já usado → {"valid":false,"reason":"already_used",...}
```

## Segurança

- **Sem auth por design**: o token de convite é a capacidade. Ele é
  aleatório de alta entropia e single-use.
- **Rate limit duplo**: 3 cadastros/hora por telefone e 5/hora por IP, via
  `WhatsAppLimitStore` (Redis quando `RATE_LIMIT_MODE=redis`; fallback
  in-memory). Aqui o limite por IP enfim **funciona de verdade** — a
  requisição vem do navegador, não do webhook do WhatsApp (R1 da F4.5).
- **Sem vazamento**: o endpoint só cria; nunca lista nem expõe dados de
  terceiros. A resposta carrega apenas o cupom do próprio indicado.
- **LGPD**: consentimento obrigatório, validado no backend (não só na UI).
- **Atenção ao expor a API pela internet**: o túnel aponta para a porta do
  backend, então *toda* a API fica alcançável. As rotas de admin seguem
  protegidas por Bearer + RBAC e o rate limiter global continua ativo, mas a
  superfície de ataque aumenta — vale restringir por regra de firewall/WAF do
  túnel ao que é público (`/public/*`) se o provedor permitir.

## Resiliência (orquestrador)

`desktop/src/main/orchestrator.ts` supervisiona os serviços locais:

- Health check periódico (default 15s por serviço).
- Queda → **restart com backoff exponencial** (2s → 4s → … teto de 60s).
- Após 5 falhas seguidas o serviço é **pausado** (evita crash-loop) e o
  operador é notificado; retomada manual por IPC.
- Estado de saúde persistido em `userData/health-state.json` — sobrevive a
  reinício do app (degradação visível, não silenciosa).
- IPC exposto: `orchestrator:status` e `orchestrator:resume`.

Persistência dos dados não muda: SQLite em `userData/gasflow.db` e a sessão
do Baileys no disco — reiniciar o app **não** perde cadastro, pedido nem
pareamento.

## Reenvio automático (fila local — F10.5)

Quando a API não responde (rede fora, túnel caído, 5xx ou excesso de
requisições), o formulário é gravado no aparelho do cliente (`localStorage`) e
a página reenvia sozinha:

- com a página aberta: backoff de 3s → 8s → 20s → 60s (teto);
- quando a internet volta (evento `online`): tenta na hora;
- ao reabrir o mesmo link: devolve o que já foi digitado e reenvia;
- o registro é descartado depois de 7 dias.

Falhas **definitivas** (convite inválido, já usado, validação) não são
reenviadas: limpam a fila e mostram o erro.

Reenviar é seguro porque o backend é **idempotente por (token + telefone)**: se
a resposta se perdeu depois do commit, `complete_signup` devolve o **mesmo
cupom** (`status: "replayed"`) em vez de 409 — sem cliente nem cupom
duplicado. Token usado por **outro** telefone continua 409 (single-use).

Um `429` não é registrado pelo rate limiter (a janela deslizante só conta
requisições **aceitas**), então reenviar não prolonga o bloqueio.

## O que acontece se…

| Situação | Comportamento |
| --- | --- |
| App fechado / PC desligado | O túnel cai; a página guarda o formulário no aparelho e reenvia sozinha (ao voltar a internet, ao reabrir o link ou com backoff). |
| Resposta perdida depois do commit | O reenvio recebe o **mesmo cupom** em vez de "convite já utilizado" (replay idempotente por token + telefone). |
| Backend reinicia no meio do cadastro | Enquanto o cadastro não conclui, o token continua válido: reenviar o formulário funciona (sem duplicar cliente). |
| Serviço morre durante a operação | O orquestrador reinicia com backoff; se falhar 5× seguidas, pausa e notifica. |
| Link já usado | A página avisa **antes** do formulário (consulta do convite) e mostra o atalho para reaver o cupom com o mesmo WhatsApp. |
| Consulta do convite fora do ar | O formulário aparece mesmo assim (otimista) e o envio segue normalmente com a fila local. |
| Cliente fecha a página e nunca volta | Não há reenvio em segundo plano (nada de service worker): o registro fica no aparelho por 7 dias e sai na próxima abertura do link. |
