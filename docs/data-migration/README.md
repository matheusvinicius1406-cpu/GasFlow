# Migração de dados — OPS-01D (Home Server)

Ferramentas de **laboratório** para proteger, copiar, verificar e ensaiar a
migração dos dados do GasFlow (SQLite legado → schema atual, com horizonte
PostgreSQL). Nada aqui autoriza migração de produção — ver a tabela de
classificação ao final.

## Invariantes (política — inegociável)

1. **A origem nunca é modificada.** Toda leitura usa `common.open_readonly`
   (modo de somente leitura + immutable quando seguro). Não existe fallback de
   escrita; sidecars (`-wal`/`-shm`) nunca são criados na origem.
2. **Relatórios existentes nunca são sobrescritos.** `--report` em arquivo já
   existente é recusado (código 2).
3. **Dados sempre sintéticos** nos ensaios (`synthetic.create_source_db`).
   O banco real de produção (`C:\gf\backend\gasflow.db`) é intocável.
4. **Dry-run por padrão.** Sem `--execute`, nada é gravado.
5. **Alvo novo é obrigatório.** Arquivo de destino precisa ser inexistente ou
   conter o marcador `_ops01d_run` desta ferramenta com a MESMA origem
   (reconciliação idempotente). Sobrescrita silenciosa não existe.

## Ferramentas (`scripts/home-server/data/`)

| Script | Papel |
| --- | --- |
| `common.py` | Utilitários: `open_readonly` (fail-closed), `guard_report_path`, `write_json`, fingerprint (sha256), códigos de saída. |
| `db_diagnose.py` | Diagnóstico somente-leitura da origem: assinatura do banco, journal/WAL, integridade, sidecars. |
| `db_backup.py` | Backup consistente (`sqlite3.Connection.backup`) com sha256 + verificação de integridade do backup. |
| `db_verify.py` | Verificação de backup (hash, integridade, comparação com a origem) + ensaio de restauração (drill) em diretório temporário. |
| `db_restore.py` | Restauração de backup em ambiente isolado, verificando o manifesto antes; dry-run por padrão. |
| `migrate_rehearsal.py` | Ensaio de migração para o schema atual: planejamento, validação linha a linha, carga transacional no alvo novo, conferências e marcador de execução. |
| `mapping.py` | Mapeamento declarativo (tabelas puladas/bloqueadas, ledgers imutáveis, chaves de negócio) — fonte de verdade executável; documentado em `mapping.md`. |
| `synthetic.py` | Fixtures sintéticas do schema legado para os ensaios. |
| `pg_backup.py` / `pg_restore.py` | Preparação da fase PostgreSQL (com mocks; sem credenciais embutidas). |

## Códigos de saída (todas as ferramentas)

| Código | Significado |
| --- | --- |
| 0 | sucesso |
| 1 | falha (ex.: ensaio abortado, alvo removido) |
| 2 | segurança (origem/alvo/relatório protegidos; nada gravado) |
| 3 | migração **parcial** — concluída, mas com bloqueios registrados no relatório |

## Fluxo típico (laboratório)

```text
1. db_diagnose.py   --source legacy.db --report diag.json
2. db_backup.py     --source legacy.db --dest backup.db --report backup.json
3. db_verify.py     --backup backup.db --source legacy.db --drill --report verify.json
4. db_restore.py    --backup backup.db --dest restored.db --report restore.json   # dry-run
   db_restore.py    --backup backup.db --dest restored.db --execute --report restore.json
5. migrate_rehearsal.py --source legacy.db --target target.db --report dry.json           # dry-run
   migrate_rehearsal.py --source legacy.db --target target.db --execute --report run.json
6. migrate_rehearsal.py --source legacy.db --target target.db --execute --report again.json  # reconciliação
```

## `migrate_rehearsal.py` — detalhes

* **Dry-run (padrão):** planeja, valida tudo, escreve relatório; não cria o
  alvo nem o diretório pai.
* **`--execute`:** cria o alvo novo com o schema atual (`create_all`), carrega
  as linhas aceitas em **uma única transação**, e dentro dela: executa
  `PRAGMA foreign_key_check`, confere contagens (origem aceita × destino),
  confere somas das colunas financeiras (`orders`, `order_items`, `payments`,
  `receivables`, `financial_ledger`) e grava o marcador `_ops01d_run`. Falha em
  qualquer etapa → rollback e **remoção do arquivo de alvo** criado nesta
  execução (nunca toca a origem).
* **Reexecução (idempotência):** alvo existente com marcador válido e a MESMA
  origem (fingerprint size+sha256) ativa **reconciliação somente-leitura**:
  revalida e reconfere sem gravar nada. Origem diferente → bloqueado (código 2).
* **`--strict`:** qualquer bloqueio impede a gravação (fail-closed) e o
  relatório sai como `strict-blocked`.
* **`--null-tenant`:** `block` (padrão, segura a linha) ou `platform`
  (preenche `tenant_id` com o valor documentado; só com flag explícita).
* **`--allow-unknown-source`:** prossegue sem reconhecer a assinatura do banco
  (o banco do serviço WhatsApp é sempre recusado).
* Relatório: JSON completo — planos por tabela, bloqueios, issues por linha
  (sem dados pessoais: só tabela/PK/coluna/regra), ordem de carga, contagens,
  verification em execute. O relatório **nunca** contém valores de colunas
  sensíveis (nomes, telefones etc.) — apenas agregados financeiros na
  conferência.

## Fase PostgreSQL (em preparação — NÃO executada)

* `pg_backup.py` / `pg_restore.py` são wrappers com mocks: cobrem CLI,
  validação de entrada, sem senha no ambiente por padrão (`PGPASSWORD` não é
  default), e fluxo de manifesto. Eles **não** operam um PostgreSQL real ainda.
* O alvo `postgresql://` do `migrate_rehearsal.py` é recusado nesta fase.
* A conversão SQLite→PostgreSQL (tipos, `SERIAL`/`BIGSERIAL`, defaults,
  collations) fica para a fase de integração — dependência registrada aqui.

## Classificação (não confundir)

| Situação | Estado |
| --- | --- |
| Ferramentas de backup/verificação/restauração/ensaio desenvolvidas | ✅ nesta fase |
| Testes isolados (sintéticos, temporário) passando | ✅ nesta fase |
| Migração SQLite→PostgreSQL validada em laboratório | ❌ não realizada |
| Migração de produção autorizada | ❌ não autorizada |

## Testes

`backend/tests/test_ops01d_*.py` — rodam com o resto da suíte
(`python -m pytest tests/ -q` em `backend/`), isolados em diretórios
temporários; nunca abrem o banco real. O mapeamento é validado contra o schema
atual pelo `test_ops01d_mapping` (se o schema mudar, `mapping.py` e este
diretório precisam mudar junto).
