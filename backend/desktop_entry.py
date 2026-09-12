"""Entrypoint do backend empacotado (PyInstaller) — Desktop GasFlow.

Diferenças em relação a rodar `app.main:app` direto (Docker/compose):

1. **Migrations no boot**: aplica `alembic upgrade head` no DATABASE_URL
   antes de subir o uvicorn. Bancos legados criados pelo antigo
   `init_db()/create_all` (sem tabela `alembic_version`) recebem
   `stamp head` primeiro — o schema deles é idêntico ao baseline e não
   deve ser recriado; a partir daí o Alembic passa a gerenciar a evolução
   (ver migrations/README.md, seção "Bancos existentes criados por
   create_all").

2. **Nunca derruba o app por falha de migração**: qualquer exceção é
   logada e o boot continua — o `init_db()/create_all` em `app.main`
   (que também roda `_ensure_sqlite_columns()`) atua como rede de
   segurança para colunas faltantes.

Empacotamento (gasflow-backend.spec): `alembic.ini` + `migrations/` entram
como datas em `<_MEIPASS>/migrations_bundle/`; `alembic`/`mako` entram como
hiddenimports. Em dev (sem PyInstaller), o bundle é o próprio diretório
backend/.
"""

import argparse
import logging
import os
import sys

import uvicorn

logger = logging.getLogger("gasflow.desktop_entry")


def _bundle_dir() -> str:
    """Diretório que contém alembic.ini + migrations/.

    Empacotado: `<_MEIPASS>/migrations_bundle` (datas do spec).
    Dev: o próprio diretório backend/ (este arquivo fica na raiz dele).
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = os.path.join(meipass, "migrations_bundle")
        if os.path.isdir(candidate):
            return candidate
    return os.path.dirname(os.path.abspath(__file__))


def _table_names(url: str) -> set[str]:
    from sqlalchemy import create_engine, inspect

    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def run_migrations() -> None:
    """Aplica `alembic upgrade head` no DATABASE_URL atual.

    - Banco vazio (0 tabelas): a cadeia completa cria tudo + alembic_version.
    - Banco legado create_all (tabelas, sem alembic_version): `stamp head`
      e o upgrade passa a ser incremental (no-op aqui).
    - Banco já versionado: aplica apenas as revisões pendentes.
    """
    from alembic import command
    from alembic.config import Config

    url = os.getenv("DATABASE_URL", "sqlite:///./gasflow.db")
    bundle = _bundle_dir()

    cfg = Config(os.path.join(bundle, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(bundle, "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)

    tables = _table_names(url)
    if "alembic_version" not in tables and tables:
        logger.warning(
            "banco legado sem alembic_version (%d tabelas) — aplicando stamp head",
            len(tables),
        )
        command.stamp(cfg, "head")

    command.upgrade(cfg, "head")
    logger.info("migrations aplicadas (alembic upgrade head)")


def main(argv: list[str] | None = None) -> None:
    """Boot do exe: migrations (falha não derruba o app) + uvicorn."""
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args, _unknown = parser.parse_known_args(argv)
    args.port = int(args.port)

    try:
        run_migrations()
    except Exception:
        logger.exception("migrations falharam no boot — seguindo com init_db/create_all")

    from app.main import app

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
