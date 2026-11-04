# Contrato de autenticação e endpoints (web, operador e entregador)

Levantado **por execução** contra a pilha de laboratório em 03/11/2026, não
por leitura de intenção. Tudo abaixo foi exercitado com HTTP real.

## 1. Modelo de identidade

- `auth_users` é **global** (sem `tenant_id`).
- Vínculo com empresa fica em `auth_memberships` (`user_id`, `tenant_id`,
  `role_id`). Papéis: `ADMIN`, `MANAGER`, `OPERATOR`, `DRIVER`, `VIEWER`,
  `CUSTOMER`, `SYSTEM`.
- A sessão carrega **um** tenant (o da membership). O admin de plataforma
  (tenant `default`) continua em `default` mesmo depois de criar outro
  tenant; para operar num tenant, entre com um usuário membro dele.
- Papel `ADMIN` em `default` é o escopo de **plataforma** (criar tenants,
  usuários, papéis globais).

## 2. Console / operador

### Login

```http
POST /auth/login
Content-Type: application/json

{"username": "lab_operador", "password": "...", "platform": "desktop"}
```

`200` devolve:

```json
{
  "success": true,
  "token": "<sessão opaca>",
  "access_token": "<token do console>",
  "refresh_token": "...",
  "token_type": "Bearer",
  "expires_in": 28800,
  "user": {"id": "...", "username": "...", "role": "OPERATOR"},
  "tenant_id": "gasflow_home_server_lab",
  "role": "OPERATOR"
}
```

- Use `Authorization: Bearer <token>` (ou `access_token`). Os dois funcionam
  nas rotas `/api/*` e `/auth/me`.
- O SPA usa o alias `/api/...` (ex.: `POST /api/auth/login`); os mesmos
  handlers existem na raiz. Prefira a raiz em integrações novas.
- `/api/auth/login` e `/auth/login` compartilham os mesmos limites.

### Sessão e troca de senha

| Método | Rota | Observação |
|---|---|---|
| GET | `/auth/me` | `id`, `username`, `email`, `display_name`, `status`, `tenant_id`, `role`, `permissions`, `must_change_password` |
| POST | `/auth/change-password` | `{current_password, new_password}`; limpa a flag |
| POST | `/auth/logout` | encerra a sessão |
| GET | `/auth/roles` | exige ADMIN |
| GET | `/auth/audit` | exige ADMIN |

**Gate de senha temporária (P0 3.8):** enquanto `must_change_password=true`,
**toda** rota fora da allowlist de `/auth` responde

```
403 {"detail": "Password change required"}
X-GasFlow-Password-Change-Required: 1
```

Isso vale para HTTP e WebSocket. O cliente precisa chamar
`/auth/change-password` antes de qualquer outra coisa — é o comportamento
correto e foi observado no fluxo do entregador.

## 3. Entregador (fluxo suportado)

### Provisionamento

```http
POST /api/v1/admin/drivers        (ADMIN do tenant, permissão user.create)
{"name": "Entregador Lab", "phone": "11999990000",
 "document": "MOTORISTA-HS-LAB-001", "username": "lab_entregador"}
```

`201` devolve `driver_id` e `temporary_password` (**única vez**).
O usuário é criado em `auth_users` com `must_change_password=true`.

### Login e operação

1. `POST /auth/login` com `{"username": "lab_entregador", "password": "<temporária>", "platform": "mobile"}`
   → `200`, `role = "DRIVER"`, `tenant_id` correto.
2. `POST /auth/change-password` (obrigatório antes de tudo — senão 403).
3. Rotas canônicas (montadas na **raiz**, sem `/api`):

| Método | Rota | O que faz |
|---|---|---|
| GET | `/driver/me` | perfil + `tracking_interval` |
| GET | `/driver/deliveries` | entregas atribuídas ao motorista |
| POST | `/driver/deliveries/{id}/accept` | aceita |
| POST | `/driver/deliveries/{id}/start` | inicia |
| POST | `/driver/deliveries/{id}/arrive` | chegou |
| POST | `/driver/deliveries/{id}/complete` | conclui |
| POST | `/driver/deliveries/{id}/fail` | falha com motivo |
| POST | `/driver/locations` | lote de posições (máx. 500) |
| GET | `/driver/locations/history` | histórico (exige permissão de localização) |

`GET /driver/me` respondeu `200` com `driver_id`, `tenant_id` e
`tracking_interval: 120` em execução real.

> O SPA também expõe o alias `/api/driver/*`. Use a raiz `/driver/*` em
> integrações: é o mesmo handler sem ambiguidade de prefixo.

## 4. Caminhos legados (não construir em cima)

| Rota | Autenticação | Situação |
|---|---|---|
| `POST /api/v1/driver/auth/login` | `driver_sessions` (JWT mobile próprio) | Rota "official v1", mas usa o login legado |
| `POST /api/driver/v1/auth/login` | idem | Marcada `[LEGACY]` no código |
| `POST /auth/mobile/login` | mini-JWT 15 min + refresh 7 d | Exige `delivery_drivers.username` **e** `password_hash` |
| `/api/v1/driver/*` | token de `driver_sessions` | **401** com token de sessão principal |

Por que o legado não serve para entregadores criados hoje:

1. `handle_driver_login` consulta o repositório com
   `tenant_id="default"` **fixo** → entregador de outro tenant não é
   encontrado (401).
2. `delivery_drivers.username`/`password_hash` **não** são preenchidos pelo
   `POST /api/v1/admin/drivers` canônico (o credencial vive em `auth_users`).
3. `/auth/mobile/login` depende exatamente desses dois campos → 401.

Nada disso bloqueia o app: o fluxo suportado é `POST /auth/login` + `/driver/*`.
Ver `FINDINGS.md` (R-3/R-4) para a decisão pendente.

## 5. Limites de taxa

Dois sistemas independentes:

**A. Por identidade, dentro do serviço de auth** (`auth_service.py`)

- `login:{username}` → **5 tentativas / 300 s**. É o limite que mais aparece
  em teste manual. Reiniciar o backend **não** limpa se o modo for Redis;
  no laboratório o contador é em memória por processo.

**B. Middleware HTTP** (`app/core/rate_limit.py`)

| Política | Limite |
|---|---|
| `login` | 5 / 300 s |
| `mutation` | 60 / 60 s |
| `read` | 120 / 60 s |
| `admin` | 30 / 60 s |
| `driver` | 30 / 60 s |
| `public` | 120 / 60 s |

Chave do bucket: `client_id` + **primeiro segmento do path**
(`/api/auth/login` → `IP:api`; `/auth/login` → `IP:auth`).

> **Achado R-5:** o mapa de políticas casa prefixos como `/auth/login` e
> `/orders` contra o path **completo**. Como o SPA chama `/api/...`, nenhuma
> política específica casa e tudo cai em `read` (120/min), num único bucket
> `IP:api` compartilhado por toda a API. Não é falha de segurança (o limite
> existe), mas o controle fino não está em vigor para `/api/*`.

`429` devolve `{"error": "Too many requests. Please try again later."}` com
`X-RateLimit-*` quando o backend é Redis.

## 6. O que fica bloqueado na borda

| Rota | Resultado na LAN |
|---|---|
| `/metrics` | `404` (Caddy não encaminha) |
| `/auth/me` sem token | `401` |
| `/driver/me` sem token | `401` |
| `/api/health`, `/ready` | `200` (públicos) |
