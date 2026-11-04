# FINAL — Plano de Integração dos Pull Requests

**Data:** 31/10/2026
**Branch de destino:** `main` (HEAD remoto `2946e59`)
**Autor:** consolidação técnica (Buffy) — nada foi mesclado; nenhuma `main` foi alterada.

---

## 1. PRs existentes

| PR | Branch de origem | Base | Commits | Arquivos | Escopo |
|---|---|---|---|---|---|
| #80 | `fix/security-body-parser-cve` | `main` | 1 | 1 | CVE-2026-111181 (`body-parser` 2.3.0 → 2.4.0) |
| #74 | `fix/sec-01-tenant-isolation` | `main` | 2 | 9 | Isolamento multitenant + autorização de plataforma |
| #75 | `sec-02-whatsapp-gateway` | `main` | 5 | 36 | Auth do gateway WhatsApp (SEC-02) + prep. Home Server + relatório de prontidão |
| #76 | `parallel/freebuff-infra` | `main` | 6 | 48 | Perfil Docker isolado do Home Server + teste de prontidão |
| #77 | `parallel/freebuff-mobile-p0` | `main` | 7 | 58 | P0 mobile (conclusão de entrega + URL do Home Server) |
| #78 | `parallel/opencode-data` | `main` | 10 | 52 | Ferramentas de dados/migração (OPS-01D) |
| #79 | `release/home-server-candidate` | `main` | 27 | 100 | Integração final (superset de #74–#78 + 12 commits novos) |

`git cherry -v origin/main <branch>` marca **todos** os commits como exclusivos (`+`), inclusive os
recriados em #79: os patch-ids diferem. **A duplicidade é real para o Git**, mesmo quando o conteúdo
é equivalente — este documento não a trata como inofensiva.

## 2. Commits compartilhados literalmente (mesmo SHA em todas as branches)

`d135caf` · `656d2de` · `544dca6` · `213c187`

São a base de #74, #75, #76, #77, #78 e #79. Mesclar #74/#75 antes de #79 **não reaplica** nada.

## 3. Commits exclusivos por PR

| PR | Commits exclusivos |
|---|---|
| #74 | `d135caf`, `656d2de` |
| #75 | `544dca6`, `213c187`, `bc41c68` (relatório de prontidão) |
| #76 | `28c7ff3`, `36b6fa8` |
| #77 | `92e3d50` |
| #78 | `971de40`, `9c46d1a`, `9a7a431`, `11fb254`, `23ca079`, `d256ac6` |
| #79 | `7bb5250`, `e3c6bd8`, `71e9467`, `0f3b00b`, `c683887`, `0792113`, `aa7e8da`, `6a15490`, `ebaf84e`, `ea01508`, `e989f70`, `cfbd564`, `117805e`, `d1be43e`, `b54c2c1`, `16bbc72`, `e108274`, `6f607ab`, `5d2ef41`, `db0a0df`, `edf1005`, `9707dc1`, `eecd1dc` |

## 4. Duplicados por conteúdo (hash diferente, mesma alteração)

| Original | Recriado em #79 | Conteúdo |
|---|---|---|
| `28c7ff3` | `7bb5250` | perfil Docker do Home Server |
| `36b6fa8` | `e3c6bd8` | teste de prontidão de release |
| `92e3d50` | `71e9467` | P0 mobile |
| `971de40` | `0f3b00b` | draft de tooling OPS-01D |
| `9c46d1a` | `c683887` | leitura read-only da origem |
| `9a7a431` | `0792113` | ensaio de migração SQLite |
| `11fb254` | `aa7e8da` | docs de migração |
| `23ca079` | `6a15490` | teste de backup/restore |
| `d256ac6` | `ebaf84e` | backup/recuperação PostgreSQL |

## 5. Evidência de conflito (medida, não presumida)

Simulação não destrutiva com `git merge-tree` (`release/home-server-candidate` × cada branch):

