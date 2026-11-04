# Achados, correções e riscos residuais

Cada item tem: sintoma observado, causa, o que foi feito e como verificar.
Evidências brutas em `evidence/`.

## Resumo

| ID | Severidade | Tema | Status |
|---|---|---|---|
| R-1 | Alta | Backend abortava no boot (dialeto SQL) | **Resolvido** |
| R-2 | Alta | Handshake TLS abortado para acesso por IP | **Resolvido** |
| R-6 | Alta | Itens de pedido gravados no tenant `default` | **Resolvido** |
| R-7 | Alta | Estoque sem `tenant_id` no insert/débito | **Resolvido** |
| R-8 | **Crítica** | Bypass de senha quando `password_hash` vazio | **Resolvido** |
| R-3 | Média | `/auth/mobile/login` inutilizável para entregador novo | Aberto (decisão) |
| R-5 | Média | Políticas de rate limit não casam com `/api/*` | Aberto |
| R-4 | Baixa | Três superfícies de entregador + tenant fixo no legado | Aberto |
| R-9 | Baixa | 500 pontual após restart do Postgres | Aceito |
| R-10 | Média | Backup sem destino independente (um disco só) | Limitação |
| R-11 | Baixa | Produtos duplicados no tenant de laboratório | Higiene de lab |

---

## R-1 — Backend abortava no boot · **Resolvido**

