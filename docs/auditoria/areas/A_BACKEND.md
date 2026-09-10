# Achados por área — Backend (FastAPI/Python, 254 arquivos)

## B-1 · F841/F401 resíduos das edições da semana

**Severidade:** 🟡 P2 · **Arquivo:** `app/application/whatsapp/gateway.py:134`, `app/infrastructure/pdf/daily_report.py:73`

**Evidência:**
```
ruff check app --select F401,F841 →
  gateway.py:134:9: F841 start_time assigned but never used
  daily_report.py:73:52: F401 TA_RIGHT imported but unused
```

**Impacto:** `start_time` ficou órfão quando a métrica de latência foi removida na limpeza; `TA_RIGHT` sobrou da remoção dos estilos não usados. CI roda `ruff check app tests` — **o push vai falhar** se esses 2 não saírem.

**Ação:** remover a atribuição e o import (2 min, antes do primeiro push).

## B-2 · mypy: 528 erros em 52 arquivos (baseline ausente)

**Severidade:** 🟢 P3 · **Evidência:** `mypy app --explicit-package-bases → Found 528 errors in 52 files`

**Impacto:** sem tipagem estrita, refatorações dependem só de testes (que estão bons: 1331 passando).

**Ação:** introduzir `mypy.ini` com baseline congelado + regra "só erros novos quebram CI". Correção em massa não é recomendada.

## B-3 · vulture: 13 variáveis "unused" de 100% — parâmetros de interface

**Severidade:** 🟢 P3 · **Evidência:** `vulture app --min-confidence 80` → routing origin/destination ×8, connection_record, extra, attrs, rejected_by, expires_minutes.

**Ação:** renomear para `_nome` conforme tocado; nenhum arquivo morto.

## B-4 · pytest derruba o banco de desenvolvimento

**Severidade:** 🟡 P2 · **Arquivo:** `tests/conftest.py:40`

**Evidência:** `Base.metadata.drop_all(bind=engine)` no teardown da sessão — durante os testes desta semana o `gasflow.db` dev perdeu as tabelas (recriadas no boot seguinte, dados de smoke perdidos).

**Impacto:** qualquer dev que rode pytest perde dados locais silenciosamente.

**Ação:** apontar os testes para `DATABASE_URL` de teste (sqlite em temp dir) em vez do engine global do dev.

## B-5 · Schema migration implementada e testada (positivo)

**Evidência:** `init_db._ensure_sqlite_columns()` + `tests/test_schema_migration.py` (3 testes) — corrige o banco velho do app instalado (5 colunas de `clients`). Resolvido nesta semana; registrado para histórico.

## B-6 · IA degrada graciosamente (positivo)

**Evidência:** `AIEngine.chat/_classify_intent/_build_response` retornam mensagem clara + `error: AI_PROVIDER_UNAVAILABLE/AI_EMPTY_RESPONSE` quando Ollama cai. Resolvido nesta semana.
