# Conectar o App do Entregador ao Home Server (LAN + HTTPS)

Este documento descreve a conexão **validada por execução** entre o app
Android (`mobile/`) e a pilha do Home Server em `https://192.168.0.211`.
O que ainda depende de ação manual está marcado como **pendência**.

> Resumo: o **servidor** está pronto e validado (login real, `/driver/*`
> ponta a ponta, certificado emitido pela CA interna). O **app** ainda precisa
> confiar na CA interna e ser instalado em um aparelho físico.

## 1. Estado atual

| Item | Situação |
|---|---|
| Servidor na LAN | `https://192.168.0.211` responde SPA + API |
| Certificado | válido para `192.168.0.211` (SAN IP) e `gasflow.home` (SAN DNS) |
| CA interna | `deploy/home-server/certs/gasflow-home-ca.crt` (10 anos) |
| Login do entregador | `POST /auth/login` → `200`, papel `DRIVER` |
| Rotas do app | `/driver/*` respondem `200` com a sessão principal |
| App Android | **não confia na CA ainda** (ver §4) |
| Aparelho físico | não disponível nesta execução (**pendência**) |

## 2. URL que o app deve usar

Digite na tela de login (ou grave no Keystore via `serverConfig`):

```
https://192.168.0.211
```

Sem barra no final. O `normalizeServerUrl` (`mobile/src/logic/serverConfig.ts`)
aceita `http(s)` e remove barras; a URL fica persistida no Keystore
(`gasflow.driver.server`).

- **Não** use `https://gasflow.home` sem antes resolver o nome (ver
  `docs/home-server/HOME_SERVER_NETWORK.md` §2). Sem DNS/hosts o app cai em
  `offline` porque o probe de `/health` falha.
- **Não** use `127.0.0.1` nem `localhost`: no celular isso aponta para o
  próprio aparelho.
- O `resolveConnection` testa `LAN → nuvem → offline` com probe de 3 s em
  `/health`. Com o IP correto e o celular na mesma rede, o modo é `lan`.

## 3. Contrato realmente exercitado

Tudo abaixo foi chamado contra a pilha de laboratório com HTTP real.

| Passo | Chamada | Resultado observado |
|---|---|---|
| 1 | `POST /auth/login` `{username, password, platform:"mobile"}` | `200`, `role=DRIVER`, `tenant_id` correto |
| 2 | `GET /auth/me` | `200`, `must_change_password` |
| 3 | `POST /auth/change-password` (se exigido) | `200`; sem isso, demais rotas dão `403` |
| 4 | `GET /driver/me` | `200`, `driver_id`, `tracking_interval` |
| 5 | `GET /driver/deliveries` | `200`, lista com `id`, `order_id`, `address` (objeto) |
| 6 | `POST /driver/deliveries/{id}/start` | `200` → `EN_ROUTE` |
| 7 | `POST /driver/deliveries/{id}/arrive` | `200` → `ARRIVED` |
| 8 | `POST /driver/deliveries/{id}/complete` | `200` → `DELIVERED` |
| 9 | Reenvio de `complete` com a mesma `idempotency_key` | `200 {"success":true,"idempotent_replay":true}` |
| 10 | `POST /driver/location` | `200` (1 ponto persistido) |
| 11 | `POST /driver/locations` (lote) | `200`, 2 pontos aceitos |

Detalhes importantes para o app:

- `GET /driver/deliveries` devolve o **registro cru** do backend. O
  `toDeliveryDTO` (`mobile/src/logic/api.ts`) normaliza `raw.id` →
  `delivery_id`, `raw.order_id` e `address` objeto → string. Já está correto;
  não mude o parser para esperar `delivery_id` na resposta.
- A cadeia de estados exige `arrive` antes de `complete`: concluir sem chegar
  responde `400`.
- `idempotency_key` é obrigatória nas ações; reenviar a mesma chave não
  duplica a transição.
- Sessões são persistidas em `auth_sessions`; reiniciar o backend não derruba
  o login.

O contrato completo (incluindo caminhos legados que **não** devem ser usados)
está em `docs/home-server/AUTH_CONTRACT.md`.

## 4. Confiança no certificado (pendência do app)

O `AndroidManifest.xml` atual tem:

```xml
android:usesCleartextTraffic="true"
```

e **não** tem `android:networkSecurityConfig`. Ou seja, o app foi construído
para o modo LAN em **HTTP**. Para usar HTTPS com a CA interna, é preciso:

1. Copiar o `gasflow-home-ca.crt` para `mobile/android/app/src/main/res/raw/`
   (ex.: `gasflow_home_ca.crt`).
