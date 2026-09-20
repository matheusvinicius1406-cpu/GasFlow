"""F10.7 — API de impressão: fila persistida + agente local (app desktop).

Cobre:
- POST /printer/print com o PEDIDO REAL (antes respondia sucesso com um cupom
  vazio) e 404 honesto quando o pedido não existe.
- Autenticação do agente por chave de serviço (fail-closed, sem JWT).
- Ciclo claim → result do agente (payload ESC/POS em base64).
- Retry: job falhado volta para PENDING; job concluído gera reimpressão.
- /printer/status mostra o que o agente reportou.
- Idempotência do auto-print como GARANTIA DO BANCO (índice único parcial) e
  claim atômico quando dois agentes leem o mesmo job.
"""

import base64
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.infrastructure.database.base import Base
from app.main import app

SERVICE_KEY = "print-secret-123"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200
    return res.json()["token"]


@pytest.fixture(autouse=True)
def _service_key(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_service_key", SERVICE_KEY)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _drain_queue(client, printer: str = "GT710") -> None:
    """Esvazia a fila (os jobs vivem no banco de testes, compartilhado entre
    testes/execuções): cada teste deve começar com a fila previsível."""
    for _ in range(50):
        body = client.get("/printer/agent/next", headers=_agent()).json()
        if body["job"] is None:
            return
        client.post(
            f"/printer/agent/jobs/{body['job']['id']}/result",
            json={"success": True, "printer_name": printer},
            headers=_agent(),
        )
    raise AssertionError("fila não drenou")


def _agent() -> dict:
    return {"X-GasFlow-Key": SERVICE_KEY}


def _db() -> Session:
    from app.infrastructure.database.init_db import engine

    return Session(bind=engine)


@pytest.fixture()
def queue_db(tmp_path):
    """Banco SQLite próprio do teste — exercita corrida sem mexer no banco
    compartilhado da suíte (que tem jobs de outros testes)."""
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'queue.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


def _create_order_with_item(codigo: str, db: Session | None = None, status: str = "CONFIRMED") -> None:
    """Pedido + item (o cupom precisa de itens reais)."""
    from app.infrastructure.repositories.order_item_model import OrderItemModel
    from app.infrastructure.repositories.order_model import OrderModel

    own = db is None
    db = db or _db()
    try:
        if db.query(OrderModel).filter(OrderModel.codigo == codigo).first():
            return
        db.add(
            OrderModel(
                tenant_id="default",
                codigo=codigo,
                client_codigo="000001",
                address_snapshot="Rua das Flores, 120 - Jardim América",
                status=status,
                subtotal=120.0,
                delivery_fee=0.0,
                discount=0.0,
                total=120.0,
                payment_method="DINHEIRO",
                payment_status="PAID",
                source="MANUAL",
                notes="",
            )
        )
        db.add(
            OrderItemModel(
                tenant_id="default",
                order_codigo=codigo,
                product_codigo="000002",
                product_nome="Botijao de Gas P13 (13kg)",
                quantity=1,
                unit_price=120.0,
                subtotal=120.0,
            )
        )
        db.commit()
    finally:
        if own:
            db.close()


class TestOperatorEndpoints:
    def test_print_unknown_order_is_404(self, client, admin_token):
        """Antes respondia 200 com cupom de mentira (\"Cliente\"/items=[])."""
        res = client.post("/printer/print", json={"order_id": "999998"}, headers=_auth(admin_token))
        assert res.status_code == 404

    def test_print_creates_job_with_real_payload(self, client, admin_token):
        _create_order_with_item("999101")

        res = client.post("/printer/print", json={"order_id": "999101"}, headers=_auth(admin_token))
        assert res.status_code == 200, res.text
        job = res.json()["job"]
        assert job["status"] == "PENDING"
        assert job["order_id"] == "999101"
        assert job["is_reprint"] is False

    def test_print_requires_auth(self, client):
        assert client.post("/printer/print", json={"order_id": "999101"}).status_code == 401

    def test_jobs_list_and_order_jobs(self, client, admin_token):
        jobs = client.get("/printer/jobs", headers=_auth(admin_token))
        assert jobs.status_code == 200
        assert any(j["order_id"] == "999101" for j in jobs.json()["jobs"])

        by_order = client.get("/printer/orders/999101/jobs", headers=_auth(admin_token))
        assert by_order.status_code == 200
        assert by_order.json()["count"] >= 1


class TestAgentAuth:
    def test_agent_requires_service_key(self, client):
        """fail-closed: sem chave configurada ou com chave errada → 401."""
        assert client.get("/printer/agent/next").status_code == 401
        assert client.get("/printer/agent/next", headers={"X-GasFlow-Key": "nope"}).status_code == 401

    def test_user_jwt_does_not_replace_service_key(self, client, admin_token):
        """Token de operador roubado não puxa a fila (payload tem dados do cliente)."""
        res = client.get("/printer/agent/next", headers=_auth(admin_token))
        assert res.status_code == 401


class TestAgentCycle:
    def test_claim_returns_escpos_and_marks_processing(self, client, admin_token):
        _drain_queue(client)
        _create_order_with_item("999102")
        client.post("/printer/print", json={"order_id": "999102"}, headers=_auth(admin_token))

        res = client.get("/printer/agent/next", headers=_agent())
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["job"]["order_id"] == "999102"
        assert body["job"]["status"] == "PROCESSING"
        assert body["job"]["attempts"] == 1

        payload = base64.b64decode(body["escpos_base64"])
        assert payload.startswith(b"\x1b@")  # ESC @ — inicializa a impressora
        assert b"Botijao de Gas P13 (13"[:22] in payload
        assert b"999102" in payload

    def test_agent_reports_success(self, client, admin_token):
        _drain_queue(client)
        _create_order_with_item("999106")
        client.post("/printer/print", json={"order_id": "999106"}, headers=_auth(admin_token))

        res = client.get("/printer/agent/next", headers=_agent())
        assert res.status_code == 200
        job = res.json()["job"]
        assert job is not None and job["order_id"] == "999106"

        done = client.post(
            f"/printer/agent/jobs/{job['id']}/result",
            json={"success": True, "printer_name": "GT710"},
            headers=_agent(),
        )
        assert done.status_code == 200, done.text
        assert done.json()["job"]["status"] == "COMPLETED"
        assert done.json()["job"]["printer_name"] == "GT710"

    def test_agent_reports_failure_with_reason(self, client, admin_token):
        _create_order_with_item("999103")
        client.post("/printer/print", json={"order_id": "999103"}, headers=_auth(admin_token))
        claimed = client.get("/printer/agent/next", headers=_agent()).json()["job"]

        failed = client.post(
            f"/printer/agent/jobs/{claimed['id']}/result",
            json={"success": False, "error": "spooler fora do ar", "printer_name": "GT710"},
            headers=_agent(),
        )
        assert failed.status_code == 200
        assert failed.json()["job"]["status"] == "FAILED"
        assert "spooler" in failed.json()["job"]["error"]

    def test_empty_queue_returns_no_job(self, client):
        """Fila vazia → o agente não recebe job fantasma (fica esperando o poll)."""
        _drain_queue(client)
        body = client.get("/printer/agent/next", headers=_agent()).json()
        assert body["job"] is None
        assert body["escpos_base64"] is None

    def test_agent_poll_reports_expired_jobs_and_does_not_hand_them_over(self, client, admin_token):
        """O agente é quem descobre o vencimento — e precisa poder AVISAR.

        O cupom de outro dia não pode vir no claim, mas o app tem que saber que
        ele existe para notificar o operador (cupom em silêncio é pedido sem
        cupom).
        """
        from app.infrastructure.repositories.print_job_model import PrintJobModel

        _drain_queue(client)
        _create_order_with_item("999108")
        created = client.post("/printer/print", json={"order_id": "999108"}, headers=_auth(admin_token))
        job_id = created.json()["job"]["id"]

        db = _db()
        try:
            db.query(PrintJobModel).filter(PrintJobModel.id == job_id).update(
                {"created_at": datetime.utcnow() - timedelta(days=1)}
            )
            db.commit()
        finally:
            db.close()

        body = client.get("/printer/agent/next", headers=_agent()).json()

        assert body["job"] is None, "cupom de ontem não é entregue ao agente"
        assert body["expired_jobs"] >= 1, "o agente precisa saber para notificar"


class TestRetry:
    def test_failed_job_returns_to_queue(self, client, admin_token):
        _create_order_with_item("999104")
        created = client.post("/printer/print", json={"order_id": "999104"}, headers=_auth(admin_token))
        job_id = created.json()["job"]["id"]

        client.post(
            f"/printer/agent/jobs/{job_id}/result",
            json={"success": False, "error": "sem papel", "printer_name": "GT710"},
            headers=_agent(),
        )

        retried = client.post(f"/printer/jobs/{job_id}/retry", headers=_auth(admin_token))
        assert retried.status_code == 200, retried.text
        assert retried.json()["job"]["status"] == "PENDING"
        assert retried.json()["job"]["error"] is None

    def test_retry_of_expired_creates_fresh_reprint(self, client, admin_token):
        """Cupom vencido (dia anterior) sai quando o operador manda: job NOVO,
        com carimbo de agora, senão voltaria a vencer na hora."""
        _create_order_with_item("999107")
        created = client.post("/printer/print", json={"order_id": "999107"}, headers=_auth(admin_token))
        job_id = created.json()["job"]["id"]

        from app.infrastructure.repositories.print_job_model import PrintJobModel

        db = _db()
        try:
            db.query(PrintJobModel).filter(PrintJobModel.id == job_id).update(
                {"status": "EXPIRED", "error": "cupom de dia anterior — não sai sozinho"}
            )
            db.commit()
        finally:
            db.close()

        reprint = client.post(f"/printer/jobs/{job_id}/retry", headers=_auth(admin_token))
        assert reprint.status_code == 200, reprint.text
        body = reprint.json()["job"]
        assert body["id"] != job_id
        assert body["is_reprint"] is True
        assert body["status"] == "PENDING"

    def test_retry_of_completed_creates_reprint(self, client, admin_token):
        _create_order_with_item("999105")
        created = client.post("/printer/print", json={"order_id": "999105"}, headers=_auth(admin_token))
        job_id = created.json()["job"]["id"]
        client.post(
            f"/printer/agent/jobs/{job_id}/result",
            json={"success": True, "printer_name": "GT710"},
            headers=_agent(),
        )

        reprint = client.post(f"/printer/jobs/{job_id}/retry", headers=_auth(admin_token))
        assert reprint.status_code == 200
        assert reprint.json()["job"]["id"] != job_id
        assert reprint.json()["job"]["is_reprint"] is True


class TestStatus:
    def test_status_reports_agent_state_and_queue(self, client, admin_token):
        reported = client.post(
            "/printer/agent/status",
            json={"status": "ONLINE", "printer_name": "GT710", "detail": "spooler ok"},
            headers=_agent(),
        )
        assert reported.status_code == 200

        res = client.get("/printer/status", headers=_auth(admin_token))
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ONLINE"
        assert body["printer_name"] == "GT710"
        assert body["detail"] == "spooler ok"
        # Reportado AGORA pelo agente → não é "sem sinal".
        assert body["stale"] is False
        assert isinstance(body["pending_jobs"], int)
        assert isinstance(body["total_jobs_today"], int)

    def test_status_requires_auth(self, client):
        assert client.get("/printer/status").status_code == 401


class TestAutoPrintUniqueness:
    """A marca de auto-print é o banco: check-then-insert em Python não basta
    com dois workers (BACKEND_WORKERS=2 em prod)."""

    def _queue(self, queue_db, session: Session | None = None):
        from app.application.printing.print_queue import PrintQueueService

        return PrintQueueService(session or Session(bind=queue_db), "default")

    def test_second_auto_enqueue_returns_the_first_job(self, queue_db):
        session = Session(bind=queue_db)
        _create_order_with_item("999201", session)
        queue = self._queue(queue_db, session)

        first, created_first = queue.enqueue_auto(order_id="999201")
        second, created_second = queue.enqueue_auto(order_id="999201")

        assert created_first is True
        assert created_second is False, "o segundo evento não pode criar 2º cupom"
        assert second.id == first.id
        assert len(queue.jobs_for_order("999201")) == 1
        assert queue.has_job_for_order("999201", only_auto=True) is True
        session.close()

    def test_manual_prints_are_not_limited_by_the_auto_index(self, queue_db):
        """Operador pode imprimir/reimprimir quantas vezes quiser: o índice é
        parcial e cobre só `requested_by='auto_print'`."""
        session = Session(bind=queue_db)
        _create_order_with_item("999202", session)
        queue = self._queue(queue_db, session)

        queue.enqueue(order_id="999202", requested_by="admin")
        queue.enqueue(order_id="999202", requested_by="admin")
        queue.enqueue(order_id="999202", requested_by="admin", is_reprint=True)

        assert len(queue.jobs_for_order("999202")) == 3
        # E o auto-print do pedido continua podendo ser criado (nada acima é
        # marca de auto-impressão — antes o `is_reprint=False` era).
        _job, created = queue.enqueue_auto(order_id="999202")
        assert created is True
        assert queue.has_job_for_order("999202", only_auto=True) is True
        session.close()

    def test_auto_mark_ignores_manual_print_of_a_new_order(self, queue_db):
        """Imprimir manualmente um pedido NOVO não pode suprimir o cupom
        automático quando ele for pago (filtro por requested_by)."""
        session = Session(bind=queue_db)
        _create_order_with_item("999203", session, status="PENDING")
        queue = self._queue(queue_db, session)

        queue.enqueue(order_id="999203", requested_by="admin")  # botão Imprimir
        assert queue.has_job_for_order("999203", only_auto=True) is False

        from app.application.delivery.auto_print_trigger import AutoPrintTrigger

        result = AutoPrintTrigger().maybe_auto_print("999203", "default", "PAID", db=session)
        assert result["created"] is True
        session.close()

    def test_db_rejects_a_surprise_duplicate_auto_job(self, queue_db):
        """Prova de que a garantia é o índice — INSERT direto também bate."""
        from sqlalchemy.exc import IntegrityError

        from app.infrastructure.repositories.print_job_model import PrintJobModel

        session = Session(bind=queue_db)
        _create_order_with_item("999204", session)
        queue = self._queue(queue_db, session)
        queue.enqueue_auto(order_id="999204")

        session.add(
            PrintJobModel(
                id="print-999204-manual-insert",
                tenant_id="default",
                order_id="999204",
                status="PENDING",
                is_reprint=False,
                requested_by="auto_print",
                attempts=0,
                payload=b"\x1b@",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.close()


class TestPreviousDayExpiry:
    """Decisão do dono: não reimprimir o cupom de ontem.

    Reabrir o app de manhã despejava no spooler a fila inteira do dia anterior
    (cupom de pedido já entregue). Agora o que ficou de outro dia vence e só sai
    se o operador mandar reimprimir.
    """

    def _queue(self, queue_db, session: Session | None = None):
        from app.application.printing.print_queue import PrintQueueService

        return PrintQueueService(session or Session(bind=queue_db), "default")

    def _backdate(self, session: Session, job_id: str, when) -> None:
        from app.infrastructure.repositories.print_job_model import PrintJobModel

        session.query(PrintJobModel).filter(PrintJobModel.id == job_id).update({"created_at": when})
        session.commit()

    def test_yesterdays_job_expires_instead_of_printing(self, queue_db):
        session = Session(bind=queue_db)
        _create_order_with_item("999401", session)
        queue = self._queue(queue_db, session)
        job, _ = queue.enqueue_auto(order_id="999401")
        self._backdate(session, job.id, datetime.utcnow() - timedelta(days=1))

        assert queue.claim_next() is None, "cupom de ontem não pode ir para o spooler"

        session.refresh(job)
        assert job.status == "EXPIRED"
        assert "dia anterior" in (job.error or "")
        assert queue.queue_counts()["expired"] == 1
        session.close()

    def test_job_created_earlier_today_still_prints(self, queue_db):
        """A regra é o DIA local, não "menos de X horas": cupom de hoje sai."""
        session = Session(bind=queue_db)
        _create_order_with_item("999402", session)
        queue = self._queue(queue_db, session)
        job, _ = queue.enqueue_auto(order_id="999402")
        self._backdate(session, job.id, datetime.utcnow() - timedelta(hours=3))

        claimed = queue.claim_next()

        assert claimed is not None, "3h atrás ainda é hoje"
        assert claimed[0].id == job.id
        session.close()

    def test_expiry_only_touches_jobs_still_waiting(self, queue_db):
        """Vencimento é sobre o que o agente AINDA não pegou.

        Job já concluído/falhado tem história própria (e o COMPLETED é a marca de
        "este cupom saiu"); job em PROCESSING é de um agente trabalhando agora.
        Nenhum dos dois pode virar EXPIRED pelo simples fato de ser de ontem.
        """
        from app.infrastructure.repositories.print_job_model import PrintJobModel

        session = Session(bind=queue_db)
        _create_order_with_item("999403", session)
        _create_order_with_item("999404", session)
        queue = self._queue(queue_db, session)
        done = queue.enqueue(order_id="999403", requested_by="admin")
        running = queue.enqueue(order_id="999404", requested_by="admin")

        old = datetime.utcnow() - timedelta(days=2)
        self._backdate(session, done.id, old)
        self._backdate(session, running.id, old)
        session.query(PrintJobModel).filter(PrintJobModel.id == done.id).update(
            {"status": "COMPLETED", "completed_at": old}
        )
        session.query(PrintJobModel).filter(PrintJobModel.id == running.id).update(
            {"status": "PROCESSING", "claimed_at": old}
        )
        session.commit()

        assert queue.expire_previous_days() == 0

        session.refresh(done)
        session.refresh(running)
        assert done.status == "COMPLETED"
        assert running.status == "PROCESSING"
        session.close()


class TestClaimRace:
    """Dois agentes (dois PCs, ou dois workers) que leram o MESMO job: só um
    imprime. Quem perde recebe None em vez de mandar o cupom de novo."""

    def test_loser_of_the_race_does_not_get_the_job(self, queue_db):
        from app.application.printing.print_queue import PrintQueueService

        winner_session = Session(bind=queue_db)
        loser_session = Session(bind=queue_db)
        _create_order_with_item("999301", winner_session)
        PrintQueueService(winner_session, "default").enqueue_auto(order_id="999301")

        loser = PrintQueueService(loser_session, "default")
        peeked = loser._peek_next()  # ambos viram o mesmo PENDING
        assert peeked is not None

        claimed = PrintQueueService(winner_session, "default").claim_next()
        assert claimed is not None
        assert claimed[0].id == peeked.id

        # O loser tenta reivindicar exatamente o que já viu: o UPDATE
        # condicional não casa (status já é PROCESSING) → perdeu.
        assert loser._claim(peeked.id) is False
        assert loser.claim_next() is None, "não há segundo job fantasma"
        assert claimed[0].id == peeked.id
        winner_session.close()
        loser_session.close()

    def test_give_up_after_max_attempts(self, queue_db):
        """Job que sempre falha não fica em loop: vira FAILED no teto."""
        from app.application.printing.print_queue import MAX_ATTEMPTS, PrintQueueService
        from app.infrastructure.repositories.print_job_model import PrintJobModel

        session = Session(bind=queue_db)
        _create_order_with_item("999302", session)
        queue = PrintQueueService(session, "default")
        job, _ = queue.enqueue_auto(order_id="999302")
        session.query(PrintJobModel).filter(PrintJobModel.id == job.id).update({"attempts": MAX_ATTEMPTS})
        session.commit()

        assert queue.claim_next() is None
        session.refresh(job)
        assert job.status == "FAILED"
        assert "tentativas" in (job.error or "")
        session.close()
