# Runbook — Ativação do WhatsApp Business Cloud API (Meta)

> Pré-requisitos do código já entregues: adapter, factory (`WHATSAPP_PROVIDER=cloud_api`),
> webhook assinado e smoke-test. Este documento cobre **o que só você pode fazer**
> (conta Meta) e a sequência de ativação.

## 1. Obter credenciais (Meta Business)

| Credencial | Onde obter | Vai para |
|---|---|---|
| **Phone Number ID** | Meta App Dashboard → WhatsApp → API Setup | `WHATSAPP_CLOUD_API_PHONE_NUMBER_ID` |
| **WABA ID** (Business Account) | Meta App Dashboard → WhatsApp → Configuração | (referência; não usado pelo adapter) |
| **Access Token permanente** | Business Settings → Usuários → Usuários do Sistema → criar System User → gerar token com permissões `whatsapp_business_messaging` + `whatsapp_business_management` | `WHATSAPP_CLOUD_API_TOKEN` |
| **App Secret** | Meta App Dashboard → Configurações → Básico → App Secret | `WHATSAPP_CLOUD_API_APP_SECRET` |
| **Verify Token** | Você inventa (string aleatória) — mesma string no servidor e no dashboard | `WHATSAPP_CLOUD_API_VERIFY_TOKEN` |

Notas:
- Token temporário do API Setup expira em 24h — use System User para produção.
- O número precisa ser verificado (SMS/ligação) e não pode estar ativo no
  WhatsApp comum/app ao mesmo tempo.

## 2. Aprovar templates (para campanhas)

Meta App Dashboard → WhatsApp → Message Templates → Criar.

Sugestões iniciais (categoria MARKETING/UTILITY conforme o caso):

- `pedido_recebido` (UTILITY): "Olá {{1}}, recebemos seu pedido #{{2}}. Valor: {{3}}."
- `entrega_confirmada` (UTILITY): "Olá {{1}}, sua entrega do pedido #{{2}} foi confirmada."
- `campanha_promocional` (MARKETING): respeitar opt-out no texto.

Aprovação costuma levar minutos a algumas horas. Sem template aprovado,
campanhas fora da janela de 24h **não funcionam** (erro 131047/132000).

## 3. Configurar o webhook (após deploy com TLS público)

Meta App Dashboard → WhatsApp → Configuration → Webhook:

1. **Callback URL**: `https://SEU-DOMINIO/api/v1/whatsapp/cloud-api/webhook`
2. **Verify token**: o mesmo de `WHATSAPP_CLOUD_API_VERIFY_TOKEN`
3. Clicar em "Verify and save" — a Meta faz o handshake GET (endpoint já
   responde com o `hub.challenge`).
4. Subscrever aos campos: `messages` (mensagens recebidas + statuses de entrega).

Validação de ponta a ponta sem esperar a Meta:

```bash
cd GasFlow/backend
python ../scripts/cloud_api_smoke_test.py --verify-webhook https://SEU-DOMINIO/api/v1
```

## 4. Ativar no GasFlow

`.env` (ou variáveis do compose — já repassadas ao backend):

```env
WHATSAPP_PROVIDER=cloud_api
WHATSAPP_CLOUD_API_TOKEN=EAAG...
WHATSAPP_CLOUD_API_PHONE_NUMBER_ID=123456789
WHATSAPP_CLOUD_API_WABA_ID=987654321
WHATSAPP_CLOUD_API_APP_SECRET=...
WHATSAPP_CLOUD_API_VERIFY_TOKEN=...
WHATSAPP_CLOUD_API_VERSION=v21.0
WHATSAPP_CLOUD_API_TEMPLATE_ORDER_RECEIVED=pedido_recebido
WHATSAPP_CLOUD_API_TEMPLATE_DELIVERY_CONFIRMED=entrega_confirmada
```

O `WABA_ID` é opcional, mas habilita `list_message_templates()` — usado para
conferir que os templates configurados estão `APPROVED` antes de campanhas.

```bash
docker compose up -d --build backend
```

## 5. Smoke test em 4 passos

```bash
cd GasFlow/backend

# 1. Credenciais + qualidade do número (não envia nada)
python ../scripts/cloud_api_smoke_test.py --check-config

# 2. Texto livre — exige que o número teste tenha mandado mensagem nas últimas 24h
#    (no painel da Meta, envie uma mensagem do seu celular para o número de teste)
python ../scripts/cloud_api_smoke_test.py --send-text 5591999999999 "Teste GasFlow"

# 3. Template (qualquer momento) — use um template já aprovado
python ../scripts/cloud_api_smoke_test.py \
  --send-template 5591999999999 entrega_confirmada \
  --params "João" "42"

# 4. Webhook
python ../scripts/cloud_api_smoke_test.py --verify-webhook https://SEU-DOMINIO/api/v1
```

Cada passo imprime o erro da Meta com dica (131047 = fora da janela 24h,
132000 = template inexistente, 401/403 = token/permissão).

## 6. Ordem de migração de campanhas

1. `WHATSAPP_PROVIDER=cloud_api` + validar passos 1–5 acima.
2. Roteio das campanhas do backend para `send_template` (próxima fase de código).
3. Só então: `WA_BROADCAST_ENABLED=false` no serviço Node — canal não-oficial
   fica reservado ao tráfego conversacional.

## 7. Qualidade do número (evitar degradação)

Dashboard → WhatsApp → Quality rating. Manter GREEN:

- Só envie para quem optou em (a base já respeita OPTED_OUT/SUPPRESSED/BLOCKED).
- Templates com conteúdo igual ao aprovado; sem placeholders quebrados.
- Monitore conversões de template (erros 131026 = destinatário não tem WhatsApp
  ou bloqueou) — taxa alta degrada a qualidade em dias.
