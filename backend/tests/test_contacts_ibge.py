"""Fase 3 — `IbgeEntreRuasProvider` (ADR-0008, spec §6).

Os testes rodam sobre uma **fixture sintética** que reproduz a estrutura medida
em Belém, não sobre a base crua (97 MB fora do repo):

- duas faces **apertadas** e decrescentes, compartilhando os mesmos dois
  cruzamentos (é o que faz o "entre" fechar);
- uma face **solta** com âncora outlier (48 entre 188) que só não estraga o
  par porque o dedup por nome (§8.8.3) retém o **menor** número da via;
- uma face **curta** que põe o cruzamento de baixo na rua;
- uma âncora **fora da tolerância** (via paralela), que não pode virar número.

O caso de aceite real (Passagem Ivan Leão, 45 → "entre Travessa dos Berredos e
Passagem Pedro Álvares Cabral") foi medido contra a base ingerida e devolve o
mesmo par; aqui ele é reproduzido pela fixture porque a base não vive no
repositório.
"""

from __future__ import annotations


import pytest

from app.application.contacts.geocoding import escolher_entre_ruas
from app.infrastructure.database.connection import SessionLocal
from app.infrastructure.geocoding.ibge_provider import IbgeEntreRuasProvider
from app.infrastructure.repositories.ibge_model import (
    CnefeEnderecoModel,
    LogradouroFaceModel,
    LogradouroNoModel,
)

_MUN = "1501402"
_RUA = "passagem teste ibge"
_SETOR = "150140260000001P"

# Face nº → (inicio, fim) ao longo do eixo. Faces NÃO compartilham extremidades
# (medido: mínimo 6,94 m), então cada uma tem seu próprio par de nós.
_FACES = {
    18: ((-1.30620, -48.4730), (-1.30660, -48.4730)),
    11: ((-1.30625, -48.4730), (-1.30665, -48.4730)),
    4: ((-1.30700, -48.4730), (-1.30730, -48.4730)),
    7: ((-1.30605, -48.4730), (-1.30615, -48.4730)),
}

# Nós de cruzamento por face: chave da via transversal → nome exibido.
_CRUZAMENTOS = {
    18: (
        ("passagem pedro alvares cabral", "PASSAGEM PEDRO ALVARES CABRAL"),
        ("travessa dos berredos", "TRAVESSA DOS BERREDOS"),
    ),
    11: (
        ("passagem pedro alvares cabral", "PASSAGEM PEDRO ALVARES CABRAL"),
        ("travessa dos berredos", "TRAVESSA DOS BERREDOS"),
    ),
    4: (("travessa santa maria", "TRAVESSA SANTA MARIA"), ("rua menino deus", "RUA MENINO DEUS")),
    7: (("rua menino deus", "RUA MENINO DEUS"), ("travessa souza franco", "TRAVESSA SOUZA FRANCO")),
}


def _entre(a, b, frac):
    return (a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac)


def _lateral(ponto, metros):
    """Desloca perpendicularmente: o eixo corre no meridiano ⇒ desloca em lng."""
    return (ponto[0], ponto[1] + metros / 111320.0)


@pytest.fixture()
def db():
    sessao = SessionLocal()
    for modelo in (CnefeEnderecoModel, LogradouroFaceModel, LogradouroNoModel):
        sessao.query(modelo).delete()
    sessao.commit()
    try:
        yield sessao
    finally:
        sessao.rollback()
        for modelo in (CnefeEnderecoModel, LogradouroFaceModel, LogradouroNoModel):
            sessao.query(modelo).delete()
        sessao.commit()
        sessao.close()


