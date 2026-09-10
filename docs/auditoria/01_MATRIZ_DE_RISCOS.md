# 01 · Matriz de Riscos

Consolidação de todos os achados (IDs referenciam os arquivos por área). Ordenado por severidade.

| ID | Achado | Área | Severidade | Impacto | Esforço | Status |
|---|---|---|---|---|---|---|
| P-1 | 36 arquivos não commitados (segurança + fixes + auto-update + docs) | Processo | 🔴 P0 | Perda de trabalho; push de outra máquina não leva nada | 30 min | **Aberto** |
| P-2 | `desktop/dist/` não versionado → CI de release empacotaria placeholder | Processo | 🔴 P0 | Release via CI geraria app sem main process | 10 min | Fix aplicado (validar no commit) |
| D-2 | Ponte IPC dormente (preload nunca carregado, 0 handlers) | Desktop | 🔴 P0 p/ auto-update | `window.gasflow*` nunca existiu no renderer; UpdateNotifier dependeria disso | já mitigado no dist | Mitigado (validar E2E) |
| D-1 | Fontes do main process não existem (só dist compilado) | Desktop | 🔴 P0 sustentação | Mudanças no main = editar JS à mão, sem typecheck | 1–2 dias | Aberto |
| P-3 | Sem `release.yml`; permissão de escrita no repo não confirmada | CI/CD | 🟠 P1 | Auto-update sem CI = releases manuais para sempre | 1 h | Aberto |
| D-3 | Build local não gera `latest.yml`; auto-update não validado em release | Desktop | 🟠 P1 | Updater não encontra manifest → sem detecção de update | 30 min | Aberto |
| W-1 | Auto-recovery `logged_out` sem validação E2E (QR → desconexão → QR) | WhatsApp | 🟠 P1 | Correção do loop de desconexão não provada em campo | 30 min + usuário | Aberto |
| E2E-1 | Playwright (7 specs) sem execução garantida no CI | Testes | 🟠 P1 | Regressões de UI chegam ao app instalado | 1 h | Aberto |
| B-1 | 2 resíduos ruff (F841 `start_time`, F401 `TA_RIGHT`) quebram o CI | Backend | 🟡 P2 | Push será barrado no job de lint | 5 min | Aberto |
| B-4 | pytest `drop_all` no banco dev (`conftest.py:40`) | Backend | 🟡 P2 | Dev perde dados locais ao rodar testes | 30 min | Aberto |
| D-5 | `waEnabled: false` ignorado no boot | Desktop | 🟡 P2 | Usuário desativa WhatsApp e serviço segue rodando | 15 min | Aberto |
| D-4 | `desktop/tests/` vazio (verde falso) | Desktop | 🟡 P2 | Nenhum teste do main process | 2 h | Aberto |
| DOC-1 | 6 docs citam wwebjs como motor atual | Docs | 🟡 P2 | Confunde manutenção | 30 min | Aberto |
| DOC-2 | README desktop sem auto-update/migration/waEnabled | Docs | 🟡 P2 | Suporte mais difícil | 20 min | Aberto |
| B-2 | mypy 528 erros (sem baseline) | Backend | 🟢 P3 | Refactor guiado só por testes | dias | Diferido |
| B-3 | vulture 13 parâmetros de interface | Backend | 🟢 P3 | Cosmético | 30 min | Diferido |
| 19 funções C90>10 | Complexidade (pior: `import_service.test_connection` = 20) | Backend | 🟢 P3 | Manutenibilidade | gradual | Diferido |
| 25 `except: pass` | Erros engolidos (triagem pendente) | Backend | 🟢 P3 | Debugging difícil em produção | 1 dia | Diferido |

## Mapa de calor

| Domínio | 🔴 | 🟠 | 🟡 | 🟢 |
|---|---|---|---|---|
| Processo/CI-CD | 2 | 1 | — | 1 ✅ |
| Desktop | 2 | 1 | 2 | — |
| Backend | — | — | 2 | 3 |
| WhatsApp | — | 1 | — | 2 ✅ |
| Frontend | — | — | — | 1 ✅ |
| Docs/Testes | — | 1 | 3 | — |

**Leitura:** o risco concentrado está em **Processo (salvar o trabalho / permitir release via CI)** e **Desktop (fontes ausentes)**. As áreas de negócio (backend, WhatsApp, frontend) estão verdes após as correções da semana.
