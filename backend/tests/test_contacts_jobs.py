"""Fase 2 §5/§9 etapa 8 — jobs bounded-batch do renomeador.

Cobre:
- faixas e retomada por cursor (GEOCODE);
- passe Overpass **UPDATE-only** de `intersecoes`, com métrica persistida;
- APPLY em blocos com a regra;
- validações (tipo/regra);
- flag `CONTACT_RENAMER_ENABLED` em vigor (409 nos endpoints).

Providers são fakes injetados: nenhuma rede no teste.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.contacts.jobs import ContactJobService
from app.application.contacts.organizer import build_rename_rule
from app.infrastructure.database.base import Base
from app.infrastructure.repositories.client_model import ClientModel
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.infrastructure.repositories.geocode_cache_model import GeocodeCacheModel

import app.infrastructure.database.init_db  # noqa: F401 — registra todos os models


# ═══════════════════════════════════════════════════════════
# Fakes
# ═══════════════════════════════════════════════════════════


class FakeGeocoding:
    def __init__(self):
        self.chamadas = 0

    def geocodificar_cliente(self, cliente):
        self.chamadas += 1
        cliente.geocode_status = "OK"
        cliente.lat = -1.3056058
        cliente.lng = -48.4738326
        return "OK"


class FakeOverpass:
    def __init__(self, intersecoes=None):
        # `[]` é resultado legítimo (D2): distinguir de "usar o default".
        self.intersecoes = (
            intersecoes
            if intersecoes is not None
            else [
                {"nome": "Rua A", "numero": 30},
                {"nome": "Rua B", "numero": 70},
            ]
        )
        self.chamadas = 0

    def buscar_intersecoes(self, rua, lat, lng):
        from app.infrastructure.geocoding.overpass_provider import PasseIntersecoes

        self.chamadas += 1
        return PasseIntersecoes(
            intersecoes=[dict(i) for i in self.intersecoes],
            encontrou_rua=True,
            ancoras=3,
            cruzamentos=3,
            inversoes_numero=1,
            motivo="ok",
        )


def _seed_client(db, codigo, nome="Maria", telefone=None, **kw):
    row = ClientModel(
        tenant_id="default",
        codigo=codigo,
        nome=nome,
        telefone=telefone or f"1199999{codigo[-4:]}",
        rua=kw.get("rua", "Travessa São Roque"),
        numero=kw.get("numero", "145"),
        bairro=kw.get("bairro", "Centro"),
        geocode_status=kw.get("geocode_status"),
        cep=kw.get("cep"),
        entre_ruas=kw.get("entre_ruas"),
        has_name=kw.get("has_name", True),
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def env():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    repo = SQLAlchemyClientRepository(db, "default")
    yield db, repo
    db.close()


# ═══════════════════════════════════════════════════════════
# 1. GEOCODE — faixas + retomada
# ═══════════════════════════════════════════════════════════


class TestJobGeocode:
    def test_processa_em_faixas_e_retoma_pelo_cursor(self, env):
        db, repo = env
        for i in (1, 2, 3):
            _seed_client(db, f"{i:06d}", geocode_status=None)
        svc = ContactJobService(db, repo, "default", geocoding=FakeGeocoding())

        job = svc.criar_job("GEOCODE")
        assert job["total"] == 3
        assert job["status"] == "PENDENTE"

        primeira = svc.processar_proximo_lote(job["id"], limite=2)
        assert primeira["processados"] == 2
        assert primeira["status"] == "PROCESSANDO"
        assert primeira["restantes"] == 1

        segunda = svc.processar_proximo_lote(job["id"])
        assert segunda["processados"] == 3
        assert segunda["status"] == "CONCLUIDO"

        # Terceira chamada é idempotente (nada muda).
        assert svc.processar_proximo_lote(job["id"])["processados"] == 3
        assert db.query(ClientModel).filter(ClientModel.geocode_status == "OK").count() == 3

    def test_contato_sem_rua_nao_entra_no_lote(self, env):
        db, repo = env
        _seed_client(db, "000001", rua="A definir")
        _seed_client(db, "000002", rua="Travessa São Roque")
        svc = ContactJobService(db, repo, "default", geocoding=FakeGeocoding())

        job = svc.criar_job("GEOCODE")

        assert job["total"] == 1


# ═══════════════════════════════════════════════════════════
# 2. OVERPASS — UPDATE só de intersecoes (§8.4)
# ═══════════════════════════════════════════════════════════


class TestJobOverpass:
    def _cache(self, db, rua, lat, lng, intersecoes=None):
        linha = GeocodeCacheModel(chave=uuid.uuid4().hex, rua=rua, lat=lat, lng=lng, intersecoes=intersecoes)
        db.add(linha)
        db.commit()
        return linha

    def test_preenche_intersecoes_e_nao_toca_em_lat_lng(self, env):
        db, repo = env
        alvo = self._cache(db, "Travessa São Roque", -1.3, -48.4)
        self._cache(db, "Sem Coordenada", None, None)  # lat nulo → fora
        self._cache(db, "Já Processada", -1.3, -48.4, intersecoes=[])  # já tem valor
        fake = FakeOverpass()
        svc = ContactJobService(db, repo, "default", overpass=fake)

        job = svc.criar_job("OVERPASS")
        assert job["total"] == 1

        fim = svc.processar_proximo_lote(job["id"])

        assert fim["status"] == "CONCLUIDO"
        db.refresh(alvo)
        assert alvo.intersecoes == [
            {"nome": "Rua A", "numero": 30},
            {"nome": "Rua B", "numero": 70},
        ]
        # UPDATE-only: lat/lng intactos, nenhuma linha criada.
        assert (alvo.lat, alvo.lng) == (-1.3, -48.4)
        assert db.query(GeocodeCacheModel).count() == 3
        assert fake.chamadas == 1

    def test_metrica_do_passe_e_persistida(self, env):
        db, repo = env
        self._cache(db, "Travessa São Roque", -1.3, -48.4)
        svc = ContactJobService(db, repo, "default", overpass=FakeOverpass())

        job = svc.criar_job("OVERPASS")
        svc.processar_proximo_lote(job["id"])

        metrica = svc.status(job["id"])["metrica"]
        assert metrica["ruas"] == 1
        assert metrica["ruas_com_2_ancoras"] == 1
        assert metrica["ruas_com_2_cruzamentos"] == 1
        assert metrica["ruas_com_intersecoes"] == 1

    def test_sem_intersecoes_grava_vazio_e_nao_quebra(self, env):
        db, repo = env
        linha = self._cache(db, "Rua Sem Dado", -1.3, -48.4)
        svc = ContactJobService(db, repo, "default", overpass=FakeOverpass(intersecoes=[]))

        job = svc.criar_job("OVERPASS")
        svc.processar_proximo_lote(job["id"])

        db.refresh(linha)
        assert linha.intersecoes == []
        assert svc.status(job["id"])["metrica"]["ruas_com_intersecoes"] == 0


# ═══════════════════════════════════════════════════════════
# 3. APPLY — renomeia em blocos
# ═══════════════════════════════════════════════════════════


class TestJobApply:
    def test_apply_em_blocos_usa_a_regra(self, env):
        db, repo = env
        for i in (1, 2, 3):
            # Nomes distintos: nome duplicado vira conflito ("Revisar") e o
            # organizer exclui conflito do lote de propósito.
            _seed_client(db, f"{i:06d}", nome=f"Cliente {i}", telefone=f"1199999000{i}")
        svc = ContactJobService(db, repo, "default")

        regra = build_rename_rule(pattern_endereco=True)
        job = svc.criar_job("APPLY", regra=regra)
        assert job["total"] == 3

        fim = svc.processar_proximo_lote(job["id"], limite=2)
        assert fim["processados"] == 2
        assert fim["alterados"] == 2
        assert fim["status"] == "PROCESSANDO"

        fim = svc.processar_proximo_lote(job["id"])
        assert fim["status"] == "CONCLUIDO"
        assert fim["alterados"] == 3
        nomes = [repo.buscar_por_codigo(c).nome for c in ("000001", "000002", "000003")]
        # D7: o nome sai sem zeros à esquerda (1=, 2=, 3=).
        assert all(n.startswith(f"{int(c)}=") for c, n in zip(("000001", "000002", "000003"), nomes))
        assert all("Travessa São Roque" in n for n in nomes)

    def test_filtro_por_bairro_escopa_o_apply(self, env):
        db, repo = env
        _seed_client(db, "000001", nome="Um", telefone="11999990001", bairro="Centro")
        _seed_client(db, "000002", nome="Dois", telefone="11999990002", bairro="Norte")
        svc = ContactJobService(db, repo, "default")

        job = svc.criar_job("APPLY", filtro={"bairro": "Centro"}, regra=build_rename_rule(case="upper"))
        assert job["total"] == 1
        svc.processar_proximo_lote(job["id"])

        assert repo.buscar_por_codigo("000001").nome == "UM"
        assert repo.buscar_por_codigo("000002").nome == "Dois"


# ═══════════════════════════════════════════════════════════
# 4. Validações
# ═══════════════════════════════════════════════════════════


class TestValidacoes:
    def test_tipo_invalido(self, env):
        db, repo = env
        svc = ContactJobService(db, repo, "default")
        with pytest.raises(ValueError):
            svc.criar_job("XPTO")

    def test_apply_exige_regra(self, env):
        db, repo = env
        svc = ContactJobService(db, repo, "default")
        with pytest.raises(ValueError):
            svc.criar_job("APPLY")

    def test_job_inexistente(self, env):
        db, repo = env
        svc = ContactJobService(db, repo, "default")
        with pytest.raises(ValueError):
            svc.status("nao-existe")


# ═══════════════════════════════════════════════════════════
# 5. HTTP — flag em vigor (409) + criação/processo
# ═══════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


class TestJobsAPI:
    def test_flag_desligada_responde_409(self, client, admin_headers, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "contact_renamer_enabled", False)
        res = client.post(
            "/whatsapp/contacts/jobs",
            json={"tipo": "GEOCODE"},
            headers=admin_headers,
        )
        assert res.status_code == 409

    def test_status_tambem_respeita_a_flag(self, client, admin_headers, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "contact_renamer_enabled", False)
        res = client.get("/whatsapp/contacts/jobs/qualquer", headers=admin_headers)
        assert res.status_code == 409

    def test_cria_e_processa_com_a_flag_ligada(self, client, admin_headers, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "contact_renamer_enabled", True)
        # O provider de geocoding real bate na rede: o teste prova o FLUXO do
        # endpoint, não o provedor (esse tem teste próprio). Desligar o
        # geocoding faz o contato sair como PENDENTE, sem requisição externa.
        monkeypatch.setattr(settings, "geocoding_enabled", False)
        criado = client.post(
            "/whatsapp/contacts/jobs",
            json={"tipo": "GEOCODE"},
            headers=admin_headers,
        )
        assert criado.status_code == 200, criado.text
        job_id = criado.json()["id"]

        res = client.post(f"/whatsapp/contacts/jobs/{job_id}/process", headers=admin_headers)
        assert res.status_code == 200, res.text
        assert res.json()["status"] in ("PROCESSANDO", "CONCLUIDO")

        status = client.get(f"/whatsapp/contacts/jobs/{job_id}", headers=admin_headers)
        assert status.status_code == 200
        assert status.json()["id"] == job_id

    def test_apply_sem_regra_422(self, client, admin_headers, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "contact_renamer_enabled", True)
        res = client.post(
            "/whatsapp/contacts/jobs",
            json={"tipo": "APPLY"},
            headers=admin_headers,
        )
        assert res.status_code == 422
