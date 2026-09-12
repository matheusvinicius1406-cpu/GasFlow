import os

from PyInstaller.utils.hooks import collect_submodules

SRC = SPECPATH  # diretório backend/ (onde este spec vive)

hiddenimports = (
    collect_submodules("app")
    + collect_submodules("uvicorn")
    # Executados no boot do exe (desktop_entry.run_migrations):
    + collect_submodules("alembic")
    + collect_submodules("mako")
)

# Alembic no exe: ini + migrations/ empacotados como datas, lidos em runtime
# por desktop_entry.run_migrations() a partir de <_MEIPASS>/migrations_bundle.
datas = [
    (os.path.join(SRC, "alembic.ini"), "migrations_bundle"),
    (os.path.join(SRC, "migrations"), "migrations_bundle/migrations"),
]

a = Analysis(
    ["desktop_entry.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="gasflow-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
