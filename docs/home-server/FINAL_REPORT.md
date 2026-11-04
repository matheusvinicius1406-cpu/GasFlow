# Relatório final — GasFlow Home Server (LAN, HTTPS, R$ 0,00)

**Data:** 04/11/2026 · **Worktree:** `GasFlow-integration` ·
**Branch:** `release/home-server-candidate` · **HEAD de código:** `9eefac6`
**Escopo:** servidor doméstico na LAN + conexão do app Android, sem custo de
licença e sem exposição à internet.

Este relatório responde às 20 perguntas da missão com o que foi **executado e
medido**, não com intenção. Evidências brutas em `evidence/`; operação em
`README.md`, `OPERATIONS.md`, `HOME_SERVER_NETWORK.md` e `FINDINGS.md`.

---

## Resumo executivo

O Home Server está **no ar e saudável (6/6 containers)**, acessível em
`https://192.168.0.211` com certificado da CA interna validado, WhatsApp em
`dry-run` e backup/restore comprovado. As correções de isolamento por tenant e
de autenticação do entregador estão **na imagem em execução** desde
`04/11 12:51Z`.

O que **não** está concluído: o app Android ainda não confia na CA interna
(falta `network_security_config`), não há aparelho físico para a Fase 2, o
backup continua no mesmo disco (`off_host=false`), o Wi-Fi está no perfil
Público e o PR #79 segue com o check Trivy vermelho — portanto **não houve e
não deve haver merge na `main`**.

---

## 1. O que foi entregue nesta missão?

Uma pilha Docker completa rodando no PC da empresa, restrita à LAN:

| Serviço | Papel | Porta no host |
|---|---|---|
| postgres 16 | dados | nenhuma |
| redis 7 | rate limit / pub-sub | nenhuma |
| backend (FastAPI) | API + Alembic | nenhuma (`8000/tcp` interna) |
| frontend (nginx) | SPA + proxy | `127.0.0.1:8088` |
| whatsapp (Baileys) | automação em `dry-run` | nenhuma |
| caddy 2 | única borda TLS | `192.168.0.211:443` e `127.0.0.1:443` |

Além disso: scripts de verificação (`scripts/home-server/`), documentação
operacional (`docs/home-server/`), contrato do app
(`docs/mobile/HOME_SERVER_MOBILE_CONNECTION.md`), dados sintéticos de
laboratório e as correções R-6/R-7/R-8 com testes.

## 2. O servidor está no ar agora?

Sim. `docker compose ps` mostra **6/6 containers `healthy`** (evidência
`evidence/00_STACK.txt`). O backend responde `/api/health` e `/ready` com
`200`; o Caddy é a única borda publicada.

## 3. Qual endereço devo usar?

`https://192.168.0.211` (SPA e API). O IP vem de `GASFLOW_LAN_IP` no
`deploy/home-server/.env.lab` e é **DHCP** — recomenda-se reserva no roteador.
`https://gasflow.home` funcionaria com DNS/hosts, mas não resolve hoje.

## 4. O HTTPS funciona e é confiável?

Sim. `verify_lan_https.py` executou **9 checagens com a CA interna validada e
0 falhas** (`evidence/06_HTTPS.txt`): SPA, `/api/health`, `/ready`,
`/api/v1/health`, `/auth/me` 401, `/driver/me` 401, `/metrics` 404, login
admin e `/api/dashboard` autenticado. O certificado tem SAN para
`192.168.0.211` e `gasflow.home`, emitido pela CA local válida até 2036.

## 5. Por que `gasflow.home` não abre?

Porque o nome não é DNS público e não há *host override* no roteador nem
`hosts` no cliente. O verificador trata isso como **AVISO**, não falha. Para
usar o nome: criar override no DNS do roteador ou entrada `hosts`; no Android,
o caminho é DNS do roteador (não há `/etc/hosts` sem root).

## 6. O servidor está exposto à internet?

Não. O Caddy publica **somente** em `192.168.0.211:443` e `127.0.0.1:443`
(nenhum `0.0.0.0`), não há *port forwarding* nem regra de firewall global.
`/metrics` é bloqueado na borda (`404`). O único acesso externo possível é a
própria LAN.

## 7. Quais dados existem? Vieram da operação real?

Não. O laboratório usa o tenant sintético `gasflow_home_server_lab`
(`evidence/02_LAB_TENANT.txt`): 4 memberships, 3 clientes, 4 pedidos,
4 itens, 6 produtos, 4 registros de estoque e 1 entregador. **Nenhum dado
operacional da Marcos Gás foi copiado ou migrado**; o SQLite operacional não
foi tocado.

## 8. O isolamento por tenant foi corrigido?

