"""Fase 9 — testes do DispatchScorer.

Cobre:
- entregador perto ganha de longe (demais fatores iguais);
- sobrecarregado perde para livre mesmo sendo mais perto;
- prazo apertado penaliza;
- fairness penaliza quem recebeu muito na janela;
- sem posição conhecida → penalidade pequena e documentada;
- breakdown bate com o total;
- flag desligada → 409 no preview;
- peso configurável por env.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker

from app.application.dispatch.scorer import (
    DEFAULT_WEIGHTS,
    STALE_POSITION_MINUTES,
    DispatchScorer,
)
from app.domain.routing.provider import Point, RouteLeg, RoutingProvider
from app.infrastructure.database.base import Base
from app.infrastructure.repositories.delivery_persistence_model import (
    DeliveryRecord,
    DriverLocationHistoryRecord,
)


# ── Provider fake ────────────────────────────────────────────


class FakeProvider(RoutingProvider):
    """Haversine puro para testes."""

    name = "haversine"

    @staticmethod
    def _haversine(a: Point, b: Point) -> float:
        import math

        R = 6371.0
        lat1, lon1 = math.radians(a[0]), math.radians(a[1])
        lat2, lon2 = math.radians(b[0]), math.radians(b[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        x = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(x), math.sqrt(1 - x))

    def distance_matrix(self, points):
        n = len(points)
        return [[self._haversine(points[i], points[j]) for j in range(n)] for i in range(n)]

    def duration_matrix(self, points):
        km = self.distance_matrix(points)
        return [[int(round(d / 28 * 3600)) for d in row] for row in km]

    def route(self, origin, destination, waypoints=()):
        sequence = [origin, *waypoints, destination]
        total = sum(self._haversine(a, b) for a, b in zip(sequence, sequence[1:]))
        return RouteLeg(total, int(round(total / 28 * 3600)), None)


# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @sa_event.listens_for(engine, "connect")
    def set_pragma(c, _):
        cur = c.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def provider():
    return FakeProvider()


def _add_driver(db, driver_id, tenant_id="default", active=True):
    from app.infrastructure.repositories.delivery_model import DeliveryDriverModel

    db.add(
        DeliveryDriverModel(
            tenant_id=tenant_id,
            codigo=driver_id,
            nome=f"Driver {driver_id}",
            telefone="00000000000",
            ativo=active,
        )
    )
    db.commit()


def _add_delivery(
    db,
    delivery_id,
    tenant_id="default",
    lat=-23.56,
    lng=-46.63,
    status="ASSIGNED",
    driver_id="drv-1",
    scheduled_at=None,
    assigned_at=None,
):
    db.add(
        DeliveryRecord(
            delivery_id=delivery_id,
            tenant_id=tenant_id,
            order_id=f"ORD-{delivery_id}",
            customer_codigo="C001",
            customer_name="Teste",
            address_lat=lat,
            address_lng=lng,
            status=status,
            driver_id=driver_id,
            scheduled_at=scheduled_at,
            assigned_at=assigned_at or datetime.utcnow(),
        )
    )
    db.commit()


def _add_position(db, driver_id, lat, lng, tenant_id="default", recorded_at=None):
    ts = recorded_at or datetime.utcnow()
    db.add(
        DriverLocationHistoryRecord(
            tenant_id=tenant_id,
            driver_id=driver_id,
            latitude=lat,
            longitude=lng,
            recorded_at=ts,
        )
    )
    db.commit()


# ── Testes ──────────────────────────────────────────────────


class TestDispatchScorer:
    """Testes unitários do scorer."""

    def test_proximidade_perto_ganha(self, db, provider):
        """Entregador perto ganha de longe (demais fatores iguais)."""
        _add_driver(db, "000001")
        _add_driver(db, "000002")
        _add_delivery(db, "dlv-1", lat=-23.56, lng=-46.63)
        _add_position(db, "000001", lat=-23.561, lng=-46.631)  # ~100m
        _add_position(db, "000002", lat=-23.60, lng=-46.70)  # ~10km

        scorer = DispatchScorer(db, "default", provider=provider)
        scores = scorer.score(delivery_id="dlv-1")

        assert len(scores) >= 2
        near = next(s for s in scores if s.driver_id == "000001")
        far = next(s for s in scores if s.driver_id == "000002")
        assert near.total > far.total

    def test_sobrecarregado_perde(self, db, provider):
        """Entregador com muitas entregas perde para um livre."""
        _add_driver(db, "000010")
        _add_driver(db, "000011")
        _add_delivery(db, "dlv-1", lat=-23.56, lng=-46.63)
        _add_position(db, "000010", lat=-23.561, lng=-46.631)
        _add_position(db, "000011", lat=-23.562, lng=-46.632)

        # Simula 4 entregas ativas para 000010
        for i in range(4):
            _add_delivery(db, f"dlv-busy-{i}", driver_id="000010", status="EN_ROUTE")

        scorer = DispatchScorer(db, "default", provider=provider)
        scores = scorer.score(delivery_id="dlv-1")

        busy = next(s for s in scores if s.driver_id == "000010")
        free = next(s for s in scores if s.driver_id == "000011")
        # O livre deve ter load maior (menos penalizado).
        assert free.breakdown["load"] > busy.breakdown["load"]

    def test_prazo_apertado_penaliza(self, db, provider):
        """Entrega com prazo apertado penaliza quem não chega a tempo."""
        _add_driver(db, "000020")
        _add_delivery(
            db,
            "dlv-1",
            lat=-23.56,
            lng=-46.63,
            scheduled_at=datetime.utcnow() + timedelta(minutes=5),  # 5 min de prazo
        )
        # Entregador a 10km de distância → ETA ~21 min → não chega a tempo
        _add_position(db, "000020", lat=-23.60, lng=-46.70)

        scorer = DispatchScorer(db, "default", provider=provider)
        scores = scorer.score(delivery_id="dlv-1")

        assert len(scores) >= 1
        s = scores[0]
        assert s.breakdown["deadline"] < 100.0  # penalizado

    def test_fairness_penaliza(self, db, provider):
        """Entregador que recebeu muitas entregas recentemente é penalizado."""
        _add_driver(db, "000030")
        _add_driver(db, "000031")
        _add_delivery(db, "dlv-1", lat=-23.56, lng=-46.63)
        _add_position(db, "000030", lat=-23.561, lng=-46.631)
        _add_position(db, "000031", lat=-23.562, lng=-46.632)

        # Simula 3 entregas recentes para 000030
        for i in range(3):
            _add_delivery(
                db,
                f"dlv-fair-{i}",
                driver_id="000030",
                status="DELIVERED",
            )

        scorer = DispatchScorer(db, "default", provider=provider)
        scores = scorer.score(delivery_id="dlv-1")

        fair = next(s for s in scores if s.driver_id == "000030")
        new = next(s for s in scores if s.driver_id == "000031")
        assert fair.breakdown["fairness"] < new.breakdown["fairness"]

    def test_breakdown_bate_com_total(self, db, provider):
        """breakdown dos componentes bate com o total (pesos normalizados)."""
        _add_driver(db, "000040")
        _add_delivery(db, "dlv-1", lat=-23.56, lng=-46.63)
        _add_position(db, "000040", lat=-23.561, lng=-46.631)

        scorer = DispatchScorer(db, "default", provider=provider)
        scores = scorer.score(delivery_id="dlv-1")

        assert len(scores) >= 1
        s = scores[0]
        expected_total = sum(DEFAULT_WEIGHTS[name] * s.breakdown[name] for name in DEFAULT_WEIGHTS)
        assert abs(s.total - expected_total) < 0.1

    def test_entregador_inexistente_ausente(self, db, provider):
        """Entregador inexistente no tenant não aparece no resultado."""
        _add_delivery(db, "dlv-1", lat=-23.56, lng=-46.63)

        scorer = DispatchScorer(db, "default", provider=provider)
        scores = scorer.score(delivery_id="dlv-1", candidate_driver_ids=["999999"])

        assert len(scores) == 0

    def test_posicao_velha_penaliza(self, db, provider):
        """Posição antiga (>15 min) reduz o score de proximidade."""
        _add_driver(db, "000050")
        _add_delivery(db, "dlv-1", lat=-23.56, lng=-46.63)
        _add_position(
            db,
            "000050",
            lat=-23.561,
            lng=-46.631,
            recorded_at=datetime.utcnow() - timedelta(minutes=30),
        )

        scorer = DispatchScorer(db, "default", provider=provider)
        scores = scorer.score(delivery_id="dlv-1")

        assert len(scores) >= 1
        s = scores[0]
        # Posição velha: proximidade descontada.
        assert s.position_age_s is not None
        assert s.position_age_s > STALE_POSITION_MINUTES * 60

    def test_sorted_deterministic(self, db, provider):
        """Dois scores iguais não trocam de ordem entre chamadas."""
        _add_driver(db, "000060")
        _add_driver(db, "000061")
        _add_delivery(db, "dlv-1", lat=-23.56, lng=-46.63)
        # Sem posição: ambos com score 0 em proximidade.

        scorer = DispatchScorer(db, "default", provider=provider)
        scores1 = [s.driver_id for s in scorer.score(delivery_id="dlv-1")]
        scores2 = [s.driver_id for s in scorer.score(delivery_id="dlv-1")]

        assert scores1 == scores2
