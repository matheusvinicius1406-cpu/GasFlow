"""Fase 3 — histórico de posições do entregador (append-only).

Cobre:
- insert em lote + leitura ordenada
- upsert da "última posição" continua com 1 linha por entregador
- distance_km_between com pontos conhecidos (haversine)
- isolamento de tenant
- today_distance_km (histórico do dia no fuso local) e retenção
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database.base import Base
from app.infrastructure.repositories.delivery_persistence_model import (
    DriverLocationHistoryRecord,
    DriverLocationRecord,
)
from app.infrastructure.repositories.delivery_persistence_repository import (
    SQLAlchemyDriverLocationRepository,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def set_pragma(c, _):
        cur = c.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _point(lat: float, lng: float, recorded_at: datetime | None = None) -> dict:
    return {"latitude": lat, "longitude": lng, "recorded_at": recorded_at}


class TestHistoryInsertAndRead:
    def test_bulk_insert_grava_n_linhas(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        base = datetime.utcnow() - timedelta(minutes=10)
        points = [_point(-23.55 + i * 0.001, -46.63, base + timedelta(seconds=i * 20)) for i in range(5)]

        accepted = repo.bulk_insert_history("t1", "d1", points)

        assert accepted == 5
        assert db.query(DriverLocationHistoryRecord).count() == 5

    def test_leitura_ordenada_e_escopada(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        base = datetime.utcnow() - timedelta(minutes=5)
        # insere fora de ordem para provar o ORDER BY recorded_at
        repo.bulk_insert_history(
            "t1",
            "d1",
            [
                _point(-23.60, -46.60, base + timedelta(minutes=2)),
                _point(-23.55, -46.63, base),
            ],
        )
        repo.bulk_insert_history("t1", "d2", [_point(-22.0, -43.0, base)])

        rows = repo.get_history("t1", "d1")

        assert [r.latitude for r in rows] == [-23.55, -23.60]
        assert all(r.driver_id == "d1" for r in rows)

    def test_pontos_malformados_sao_descartados(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        accepted = repo.bulk_insert_history(
            "t1",
            "d1",
            [{"latitude": None, "longitude": -46.63}, {"latitude": -23.55, "longitude": -46.63}],
        )
        assert accepted == 1

    def test_lote_acima_de_500_e_truncado(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        points = [_point(-23.55, -46.63) for _ in range(600)]
        assert repo.bulk_insert_history("t1", "d1", points) == 500


class TestLastLocationUnchanged:
    def test_upsert_mantem_uma_linha_por_entregador(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        repo.upsert_location("t1", "d1", -23.55, -46.63)
        repo.upsert_location("t1", "d1", -23.56, -46.64)
        repo.upsert_location("t1", "d2", -22.0, -43.0)

        assert db.query(DriverLocationRecord).count() == 2
        assert repo.get_location("t1", "d1").latitude == -23.56

    def test_upsert_nao_escreve_no_historico(self, db):
        """Histórico é append-only de verdade: upsert não deve poluí-lo."""
        repo = SQLAlchemyDriverLocationRepository(db)
        repo.upsert_location("t1", "d1", -23.55, -46.63)
        assert db.query(DriverLocationHistoryRecord).count() == 0


class TestDistance:
    def test_haversine_pontos_conhecidos(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        # 0,01° de latitude ≈ 1,11 km
        repo.bulk_insert_history(
            "t1",
            "d1",
            [
                _point(-23.55, -46.63, datetime.utcnow() - timedelta(minutes=2)),
                _point(-23.56, -46.63, datetime.utcnow() - timedelta(minutes=1)),
            ],
        )
        distance = repo.distance_km_between("t1", "d1")
        assert 1.0 < distance < 1.2

    def test_distancia_zero_com_ponto_unico(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        repo.bulk_insert_history("t1", "d1", [_point(-23.55, -46.63)])
        assert repo.distance_km_between("t1", "d1") == 0.0

    def test_distancia_escopada_por_tenant(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        base = datetime.utcnow() - timedelta(minutes=2)
        pts = [
            _point(-23.55, -46.63, base),
            _point(-23.56, -46.63, base + timedelta(minutes=1)),
        ]
        repo.bulk_insert_history("t1", "d1", pts)
        repo.bulk_insert_history("t2", "d1", pts)

        assert repo.distance_km_between("t1", "d1") > 1.0
        assert repo.distance_km_between("t3", "d1") == 0.0


class TestTodayDistance:
    def test_today_distance_maior_que_zero(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        base = datetime.utcnow().replace(microsecond=0)
        repo.bulk_insert_history(
            "t1",
            "d1",
            [
                _point(-23.55, -46.63, base - timedelta(minutes=2)),
                _point(-23.56, -46.63, base - timedelta(minutes=1)),
            ],
        )
        assert repo.today_distance_km("t1", "d1") > 1.0

    def test_today_distance_ignora_dia_anterior(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        old = datetime.utcnow() - timedelta(days=2)
        repo.bulk_insert_history(
            "t1",
            "d1",
            [
                _point(-23.55, -46.63, old),
                _point(-23.60, -46.63, old + timedelta(minutes=1)),
            ],
        )
        assert repo.today_distance_km("t1", "d1") == 0.0

    def test_today_distance_isolada_por_driver(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        base = datetime.utcnow().replace(microsecond=0)
        repo.bulk_insert_history(
            "t1",
            "d1",
            [
                _point(-23.55, -46.63, base - timedelta(minutes=1)),
                _point(-23.56, -46.63, base),
            ],
        )
        assert repo.today_distance_km("t1", "d2") == 0.0


class TestRetention:
    def test_purge_apaga_antigos_e_preserva_recentes(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        old = datetime.utcnow() - timedelta(days=100)
        recent = datetime.utcnow()
        repo.bulk_insert_history("t1", "d1", [_point(-23.55, -46.63, old), _point(-23.56, -46.63, recent)])

        deleted = repo.purge_history_older_than(days=90)

        assert deleted == 1
        assert repo.get_history("t1", "d1")[0].recorded_at.date() == recent.date()
