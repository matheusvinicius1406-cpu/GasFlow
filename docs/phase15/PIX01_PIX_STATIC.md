# PIX-01 — PIX Estático (BR Code + QR Code)

**Status:** CONCLUÍDO — suíte 1162 passed / 27 skipped · ruff limpo · tsc FE 0 erros

---

## Contexto real (auditado antes de implementar)

O GasFlow já tinha a **gestão de configuração PIX por tenant** (`pix_configs`
table, `PixConfig` domain, CRUD em `/payments/pix` e `/payments/pix/{id}`)
e o modelo de pagamentos com campos `pix_key_used` / `pix_copy_paste`.

**O que faltava (e foi implementado):**
- Gerar o **BR Code** (copia-e-cola) — o campo `copy_paste_code` existia mas
  nunca era preenchido;
- Gerar o **QR Code** (imagem PNG base64);
- Um endpoint para **gerar o payload de pagamento** de um pedido;
- Consulta de **status por TXID**.

## Decisão de dependência

**Não** usamos `pypix`. O BR Code PIX é uma spec pequena e determinística
(EMV® QR + campos BACEN + CRC16-CCITT); implementá-la localmente em
`app/domain/payment/pix_service.py` evita uma dependência externa não
verificada e torna o comportamento 100% testável (CRC recomputado nos
testes). Só `qrcode` (puro Python) + `Pillow` foram adicionados — e Pillow
já estava presente no ambiente.

## Implementado

### `app/domain/payment/pix_service.py` (novo)
- `build_pix_copy_paste(key, key_type, merchant_name, merchant_city, amount,
  description, txid)` → BR Code completo com CRC16-CCITT (0x1021/0xFFFF);
- `validate_pix_key(key, key_type)` → CPF (11), CNPJ (14), EMAIL, PHONE,
  RANDOM; `ValueError` se inválido;
- `PixService.generate_payload(...)` → dict com `br_code`, `qr_code`
  (data URI PNG), `txid` (sanitizado, máx 25 alfanumérico; `***` no estático),
  `amount`, `key`, `key_type`, `merchant_name`, `merchant_city`;
- Normalização de acentos/ASCII e limites de tamanho da spec (nome ≤ 25,
  cidade ≤ 15).

### `app/domain/payment/service.py` (wiring)
- `create_pix_config` / `update_pix_config` → agora **populam
  `copy_paste_code`** com o BR Code estático da chave;
- `create_payment` (método PIX/PIX_DYNAMIC) → **gera BR Code com o valor do
  pedido** e grava em `pix_copy_paste` (antes ficava vazio);
- `generate_pix_payload(tenant_id, amount, description, order_codigo)` →
  payload pronto usando a config ativa; `None` se sem chave; `ValueError`
  se amount ≤ 0;
- TXID determinístico do pedido: `GAS{codigo}` (sanitizado).

### `app/presentation/api/payments.py` (endpoints — sem colidir com CRUD)
- `POST /payments/pix/payload` → gera BR Code + QR do tenant
  (400 se amount ≤ 0; 409 se sem chave ativa);
- `GET /payments/pix/{txid}/status` → status tenant-scoped (busca por
  `external_id`/`pix_copy_paste`; `NOT_FOUND` até o PSP/webhook existir).

### Frontend
- `client.ts`: métodos `payments.generatePix` e `payments.pixStatus`.

### requirements.txt
- `qrcode` + `Pillow`.

## Testes (`tests/test_pix_service.py`, +21)
- **Lib**: estrutura do payload, CRC válido, valor BRL (vírgula), TXID
  sanitizado/truncado, TXID estático `***`, valores inválidos (0/negativo),
  chave ausente, validação de chave por tipo, QR é PNG, campos do payload;
- **Service**: config → copy_paste_code; create_payment PIX → BR Code com
  valor; generate_pix_payload com/sem config; isolamento por tenant;
- **HTTP** (determinístico, service stubado): 409 sem config, 200 com QR,
  400 amount inválido, status NOT_FOUND e status PENDING após payment.

Validação ao vivo: payload real conferido — CRC re-computado por
implementação de referência independente (bate).

## Riscos / pendências
- **PSP/webhook**: `GET /payments/pix/{txid}/status` retorna `NOT_FOUND`
  até haver integração com banco — confirmação segue manual
  (`POST /payments/{id}/confirm`);
- Validação de dígitos verificadores (CPF/CNPJ) não aplicada — apenas
  tamanho (P3);
- UI de exibição do QR no fluxo de pedido: os métodos no client estão
  prontos; a tela depende do fluxo de checkout (ver FE-02/ordem de pedidos).