Sim. R-6 (itens de pedido) e R-7 (estoque) gravavam sem `tenant_id` e caíam em
`default`. As correções passam o tenant explícito no insert e no `UPDATE`
atômico. A imagem em execução contém as duas correções
(`evidence/IMAGE_IDENTITY.txt`) e os testes
`test_order_item_tenant_isolation.py` + a suíte de estoque passam.

## 9. O login do entregador é seguro?

O bypass R-8 foi corrigido no código e **implantado**: quando
`password_hash` é vazio, o login falha fechado (`401`) em `/auth/mobile/login`
e no legado `/api/v1/driver/auth/login`. A imagem anterior
(`sha256:0c7373b5…`) ainda tinha o código vulnerável; foi reconstruída e o
container recriado em `04/11 12:51Z` com `sha256:ce593188…`, verificado por
inspeção (`stored_hash` presente nos dois arquivos). Testes: 2 passed.

## 10. O app Android já conecta?

Parcialmente. O **servidor** está pronto e o contrato `/auth/login` +
`/driver/*` foi exercitado com HTTP real. O **app** ainda:
- não confia na CA interna (manifest com `usesCleartextTraffic="true"` e sem
  `networkSecurityConfig`);
- não foi instalado em aparelho físico nesta execução.

Ou seja: funciona em HTTP; para HTTPS falta o passo descrito em
`docs/mobile/HOME_SERVER_MOBILE_CONNECTION.md` §4. **Não** se deve desativar a
validação de certificado como atalho.

## 11. Quais endpoints o app usa?

Fluxo suportado (raiz, sem `/api`):

| Método | Rota |
|---|---|
| POST | `/auth/login` (`platform: "mobile"`) |
| GET | `/auth/me` |
| POST | `/auth/change-password` |
| GET | `/driver/me` |
| GET | `/driver/deliveries` |
| POST | `/driver/deliveries/{id}/accept|start|arrive|complete|fail` |
| POST | `/driver/location` |
| POST | `/driver/locations` (lote) |
| GET | `/driver/locations/history` |

`/driver/deliveries` devolve o registro cru (`id`, `order_id`, `address`
objeto); o `toDeliveryDTO` do app já normaliza. Os caminhos legados
(`/auth/mobile/login`, `/api/v1/driver/*`) **não** devem ser usados.

## 12. O fluxo de entrega foi testado ponta a ponta?

Sim, duas vezes: a entrega `000001`
(`7cbbec1a-11de-4de3-98ee-2bdeeeb13266`) percorreu
`start → arrive → complete` com `200` e terminou `DELIVERED` (version 5,
prova `PHOTO`); o reenvio de `complete` com a mesma chave devolveu
`200 {"success":true,"idempotent_replay":true}`. A entrega `000002`
(`1425fe7b-15d3-4755-b21b-b93f50a4f046`) permanece `ASSIGNED` (version 2)
para a validação no aparelho.

## 13. O GPS/rastreamento funciona?

Sim no servidor: `POST /driver/location` devolveu `200` e o lote
`POST /driver/locations` aceitou 2 pontos; `driver_locations` tem 1 linha
persistida (o ingest aplica *throttle*/janela de trabalho). O rastreamento no
aparelho depende da Fase 2 e das permissões de localização.

## 14. O WhatsApp está enviando mensagem?

Não, por decisão. `WA_SEND_MODE=dry-run`, `WA_BROADCAST_ENABLED=false`, sem
porta publicada, sem arquivo de sessão e sem pareamento
(`evidence/03_WHATSAPP.txt`). `/metrics` responde `401` sem token. Nenhuma
mensagem real foi enviada.

## 15. O backup existe e foi restaurado de verdade?

Sim. A execução `20261104T125554Z` gerou dump custom de **240.467 bytes**
(SHA-256 `a990eeed…305f4b`), criou um banco descartável, restaurou com
`pg_restore --exit-on-error` e comparou: **69 tabelas, 299 índices,
113 constraints, `alembic_version a4b5c6d7e8f9`, 0 divergências**. O banco
descartável foi removido.

**Limitação:** o host tem um disco só, então o manifest registra
`"off_host": false`. Isso protege contra erro de operação, não contra perda do
disco.

## 16. O sistema aguenta reinício de serviços?

Sim. `verify_resilience.py` reiniciou cada serviço e a pilha voltou sozinha:
redis **8 s**, frontend **10 s**, caddy **17 s**, postgres **23 s**. Houve o
`500` transitório esperado após o restart do Postgres, recuperado em **3 s**;
sessão e dados (`5/4/1/6` clientes/pedidos/entregadores/usuários) sobreviveram
(`evidence/09_RESILIENCE.txt`).