**Sintoma:** log de boot com erro de dialeto SQL ("schema migration leve
falhou"), backend sem subir.

**Causa:** SQL incompatível com o dialeto no caminho de preparação.

**Verificação:** `evidence/01_BOOT.txt` — `alembic current` = `a4b5c6d7e8f9
(head)`, 69 tabelas, **0** ocorrências do erro no log.

---

## R-2 — TLS abortado para clientes que acessam por IP · **Resolvido**

**Sintoma:** `openssl s_client -connect 192.168.0.204:443` (sem
`-servername`) devolvia `TLSV1_ALERT_INTERNAL_ERROR`; navegador no celular
não abria `https://192.168.0.204`.

> **Nota histórica:** o sintoma foi observado quando o servidor estava em
> `192.168.0.204`. O IP atual é `192.168.0.211` (DHCP); a correção e a
> verificação valem para qualquer IP configurado em `GASFLOW_LAN_IP`.

**Causa:** navegador/Android **não enviam SNI em conexão por IP** (RFC 6066).
Com dois sites no Caddy, sem SNI ele não escolhe certificado e aborta.

**Correção:** `default_sni {$GASFLOW_LAN_IP}` no bloco global do `Caddyfile`.

**Verificação:** handshake sem SNI passa; `verify_lan_https.py` valida a
cadeia → 9/9 (`evidence/06_HTTPS.txt`).

---

## R-6 — Itens de pedido no tenant errado · **Resolvido**

**Sintoma:** pedidos no tenant `gasflow_home_server_lab` com `order_items`
gravados em `tenant_id='default'` (0 itens visíveis no tenant).

**Causa:** `SQLAlchemyOrderItemRepository._to_model` não passava
`tenant_id`; a coluna caía no default `"default"`. Como a leitura é filtrada
por tenant, o item sumia — e, porque o código do pedido reinicia por tenant
(`000001`, `000002`…), itens de tenants distintos colidiam no mesmo bucket.

**Correção:** `tenant_id=self.tenant_id` na criação do modelo; 4 linhas
existentes no laboratório corrigidas (`UPDATE 4`).

**Verificação:** `select tenant_id, order_codigo ... from order_items` mostra
todos no tenant correto; teste novo
`tests/test_order_item_tenant_isolation.py` (2 passed).

> Mesma classe do R-7. Vale auditar qualquer repositório que herde
> `TenantMixin` e construa modelo sem `tenant_id` explicitamente.

---

## R-7 — Estoque sem `tenant_id` · **Resolvido**

**Sintoma:** `inventory` criado/atualizado sem tenant, invisível para o
tenant real.

**Correção (na árvore de trabalho):**
`inventory_repository.py` passa `tenant_id=self.tenant_id` no insert e nos
`UPDATE` atômicos de débito.

**Verificação:** `select tenant_id, count(*) from inventory group by 1`
mostra somente `gasflow_home_server_lab`.

---

## R-8 — Bypass de autenticação no login de entregador · **Resolvido**

**Sintoma (código):** em `/auth/mobile/login` e no login legado
`/api/v1/driver/auth/login`:

```python
if driver.password_hash:
    if not bcrypt.checkpw(...):
        raise 401
```

Quando `password_hash` era vazio/NULL a checagem era **pulada** — qualquer
senha autenticava. O fluxo canônico de criação de entregador
(`POST /api/v1/admin/drivers`) **nasce** com esse campo vazio, então a
condição era alcançável.

**Correção:** falha fechada nos dois caminhos — sem hash, `401`.

**Verificação:** `tests/test_driver_login_requires_password_hash.py` (2
passed) cobre mobile e legado com senha arbitrária. A suíte
`test_driver_mobile.py` continua passando (sem regressão).

**Runtime:** a imagem `sha256:0c7373b5…` (03/11 15:53Z) ainda tinha o código
antigo. Em 04/11 12:49Z o backend foi reconstruído e o container recriado às
12:51Z; a imagem atual (`sha256:ce593188…`) contém `stored_hash` nos dois
caminhos (`evidence/IMAGE_IDENTITY.txt`).

**Impacto no laboratório:** nenhum entregador ficou bloqueado — o único
existente tem username vazio e autentica pelo fluxo principal.

---

## R-3 — `/auth/mobile/login` inutilizável para entregador criado hoje · **Aberto**

**Sintoma:** `401` mesmo com a senha correta.

**Causa:** três fatos combinados:

1. `/auth/mobile/login` busca em `delivery_drivers.username` +
   `password_hash`;
2. `POST /api/v1/admin/drivers` grava a credencial em `auth_users` e **não**
   preenche as colunas de `delivery_drivers`;
3. O login legado ainda usa `tenant_id="default"` fixo no repositório.

**O que foi feito:** documentado o fluxo suportado (`POST /auth/login` +
`/driver/*`), que funciona ponta a ponta (login `200`, `/driver/me` `200`).
O laboratório foi provisionado por esse caminho.

**Decisão pendente:** (a) descontinuar `/auth/mobile/login`, ou
(b) fazer o create-driver popular `delivery_drivers.username/password_hash`.
Recomendo (a): manter duas credenciais para o mesmo entregador duplica
superfície de ataque.

---

## R-5 — Políticas de rate limit não casam com `/api/*` · **Aberto**

**Sintoma (código):** `_get_policy()` compara prefixos como `/auth/login`,
`/orders`, `/driver` com o path **completo**. O SPA chama `/api/...`, então
nenhuma política específica casa e tudo cai em `read` (**120/min**), num
único bucket `client_id + ":api"`.

**Efeito:** o limite existe (não é bypass), mas `login`, `mutation` e `admin`
ficam inertes para o SPA, e toda a API compartilha um bucket por IP — o que
pode gerar `429` em uso intenso legítimo.

**Sugestão:** remover o prefixo `/api` (e `/api/v1`) antes de casar a
política, e incluir o nome da política na chave do bucket.

**Observação prática:** o limite que domina o teste manual é o do serviço de
auth — `login:{username}` 5/300 s. Reentrar repetidamente com o mesmo
usuário produz `429` mesmo com o middleware folgado.

---

## R-4 — Três superfícies de entregador · **Aberto (baixo)**

Existem, simultaneamente:

| Superfície | Auth | Situação |
|---|---|---|
| `/driver/*` | sessão principal + papel DRIVER | **usar** |
| `/api/v1/driver/*` | `driver_sessions` | 401 com token de sessão principal |
| `/api/driver/v1/*` e `/auth/mobile/login` | sessão própria/JWT mobile | legado, marcado no código |

Risco: cliente novo escolher a errada e receber 401 sem explicação. Já está
registrado no código como legado; falta um aviso explícito no contrato
público (feito em `AUTH_CONTRACT.md`).

---

## R-9 — 500 pontual após restart do Postgres · **Aceito**

**Sintoma:** a primeira requisição que toca o banco após reiniciar o
Postgres devolve `500`; as seguintes voltam a `200`.

**Causa:** conexão morta no pool durante a janela de recuperação.
`pool_pre_ping=True` está ativo e a recuperação é automática em segundos.

**Aceito** com nota operacional em `OPERATIONS.md` §3. Se incomodar, um
retry no cliente resolve sem mudar o servidor.

---

## R-10 — Backup sem destino independente · **Limitação**

O host tem um disco só. O manifest registra `"off_host": false`. Backup
protege contra erro de operação, **não** contra perda do disco. Pendência P1:
segundo volume/HD externo e só então `--confirm-off-host`.

---

## R-11 — Produtos duplicados no laboratório · **Higiene**

`POST /api/v1/products` **ignora** `codigo` e gera o seu próprio. O seeder
tentou ser idempotente por código e criou `000001`…`000006` (três pares).
Além disso, entrada de estoque é **aditiva**: rodar o seeder duas vezes
dobrou a quantidade (50 → 100).

Não afeta produção, mas o tenant de laboratório tem 6 produtos para 2 SKUs.
Limpar com `DELETE`/inativação antes de usar como demonstração.
