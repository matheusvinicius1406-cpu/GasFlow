"""`--from-file` do script de renomeação: mapping de IA gerado fora de linha.

A camada `--ia` depende de um provider no momento da operação; o `--from-file`
aceita o MESMO contrato (`{bruto: {excluir, ..., nome_final_contato}}`) já
gravado em JSON — é o caminho do lote C3, revisado à mão sem Ollama.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os

import pytest

_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "renomear_agenda_local.py"
)
_spec = importlib.util.spec_from_file_location("renomear_agenda_local", _SCRIPT)
renomear_agenda = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(renomear_agenda)


def _dados(pendentes):
    return {
        "mudancas": [],
        "excluidos": [],
        "mantidos": len(pendentes),
        "pendentes_ia": pendentes,
    }


def _args(mapping_path):
    return argparse.Namespace(from_file=str(mapping_path), ia=False)


def _resposta(**kwargs):
    base = {
        "excluir": False,
        "nome": None,
        "nome_curto": None,
        "endereco": None,
        "numero": None,
        "complemento": None,
        "entre_ruas": None,
        "referencia": None,
    }
    base.update(kwargs)
    return base


def test_mapping_aplica_nome_final_como_mudanca_ia(tmp_path):
    pendente = {"id": 217, "phone": None, "name": "Mangue 217"}
    mapping = tmp_path / "map.json"
    mapping.write_text(
        json.dumps({"Mangue 217": _resposta(endereco="Mangue", numero="Nº217", nome_final_contato="Mangue Nº217")}),
        encoding="utf-8",
    )
    dados = _dados([pendente])

    stats = renomear_agenda._rodar_ia_de_arquivo(_args(mapping), dados)

    assert stats["aplicados"] == 1
    assert stats["sem_resposta"] == 0
    assert dados["mudancas"] == [
        {
            "id": 217,
            "phone": None,
            "antes": "Mangue 217",
            "depois": "Mangue Nº217",
            "nome": None,
            "endereco": "Mangue",
            "numero": "Nº217",
            "complemento": None,
            "entre_ruas": None,
            "origem": "ia",
        }
    ]
    assert dados["mantidos"] == 0


def test_excluir_true_nao_renomeia_apenas_sinaliza(tmp_path):
    pendente = {"id": 1, "phone": None, "name": "Zap"}
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({"Zap": _resposta(excluir=True, nome_final_contato="Zap")}), encoding="utf-8")
    dados = _dados([pendente])

    stats = renomear_agenda._rodar_ia_de_arquivo(_args(mapping), dados)

    assert stats["ignorados"] == 1
    assert stats["aplicados"] == 0
    assert dados["mudancas"] == []
    assert dados["mantidos"] == 1


def test_sem_endereco_ou_igual_ao_bruto_conta_como_ignorado(tmp_path):
    pendentes = [
        {"id": 2, "phone": None, "name": "Lilia Gas"},
        {"id": 3, "phone": None, "name": "= Top Gas"},
    ]
    mapping = tmp_path / "map.json"
    # Regra 3 do prompt: sem endereço, o final é o bruto — e o bruto == atual.
    mapping.write_text(
        json.dumps(
            {
                "Lilia Gas": _resposta(nome_final_contato="Lilia Gas"),
                "= Top Gas": _resposta(nome_final_contato="Top Gas"),
            }
        ),
        encoding="utf-8",
    )
    dados = _dados(pendentes)

    stats = renomear_agenda._rodar_ia_de_arquivo(_args(mapping), dados)

    assert stats["aplicados"] == 1
    assert stats["ignorados"] == 1
    assert [m["depois"] for m in dados["mudancas"]] == ["Top Gas"]


def test_bruto_ausente_do_mapping_conta_como_sem_resposta(tmp_path):
    pendente = {"id": 4, "phone": None, "name": "Surper Gas ( Wagner )"}
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({}), encoding="utf-8")
    dados = _dados([pendente])

    stats = renomear_agenda._rodar_ia_de_arquivo(_args(mapping), dados)

    assert stats["sem_resposta"] == 1
    assert stats["aplicados"] == 0
    assert dados["mudancas"] == []


def test_from_file_e_ia_sao_excludentes(monkeypatch):
    def _falha():
        raise AssertionError("não deveria chegar no --ia")

    monkeypatch.setattr(renomear_agenda, "_rodar_ia", lambda _a, _d: _falha())
    monkeypatch.setattr(renomear_agenda, "_carregar_contatos", lambda _c: [{"id": 1, "name": "X", "phone": None}])
    monkeypatch.setattr(renomear_agenda, "planejar", lambda _c: _dados([]))
    monkeypatch.setattr(
        renomear_agenda, "_rodar_ia_de_arquivo", lambda _a, _d: (_ for _ in ()).throw(SystemExit("--x"))
    )
    monkeypatch.setattr("os.path.isfile", lambda _p: True)
    monkeypatch.setattr("sqlite3.connect", lambda _p: _FakeCon())
    monkeypatch.setattr(
        "sys.argv",
        ["renomear_agenda_local.py", "--from-file", "map.json", "--ia"],
    )
    with pytest.raises(SystemExit):
        renomear_agenda.main()


class _FakeCon:
    def cursor(self):  # pragma: no cover - nunca usado: main cai antes
        raise AssertionError("não deveria gravar")

    def close(self):
        pass