def _semear(db, *, ancoras=True, cruzamentos=True, faces=None):
    """Monta a rua. `faces` overrideia quais faces entram (default: todas)."""
    for face, (inicio, fim) in _FACES.items():
        if faces is not None and face not in faces:
            continue
        db.add(
            LogradouroFaceModel(
                cod_municipio=_MUN,
                cod_setor=_SETOR,
                cod_quadra=2 if face in (18, 4) else 4,
                cod_face=face,
                chave_logradouro=_RUA,
                nome_logradouro="Passagem Teste Ibge",
                geom=[list(inicio), list(fim)],
            )
        )
        if cruzamentos:
            for (chave, nome), ponto in zip(_CRUZAMENTOS[face], (inicio, fim)):
                db.add(
                    LogradouroNoModel(
                        cod_municipio=_MUN,
                        node_lat=ponto[0],
                        node_lng=ponto[1],
                        chave_logradouro=chave,
                        nome_logradouro=nome,
                    )
                )
    if not ancoras:
        db.commit()
        return

    def add(face, quadra, numero, frac, nv="1", ponto=None):
        inicio, fim = _FACES[face]
        db.add(
            CnefeEnderecoModel(
                cod_municipio=_MUN,
                cod_unico_endereco=f"t-{quadra}-{face}-{numero}-{frac}",
                cod_setor=_SETOR,
                num_quadra=quadra,
                num_face=face,
                num_endereco=numero,
                chave_logradouro=_RUA,
                chave_nome="teste ibge",
                nome_logradouro="Passagem Teste Ibge",
                lat=(ponto or _entre(inicio, fim, frac))[0],
                lng=(ponto or _entre(inicio, fim, frac))[1],
                nv_geo_coord=nv,
            )
        )

    # Faces apertadas e DECRESCENTES (62→33 e 65→35), como as de Ivan Leão.
    add(18, 2, 62, 0.2)
    add(18, 2, 45, 0.5)
    add(18, 2, 33, 0.8)
    add(11, 4, 65, 0.2)
    add(11, 4, 50, 0.5)
    add(11, 4, 35, 0.8)
    # Face solta: 188 no início, 48 no fim (o 48 é a âncora que só não vira
    # "acima de 45" porque o dedup por nome mantém o MENOR número da via).
    add(4, 2, 188, 0.1)
    add(4, 2, 48, 0.9)
    # Face curta, crescente — é quem dá o cruzamento de baixo da rua.
    add(7, 4, 6, 0.2)
    add(7, 4, 10, 0.8)
    db.commit()


def _provider(db) -> IbgeEntreRuasProvider:
    return IbgeEntreRuasProvider(db)


def _nomes(passe):
    return [item["nome"] for item in passe.intersecoes]


class TestCasoDeAceite:
    def test_par_que_emoldura_o_45(self, db):
        _semear(db)
        passe = _provider(db).buscar_intersecoes("Passagem Teste Ibge")
        assert passe.motivo == "ok"
        assert passe.encontrou_rua is True

        resposta = escolher_entre_ruas(passe.intersecoes, 45)
        assert resposta is not None
        assert {p.strip() for p in resposta.split(" e ")} == {
            "TRAVESSA DOS BERREDOS",
            "PASSAGEM PEDRO ALVARES CABRAL",
        }

    def test_dedup_mantem_o_menor_numero_da_via(self, db):
        """§8.8.3: uma via transversal entra uma vez só, pelo menor número."""
        _semear(db)
        passe = _provider(db).buscar_intersecoes("Passagem Teste Ibge")
        nomes = _nomes(passe)
        assert len(nomes) == len(set(nomes))
        # RUA MENINO DEUS aparece nas faces 4 (48) e 7 (6): fica 6.
        assert {i["nome"]: i["numero"] for i in passe.intersecoes}["RUA MENINO DEUS"] == 6

    def test_ordenacao_crescente(self, db):
        _semear(db)
        passe = _provider(db).buscar_intersecoes("Passagem Teste Ibge")
        numeros = [i["numero"] for i in passe.intersecoes]
        assert numeros == sorted(numeros)

    def test_direcao_da_face_decrescente(self, db):
        """Com a numeração caindo ao longo da geometria, o extremo ALTO fica em
        geom[0]: trocar isso inverte o par do "entre"."""
        _semear(db)
        passe = _provider(db).buscar_intersecoes("Passagem Teste Ibge")
        por_nome = {i["nome"]: i["numero"] for i in passe.intersecoes}
        assert por_nome["TRAVESSA DOS BERREDOS"] < por_nome["PASSAGEM PEDRO ALVARES CABRAL"]


