# Cadeia de migrations arquivada (a074 -> b001 -> c001, Ago 2026)

Motivo: cadeia quebrada — 'alembic upgrade head' falha em SQLite (drop_constraint sem batch mode) e
cobria apenas 18 das 39 tabelas atuais. O baseline atual vive em versions/ e é gerado
a partir dos models SQLAlchemy (fonte única do schema). Consulte git para o histórico.