## 17. Quais testes foram executados?

| Escopo | Comando | Resultado |
|---|---|---|
| Backend direcionado | 6 arquivos (auth, tenant, driver, gate, perfil) | **70 passed**, 0 failed |
| Backend — gate/perfil | `pytest tests/test_ops01d… test_ops01b… test_prod_stack…` | **54 passed** (`07_TESTS.txt`) |
| Backend — auth/tenant | `pytest test_driver_login… test_order_item… test_driver_mobile…` | **16 passed** (`08_TESTS_DRIVER_AUTH.txt`) |
| Lint backend | `ruff check` nos 6 arquivos alterados | **All checks passed** |
| Mobile | `npm test` | **101 passed**, 0 failed (`09/09` suítes) |
| Mobile typecheck | `tsc --noEmit` | **exit 0** |

A suíte completa histórica do backend (2552 passed) não foi repetida nesta
execução; os 70 testes direcionados cobrem exatamente os arquivos alterados e
os gates do Home Server.

## 18. O código está commitado e publicado?

As alterações desta missão estão na branch `release/home-server-candidate`
(worktree `GasFlow-integration`) e serão publicadas no PR **#79**. O PR está
`OPEN`, `mergeable=MERGEABLE`, `mergeStateStatus=UNSTABLE`; **somente o Trivy
falha**. Não houve merge na `main`, force-push, reset, `clean`, remoção de
worktree ou de volume.

- Commit desta entrega: `55721ed` (`feat(home-server): LAN HTTPS stack,
  lab evidence and tenant/driver-auth fixes`); o HEAD anterior era `9eefac6`.
- Worktrees `GasFlow`, `GasFlow-freebuff`, `GasFlow-opencode` e
  `GasFlow-integration`: **preservados**.

## 19. Este PC aguenta operar isso continuamente?

Com ressalvas. O host é um i3-10110U (2C/4T), 12 GB de RAM e **HDD 5400 rpm**.
A pilha roda, mas a auditoria OPS-00B não recomenda o conjunto completo como
serviço de produção contínuo nesse hardware. O perfil atual é **laboratório
estável**, não produção. Para produção: SSD, host dedicado e backup off-host.

## 20. Riscos, limitações e próximo passo

**Bloqueadores / limitações:**

| Item | Impacto | Ação |
|---|---|---|
| App sem `networkSecurityConfig` | HTTPS falha no app | implementar §4 e rebuildar o APK |
| Sem aparelho físico | Fase 2 não validada | executar checklist §5 |
| `off_host=false` | perda do disco perde dados e backup | HD externo/NAS + `--confirm-off-host` |
| IP DHCP | troca de IP quebra URL/certificado | reserva de DHCP |
| Wi-Fi perfil Público | firewall pode bloquear | regra 443 restrita à sub-rede (requer admin) |
| `gasflow.home` sem DNS | nome não resolve | override no roteador |
| Trivy vermelho no PR #79 | merge bloqueado | corrigir CVEs antes do merge |
| HDD/2 núcleos | I/O e latência | SSD/host dedicado para produção |

**Riscos residuais:** R-3 (login mobile legado inutilizável para entregador
novo — decisão pendente), R-4 (três superfícies de entregador), R-5 (rate
limit não casa `/api/*`), R-9 (500 pontual após restart do Postgres — aceito),
R-10 (backup no mesmo disco), R-11 (produtos duplicados no laboratório).

**Próximo passo (ordem recomendada):**

1. Implementar o `network_security_config` no app e gerar novo APK.
2. Validar a entrega `000002` em aparelho físico na LAN.
3. Reservar o IP `192.168.0.211` no roteador.
4. Copiar o dump para destino off-host e rodar o gate com
   `--confirm-off-host`.
5. Corrigir o Trivy e só então avaliar o merge do PR #79.

---

## Critérios de aceite

| Critério | Status |
|---|---|
| Pilha 6/6 saudável | **Atingido** |
| HTTPS com CA interna validada | **Atingido** (9/9) |
| Acesso apenas pela LAN | **Atingido** |
| WhatsApp sem envio/pareamento | **Atingido** |
| Dados reais intocados | **Atingido** |
| Isolamento por tenant | **Atingido** (R-6/R-7 na imagem) |
| Login de entregador sem bypass | **Atingido** (R-8 na imagem) |
| Backup + restore independente | **Atingido** (69/299/113, 0 divergências) |
| Resiliência a restart | **Atingido** |
| App Android em HTTPS no aparelho | **Pendente** (CA/APK) |
| Backup off-host | **Pendente** (um disco) |
| PR #79 verde e pronto para merge | **Pendente** (Trivy) |