class TestContrato:
    def test_formato_congelado(self, db):
        _semear(db)
        passe = _provider(db).buscar_intersecoes("Passagem Teste Ibge")
        assert len(passe.intersecoes) >= 2
        for item in passe.intersecoes:
            assert isinstance(item, dict)
            assert set(item) == {"nome", "numero"}
            assert isinstance(item["nome"], str) and item["nome"].strip()
            assert isinstance(item["numero"], int) and item["numero"] > 0

    def test_metricas_da_passe(self, db):
        _semear(db)
        passe = _provider(db).buscar_intersecoes("Passagem Teste Ibge")
        assert passe.ancoras >= 2
        assert passe.cruzamentos >= 2
        assert 0.0 < passe.cobertura_eixo <= 1.0
        assert passe.inversoes_numero >= 0

    def test_e_idempotente(self, db):
        _semear(db)
        servico = _provider(db)
        primeira = servico.buscar_intersecoes("Passagem Teste Ibge")
        segunda = servico.buscar_intersecoes("Passagem Teste Ibge")
        assert primeira.intersecoes == segunda.intersecoes

    def test_lat_lng_sao_ignorados(self, db):
        """Paridade de interface: o IBGE identifica a rua pelo nome, não por
        busca espacial."""
        _semear(db)
        servico = _provider(db)
        com = servico.buscar_intersecoes("Passagem Teste Ibge", -1.0, -48.0)
        sem = servico.buscar_intersecoes("Passagem Teste Ibge")
        assert com.intersecoes == sem.intersecoes


class TestPortoesDeVazio:
    def test_rua_inexistente_triagem(self, db):
        _semear(db)
        passe = _provider(db).buscar_intersecoes("Avenida Que Nao Existe Nenhuma")
        assert passe.intersecoes == []
        assert passe.encontrou_rua is False
        assert passe.motivo == "sem_face"

    def test_rua_vazia(self, db):
        _semear(db)
        passe = _provider(db).buscar_intersecoes("   ")
        assert passe.intersecoes == []
        assert passe.motivo == "rua_vazia"

    def test_face_sem_ancoras(self, db):
        _semear(db, ancoras=False)
        passe = _provider(db).buscar_intersecoes("Passagem Teste Ibge")
        assert passe.intersecoes == []
        assert passe.encontrou_rua is True
        assert passe.motivo == "sem_ancora_util"
        assert passe.ancoras == 0

    def test_uma_ancora_so_nao_gera_numero(self, db):
        """Menos de duas âncoras não definem faixa (§6.3) — não se inventa (D2)."""
        _semear(db, faces=(18,))
        db.query(CnefeEnderecoModel).delete()
        inicio, fim = _FACES[18]
        db.add(
            CnefeEnderecoModel(
                cod_municipio=_MUN,
                cod_unico_endereco="unico",
                cod_setor=_SETOR,
                num_quadra=2,
                num_face=18,
                num_endereco=45,
                chave_logradouro=_RUA,
                chave_nome="teste ibge",
                nome_logradouro="Passagem Teste Ibge",
                lat=_entre(inicio, fim, 0.5)[0],
                lng=_entre(inicio, fim, 0.5)[1],
                nv_geo_coord="1",
            )
        )
        db.commit()
        passe = _provider(db).buscar_intersecoes("Passagem Teste Ibge")
        assert passe.intersecoes == []
        assert passe.motivo == "sem_ancora_util"

    def test_geom_invalida_nao_levanta(self, db):
        _semear(db)
        db.add(
            LogradouroFaceModel(
                cod_municipio=_MUN,
                cod_setor=_SETOR,
                cod_quadra=9,
                cod_face=99,
                chave_logradouro=_RUA,
                geom=[["nao", "é", "coordenada"]],
            )
        )
        db.commit()
        passe = _provider(db).buscar_intersecoes("Passagem Teste Ibge")
        assert passe.motivo == "ok"

    def test_numero_nao_numerico_nunca_vira_ancora(self, db):
        _semear(db, faces=(18,))
        db.query(CnefeEnderecoModel).delete()
        inicio, fim = _FACES[18]
        for frac in (0.2, 0.5, 0.8):
            db.add(
                CnefeEnderecoModel(
                    cod_municipio=_MUN,
                    cod_unico_endereco=f"sn-{frac}",
                    cod_setor=_SETOR,
                    num_quadra=2,
                    num_face=18,
                    num_endereco=None,
                    chave_logradouro=_RUA,
                    chave_nome="teste ibge",
                    nome_logradouro="Passagem Teste Ibge",
                    lat=_entre(inicio, fim, frac)[0],
                    lng=_entre(inicio, fim, frac)[1],
                    nv_geo_coord="1",
                )
            )
        db.commit()
        passe = _provider(db).buscar_intersecoes("Passagem Teste Ibge")
        assert passe.intersecoes == []