| Par | Conflitos | Arquivos em conflito |
|---|---|---|
| #76 × #79 | **SIM** | `deploy/home-server/.env.lab.example`, `README.md`, `verify-static.sh`, `docker-compose.homeserver.lab.yml`, `docs/delivery/PENDENCIAS_BLOQUEANTES.md`, `backend/tests/test_ops01b_homeserver_profile.py`, `test_delivery_readiness_mobile_contracts.py` |
| #77 × #79 | **SIM** | os mesmos acima + `mobile/src/containers/wired.tsx` |
| #78 × #79 | não | — |

Deleções provocadas por #79 em relação a #76/#77/#78: **0 arquivos** (`git diff --diff-filter=D`).
Ou seja, #79 **não perde** nenhuma contribuição das branches anteriores.

## 6. Estratégia escolhida — híbrida (Opção B até #78, Opção C para o topo)

1. **#80 é independente** e deve ser integrado primeiro: corrige a vulnerabilidade HIGH que reprova o
   check Trivy de **todos** os PRs, inclusive #74 (cujo diff só toca `backend/`, provando origem
   pré-existente na `main`).
2. **#74 e #75 são ancestrais literais de #79** (mesmos SHAs) → merge limpo, preservam a revisão em
   camadas.
3. **#78 mescla sem conflito** com #79 → pode entrar antes.
4. **#79 é o PR canônico do restante** (infra + mobile + dados + 12 commits finais). Seus commits
   recriados tornam insegura a mesclagem prévia de #76/#77, que conflitam por conteúdo já presente.
5. **#76 e #77 ficam como superseded por #79** — branches preservadas, sem fechar nada até a
   integração autorizada de #79, com justificativa registrada no PR.

### Ordem de revisão e merge

```
#80  (segurança/CVE)      → primeiro, independente
#74  (tenant isolation)   → ancestrais de #79
#75  (WhatsApp gateway)   → ancestrais de #79
#78  (dados/migração)     → sem conflito com #79
#79  (integração final)   → último; absorve #76 e #77
```

Após cada merge autorizado: `git fetch origin`, atualizar as branches restantes com
`git merge origin/main` (nunca rebase/force push), reexecutar checks e conferir o diff antes de seguir.

## 7. Justificativa: manter ou consolidar

| PR | Decisão | Justificativa |
|---|---|---|
| #80 | manter e integrar primeiro | escopo isolado, remove bloqueio de segurança de todos os checks |
| #74 | manter | escopo coeso de segurança, sem duplicidade |
| #75 | manter | escopo coeso do gateway, sem duplicidade |
| #78 | manter | mescla limpa com #79, escopo de dados |
| #76 | manter aberto, marcar superseded | conteúdo integralmente presente em #79; conflito se mesclado antes |
| #77 | manter aberto, marcar superseded | idem; evolução do mobile está em #79, incluindo `queuePersistence` |
| #79 | manter como canônico | superset verificado (0 deleções) com os 12 commits finais e `eecd1dc` |

Nenhuma branch é apagada; nenhum histórico é reescrito; nenhum force push.

## 8. Riscos

| Risco | Mitigação |
|---|---|
| #79 reaplicar trabalho de #76/#77 em duplicidade textual | merge de #79 é limpo se #76/#77 não forem mesclados antes (medido com `merge-tree`) |
| #76/#77 ficarem “esquecidos” abertos | comentário de superseded + branches preservadas + conteúdo verificável em #79 |
| Trivy vermelho em #74–#78 após o merge de #80 | atualizar cada branch a partir da `main` antes do merge |
| Divergência futura de `main` durante a sequência | `git fetch` + update de branch + checks a cada merge autorizado |
| Revisão perder granularidade | PRs #74/#75/#78 continuam revisáveis isoladamente |

## 9. Pré-requisitos para autorizar cada merge

- Todos os checks obrigatórios verdes (após #80 e do update de branch).
- Sem vulnerabilidade HIGH sem tratamento.
- Sem conflito (`mergeable: MERGEABLE`).
- Sem perda de trabalho (0 deleções verificadas).
- Rollback descrito no PR (`FINAL_ROLLBACK_PLAN.md`).