2. Criar `mobile/android/app/src/main/res/xml/network_security_config.xml`:

   ```xml
   <?xml version="1.0" encoding="utf-8"?>
   <network-security-config>
     <domain-config cleartextTrafficPermitted="false">
       <domain includeSubdomains="false">192.168.0.211</domain>
       <domain includeSubdomains="false">gasflow.home</domain>
       <trust-anchors>
         <certificates src="@raw/gasflow_home_ca" />
         <certificates src="system" />
       </trust-anchors>
     </domain-config>
   </network-security-config>
   ```

3. Referenciar no `<application>`:
   `android:networkSecurityConfig="@xml/network_security_config"`.
4. Manter `usesCleartextTraffic="true"` **somente** se o modo LAN HTTP ainda
   for suportado; caso contrário, remova o flag e deixe o
   `cleartextTrafficPermitted="false"`.
5. Rebuild do APK e instalação em aparelho físico.

**Não** desative a validação de certificado (`TrustManager` que aceita tudo,
`hostnameVerifier` que retorna `true`). Isso anula o ganho do HTTPS e não é
aceitável nem em laboratório.

Enquanto o passo 2 não existir, o app em HTTPS falha com erro de certificado;
em HTTP ele funciona, mas sem TLS. A recomendação é concluir o passo 2 antes
de qualquer demonstração.

### Instalar a CA no aparelho (alternativa/complemento)

Instalar a CA em *Configurações → Segurança → Instalar certificado → CA* faz o
**navegador** confiar no certificado. No Android 7+, apps **não** confiam
automaticamente em CAs instaladas pelo usuário: por isso o
`network_security_config` continua necessário para o app.

## 5. Checklist da Fase 2 (quando houver aparelho)

- [ ] Confirmar `https://192.168.0.211/api/health` no navegador do celular
      (com a CA instalada, sem aviso).
- [ ] Aplicar o `network_security_config` e rebuildar o APK.
- [ ] Instalar o APK e digitar `https://192.168.0.211` na tela de login.
- [ ] Login com `lab_entregador` (senha trocada no primeiro acesso).
- [ ] Aceitar/iniciar/chegar/concluir a entrega `000002` (hoje `ASSIGNED`).
- [ ] Verificar no servidor: `delivery_records` da entrega muda para
      `DELIVERED` e `driver_locations` recebe pontos.
- [ ] Testar modo avião / fora da LAN: o app deve cair em `offline` e enfileirar,
      não travar.

## 6. Limitações conhecidas

| Limitação | Impacto | Contorno |
|---|---|---|
| App não confia na CA interna | HTTPS falha no app | §4 (network security config) |
| Sem aparelho físico nesta execução | Fase 2 não validada no device | checklist §5 |
| IP por DHCP (`192.168.0.211`) | IP pode mudar após reboot do roteador | reserva de DHCP recomendada |
| `gasflow.home` sem DNS | nome não resolve | usar IP ou criar host override |
| Wi-Fi no perfil Público do Windows | firewall pode bloquear | regra 443 restrita à sub-rede (ver `HOME_SERVER_NETWORK.md` §5) |

## 7. Re-verificação de 04/11/2026 (execução atual)

Tudo abaixo foi medido de novo nesta execução, sem alterar a pilha:

| Verificação | Comando real | Resultado |
|---|---|---|
| Serviços | `docker compose ... ps` | **6/6 healthy** |
| HTTPS pela LAN | `verify_lan_https.py --base https://192.168.0.211` | **9 ok / 0 falhas**, CA validada |
| Cadeia TLS | `openssl s_client -CAfile .../gasflow-home-ca.crt` | `Verify return code: 0 (ok)` |
| SAN | handshake com SNI | IP `192.168.0.211` e `DNS:gasflow.home` |
| Login | `POST /auth/login` (admin) | `200`; `/api/dashboard` `200` |
| Resiliência | `verify_resilience.py` | redis/frontend/caddy/postgres voltam; sessão e `5/4/1/6` preservados |
| Backup/restore | `verify_backup_restore.sh` | 69/299/113, `alembic a4b5c6d7e8f9`, **0 divergências** |
| Isolamento | WhatsApp | `WA_SEND_MODE=dry-run`, `WA_BROADCAST_ENABLED=false` |

A URL de conexão do app permanece `https://192.168.0.211` e o endpoint de
login do entregador é `POST /auth/login` com `platform: "mobile"`.
O caminho legado `/auth/mobile/login` continua **inutilizável** para entregador
novo (R-3, decisão pendente) e não deve ser usado pelo app.