class TestTolerancia:
    def test_ancora_de_via_paralela_e_descartada(self, db):
        """§8.3.1/§8.8.4: 100 m de deslocamento perpendicular não é âncora."""
        _semear(db, faces=(18,))
        db.query(CnefeEnderecoModel).delete()
        inicio, fim = _FACES[18]
        quadra = 2
        for frac, numero in ((0.2, 62), (0.5, 45), (0.8, 33)):
            db.add(
                CnefeEnderecoModel(
                    cod_municipio=_MUN,
                    cod_unico_endereco=f"ok-{numero}",
                    cod_setor=_SETOR,
                    num_quadra=quadra,
                    num_face=18,
                    num_endereco=numero,
                    chave_logradouro=_RUA,
                    chave_nome="teste ibge",
                    nome_logradouro="Passagem Teste Ibge",
                    lat=_entre(inicio, fim, frac)[0],
                    lng=_entre(inicio, fim, frac)[1],
                    nv_geo_coord="1",
                )
            )
        # Uma âncora 100 m a leste — número que nunca pode aparecer.
        db.add(
            CnefeEnderecoModel(
                cod_municipio=_MUN,
                cod_unico_endereco="paralela",
                cod_setor=_SETOR,
                num_quadra=quadra,
                num_face=18,
                num_endereco=9999,
                chave_logradouro=_RUA,
                chave_nome="teste ibge",
                nome_logradouro="Passagem Teste Ibge",
                lat=_entre(inicio, fim, 0.5)[0],
                lng=_lateral(_entre(inicio, fim, 0.5), 100.0)[1],
                nv_geo_coord="1",
            )
        )
        db.commit()
        passe = _provider(db).buscar_intersecoes("Passagem Teste Ibge")
        assert 9999 not in [i["numero"] for i in passe.intersecoes]
        assert passe.ancoras == 3

    def test_coordenada_de_qualidade_baixa_nao_entra(self, db):
        """NV_GEO_COORD fora de {1,2} não ancora (§6.2) — filtro medido, não achismo."""
        _semear(db, faces=(18,))
        db.query(CnefeEnderecoModel).delete()
        inicio, fim = _FACES[18]
        for frac, numero in ((0.2, 62), (0.5, 45), (0.8, 33)):
            db.add(
                CnefeEnderecoModel(
                    cod_municipio=_MUN,
                    cod_unico_endereco=f"q-{numero}",
                    cod_setor=_SETOR,
                    num_quadra=2,
                    num_face=18,
                    num_endereco=numero,
                    chave_logradouro=_RUA,
                    chave_nome="teste ibge",
                    nome_logradouro="Passagem Teste Ibge",
                    lat=_entre(inicio, fim, frac)[0],
                    lng=_entre(inicio, fim, frac)[1],
                    nv_geo_coord="5",
                )
            )
        db.commit()
        passe = _provider(db).buscar_intersecoes("Passagem Teste Ibge")
        assert passe.intersecoes == []
        assert passe.ancoras == 0


class TestNomeSemTipo:
    def test_sufixo_casa_o_cache_d27(self, db):
        """O cache guarda "Ivan Leão" e o IBGE tem "Passagem Ivan Leão" (D27)."""
        _semear(db)
        passe = _provider(db).buscar_intersecoes("Teste Ibge")
        assert passe.motivo == "ok"
        assert passe.intersecoes

    def test_sufixo_ambiguo_triagem(self, db):
        """Duas ruas terminando no mesmo sufixo ⇒ não se mistura (D2)."""
        _semear(db)
        db.add(
            LogradouroFaceModel(
                cod_municipio=_MUN,
                cod_setor=_SETOR,
                cod_quadra=7,
                cod_face=1,
                chave_logradouro="travessa teste ibge",
                geom=[list(_FACES[18][0]), list(_FACES[18][1])],
            )
        )
        db.commit()
        passe = _provider(db).buscar_intersecoes("Teste Ibge")
        assert passe.intersecoes == []
        assert passe.encontrou_rua is False
        assert passe.motivo == "sem_face"


class TestNuncaLevanta:
    def test_entrada_hostil_nao_estoura(self, db):
        _semear(db)
        servico = _provider(db)
        for entrada in (None, "", "   ", "0", "<script>"):
            passe = servico.buscar_intersecoes(entrada)
            assert isinstance(passe.intersecoes, list)

    def test_municipio_sem_dado(self, db):
        _semear(db)
        servico = IbgeEntreRuasProvider(db, cod_municipio="9999999")
        passe = servico.buscar_intersecoes("Passagem Teste Ibge")
        assert passe.intersecoes == []
        assert passe.encontrou_rua is False
