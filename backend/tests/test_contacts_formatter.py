"""Fase 2 §9 — Formatter do nome de rota (etapa 7): padrão, fallbacks e idempotência.

Estratégia: funções puras, sem banco. A integração com o organizer
(`pattern_endereco`) fica em `test_contacts_organizer.py`, que já tem o fake.
"""

from __future__ import annotations

from app.application.contacts.formatter import (
    formatar_nome_rota,
    limpar_codigo,
    nome_da_pessoa,
)
from app.domain.client.entity import Client


def _cliente(codigo: str = "000001", nome: str = "Maria", **kwargs) -> Client:
    return Client(
        codigo=codigo,
        nome=nome,
        telefone=kwargs.get("telefone", "11999990001"),
        rua=kwargs.get("rua", "Travessa São Roque"),
        numero=kwargs.get("numero", "145"),
        bairro=kwargs.get("bairro", "Centro"),
        **{k: v for k, v in kwargs.items() if k not in ("telefone", "rua", "numero", "bairro")},
    )


# ═══════════════════════════════════════════════════════════
# 1. Formato completo (D5)
# ═══════════════════════════════════════════════════════════


class TestFormatoCompleto:
    def test_monta_todos_os_trechos(self):
        c = _cliente(has_name=True, entre_ruas="Rua A e Rua B", cep="66811-120")

        assert formatar_nome_rota(c) == "1= Travessa São Roque Nº 145 entre Rua A e Rua B - CEP 66811-120 (Maria)"

    def test_codigo_sai_sem_zeros_a_esquerda(self):
        # D7: o banco guarda 6 dígitos, o nome usa a forma curta.
        c = _cliente(codigo="000042", has_name=False)

        assert formatar_nome_rota(c).startswith("42= ")


# ═══════════════════════════════════════════════════════════
# 2. Fallbacks (D2): nada é inventado
# ═══════════════════════════════════════════════════════════


class TestFallbacks:
    def test_sem_entre_omite_o_trecho(self):
        c = _cliente(has_name=True, entre_ruas="", cep="66811-120")

        assert formatar_nome_rota(c) == "1= Travessa São Roque Nº 145 - CEP 66811-120 (Maria)"

    def test_sem_cep_omite_o_trecho(self):
        c = _cliente(has_name=True, entre_ruas="Rua A e Rua B", cep="")

        assert formatar_nome_rota(c) == "1= Travessa São Roque Nº 145 entre Rua A e Rua B (Maria)"

    def test_sem_nome_de_pessoa_omite_o_sufixo(self):
        # has_name = None/False → o placeholder do import não vira sufixo.
        c = _cliente(nome="Contato 11999990001", has_name=False, cep="66811-120")

        assert formatar_nome_rota(c) == "1= Travessa São Roque Nº 145 - CEP 66811-120"

    def test_entre_ruas_injetado_tem_precedencia(self):
        c = _cliente(has_name=False, entre_ruas="antigo")

        assert formatar_nome_rota(c, entre_ruas="Rua C e Rua D") == ("1= Travessa São Roque Nº 145 entre Rua C e Rua D")

    def test_sem_rua_renderiza_so_o_que_existe(self):
        c = _cliente(rua="", numero="", has_name=True)

        assert formatar_nome_rota(c) == "1= (Maria)"


# ═══════════════════════════════════════════════════════════
# 3. Idempotência (§9): aplicar duas vezes não empilha
# ═══════════════════════════════════════════════════════════


class TestIdempotencia:
    def test_formatar_o_proprio_resultado_e_estavel(self):
        c = _cliente(has_name=True, entre_ruas="Rua A e Rua B", cep="66811-120")

        primeiro = formatar_nome_rota(c)
        c.nome = primeiro
        segundo = formatar_nome_rota(c)

        assert segundo == primeiro

    def test_rota_sem_sufixo_nao_duplica_o_endereco(self):
        c = _cliente(nome="1= Travessa São Roque Nº 145", has_name=True)

        # Sem `(...)` no nome, a pessoa não é recuperável: omite em vez de
        # repetir o endereço como se fosse gente.
        assert formatar_nome_rota(c) == "1= Travessa São Roque Nº 145"

    def test_codigo_legado_no_nome_e_descartado(self):
        # D1: o código antigo colado ao nome nunca é copiado.
        assert limpar_codigo("1443= berredos 145") == "berredos 145"
        c = _cliente(nome="114= rua antiga Nº 10", has_name=True, cep="66811-120")

        assert formatar_nome_rota(c) == "1= Travessa São Roque Nº 145 - CEP 66811-120"

    def test_nome_da_pessoa_extrai_do_sufixo(self):
        assert nome_da_pessoa(_cliente(nome="Maria")) == "Maria"
        assert nome_da_pessoa(_cliente(nome="1= rua X Nº 145 (João)")) == "João"
        assert nome_da_pessoa(_cliente(nome="1= rua X Nº 145")) == ""
