"""Renomeador de contatos — regras do prompt (§1–§8).

Cobre o módulo puro `app.application.contacts.renamer`: exclusões, número
sempre `Nº<digit>`, complementos, "entre ruas", nome da pessoa e o
`nome_final_contato` no padrão combinado (endereço + Nº + complemento + nome).
"""

from collections import Counter

from app.application.contacts.renamer import motivo_exclusao, nome_curto, renomear


# ═══════════════════════════════════════════════════════════
# §4 — Exclusões
# ═══════════════════════════════════════════════════════════


class TestExclusoes:
    def test_so_numero(self):
        assert motivo_exclusao("041-919-81578147") == "numero"
        assert motivo_exclusao("932-478-141") == "numero"

    def test_portaria_pix_pesquisa_concorrente(self):
        assert motivo_exclusao("Portaria") == "portaria"
        assert motivo_exclusao("Pix Portaria") == "pix"
        assert motivo_exclusao("Portal Gas Pesquisa") == "pesquisa"
        assert motivo_exclusao("Concorrente Ligue") == "concorrente"

    def test_outros_operacionais(self):
        assert motivo_exclusao("Na última") == "na_ultima"
        assert motivo_exclusao("SPC") == "spc"
        assert motivo_exclusao("Cliente Novo") == "cliente_novo"

    def test_cliente_real_nao_e_excluido(self):
        assert motivo_exclusao("Rafaele") is None
        assert motivo_exclusao("Cohab Tv L4 Nº204 (Socorro)") is None

    def test_excluido_marca_flag(self):
        r = renomear("Pix Soledade")
        assert r["excluido"] is True
        assert r["motivo"] == "pix"
        assert r["original"] == "Pix Soledade"


# ═══════════════════════════════════════════════════════════
# §6 — Exemplos de transformação (adaptados ao padrão combinado)
# ═══════════════════════════════════════════════════════════


class TestExemplosDoPrompt:
    def test_numero_entre_ruas(self):
        r = renomear("15 De Agosto N⁰ 16 (Pimenta E Cruzeiro) (Rafaele)")
        assert r["nome"] == "Rafaele"
        assert r["endereco"] == "15 De Agosto"
        assert r["numero"] == "Nº16"
        assert r["complemento"] is None
        assert r["entre_ruas"] == "Entre Pimenta e Cruzeiro"
        assert r["nome_final_contato"] == "15 De Agosto Nº16 Entre Pimenta e Cruzeiro - Rafaele"

    def test_complemento_bloco_apto(self):
        r = renomear("Paricás Rua: 07 Bl: 62 Apto: 101( Mailson)")
        assert r["nome"] == "Mailson"
        assert r["endereco"] == "Paricás Rua 07"
        assert r["numero"] is None
        assert r["complemento"] == "Bloco 62, Apto 101"
        assert r["nome_final_contato"] == "Paricás Rua 07 Bloco 62 Apto 101 - Mailson"

    def test_ordinal_queda_de_rua(self):
        r = renomear("5 Rua Q- 06 Bl:124 Apto: 202 ( Kamily)")
        assert r["nome"] == "Kamily"
        assert r["endereco"] == "5ª Rua"
        assert r["complemento"] == "Quadra 06, Bloco 124, Apto 202"
        assert r["nome_final_contato"] == "5ª Rua Quadra 06 Bloco 124 Apto 202 - Kamily"

    def test_cohab_tv(self):
        r = renomear("Cohab Tv: L4 N⁰ 204 (Socorro)")
        assert r["nome"] == "Socorro"
        assert r["endereco"] == "Cohab Tv L4"
        assert r["numero"] == "Nº204"
        assert r["nome_final_contato"] == "Cohab Tv L4 Nº204 - Socorro"

    def test_referencia_no_parenteses(self):
        r = renomear("A. Montenegro N° 160 ( Pm Box E 7 Rua) Anderson")
        assert r["nome"] == "Anderson"
        assert r["endereco"] == "A. Montenegro"
        assert r["numero"] == "Nº160"
        assert r["entre_ruas"] is None
        assert r["referencia"] == "Pm Box E 7 Rua"
        assert r["nome_final_contato"] == "A. Montenegro Nº160 Pm Box E 7 Rua - Anderson"

    def test_entre_de_ordinais(self):
        r = renomear("Pass: Maura N° 300 ( 3° E 4 ° Rua) Danuzia Ou Kelide)")
        assert r["nome"] == "Danuzia Ou Kelide"
        assert r["endereco"] == "Pass Maura"
        assert r["numero"] == "Nº300"
        assert r["entre_ruas"] == "Entre 3ª e 4ª Rua"
        assert r["nome_final_contato"] == "Pass Maura Nº300 Entre 3ª e 4ª Rua - Danuzia Ou Kelide"

    def test_casa_e_entre_ruas(self):
        r = renomear("5 Rua Al: Castanheira N⁰ 981/ Casa N⁰ 05 (Itaboraí E S. Roque) (Jhony)")
        assert r["nome"] == "Jhony"
        assert r["endereco"] == "5ª Rua Al Castanheira"
        assert r["numero"] == "Nº981"
        assert r["complemento"] == "Casa 05"
        assert r["entre_ruas"] == "Entre Itaboraí e S. Roque"
        assert r["nome_final_contato"] == ("5ª Rua Al Castanheira Nº981 Casa 05 Entre Itaboraí e S. Roque - Jhony")


# ═══════════════════════════════════════════════════════════
# Regras transversais
# ═══════════════════════════════════════════════════════════


class TestRegras:
    def test_codigo_legado_removido(self):
        r = renomear("1628= 3⁰ Rua N⁰ 1758 (Soledade E Andradas) Ewerton (Cláudia)")
        assert r["endereco"] == "3ª Rua"
        assert r["numero"] == "Nº1758"
        assert r["nome"] == "Cláudia"
        assert "1628=" not in r["nome_final_contato"]

    def test_numero_sempre_com_o_simbolo_n_ordinal_junto(self):
        r = renomear("2 Rua Da Campina Nº 195 Fundos")
        assert r["numero"] == "Nº195"
        assert "Nº 195" not in r["nome_final_contato"]

    def test_tratamento_preservado_no_nome_curto(self):
        assert nome_curto("Dona Maria Do Carmo") == "Dona Maria"
        assert nome_curto("Senhor Antônio Carlos") == "Senhor Antônio"
        assert nome_curto("Rafaele") == "Rafaele"

    def test_sem_nome_usa_endereco(self):
        r = renomear("Andradas AL: Visconde De Mauá N° 08")
        assert r["nome"] is None
        assert r["numero"] == "Nº08"
        assert r["nome_final_contato"] == "Andradas AL Visconde De Mauá Nº08"

    def test_vazio_nao_quebra(self):
        assert renomear(None)["nome_final_contato"] == ""
        assert renomear("   ")["alterado"] is False

    def test_idempotente(self):
        saida = renomear("5 Rua Q- 06 Bl:124 Apto: 202 ( Kamily)")["nome_final_contato"]
        assert renomear(saida)["nome_final_contato"] == saida
        assert renomear(saida)["alterado"] is False


# ═══════════════════════════════════════════════════════════
# Nome antes do endereço (o padrão "Fulano Rua X Nº…")
# ═══════════════════════════════════════════════════════════


class TestNomeEsquerda:
    def test_tratamento_antes_do_endereco(self):
        r = renomear("Dona Ketelyn Pass Da Flores  Al Texeira Casa 94")
        assert r["nome"] == "Dona Ketelyn"
        assert r["endereco"] == "Pass Da Flores Al Texeira"
        assert r["complemento"] == "Casa 94"
        assert r["nome_final_contato"] == "Pass Da Flores Al Texeira Casa 94 - Dona Ketelyn"

    def test_logradouro_de_duas_palavras_nao_vira_nome(self):
        # Sem tratamento, "Souza Franco" é rua — não nome de pessoa.
        r = renomear("Souza Franco Al Zizi Casa 23")
        assert r["nome"] is None
        assert r["endereco"] == "Souza Franco Al Zizi"
        assert r["nome_final_contato"] == "Souza Franco Al Zizi Casa 23"

    def test_bairro_no_inicio_nao_vira_nome(self):
        r = renomear("Recanto Verde Alameda C N° 3")
        assert r["nome"] is None
        assert r["numero"] == "Nº3"
        assert r["nome_final_contato"] == "Recanto Verde Alameda C Nº3"

    def test_rua_no_inicio_nao_vira_nome(self):
        r = renomear("Andradas AL: Visconde De Mauá N° 08")
        assert r["nome"] is None
        assert r["nome_final_contato"] == "Andradas AL Visconde De Mauá Nº08"

    def test_referencia_com_ponto_e_reconhecida(self):
        r = renomear("Pass Espírito Santo N° 03 (Próx. Pass Livramento) (Pablo)")
        assert r["referencia"] == "Próx. Pass Livramento"
        assert r["nome"] == "Pablo"
        assert r["nome_final_contato"] == "Pass Espírito Santo Nº03 Próx. Pass Livramento - Pablo"


# ═══════════════════════════════════════════════════════════
# Reprocessar a própria saída não pode apagar nem duplicar dado
# ═══════════════════════════════════════════════════════════

# Nomes JÁ formatados (reais, da agenda local) em que o parser precisa separar
# endereço, número, complemento, referência e nome sem deixar nada de fora.
JA_FORMATADOS = [
    "Conjunto Vale Azul Quadra 4 Casa 98 Próximo A Igreja",
    "Souza Franco N°1475 Próx. Da Assembleia De Deus",
    "Al. São Paulo N°11 Parque Guajará - Luis Klaus",
    "São Vicente N°120 - Entrando Pela 8 De Maio",
    "Arinos Noronha Travessa São Roque N°60 - Entre 1ªe 2ªRua",
    "Rua Moura Carvalho N°52 Frente A Rua N3 - Neide",
    "Pass Ferreira N°12 - Esqui: Castelo Branco",
    "2ª Vila Dos Inocentes Pass Sta Rosa N°40 Xodé Da Vila",
    "Soledade N°76 Em Frente A Creche - Dona Sômia",
    "S. Roque N°897 Passando A Borracharia Entre 5/6 Rua - Maria De Fátima",
    "S. Franco N°1720 - Ivan Leão D. Coen",
    "Maria Anete Travessa Soledade N°560 - 3ªe 4ª",
    "Buraco Fundo Passagem São Luís Dona Josi N°5",
    "4525 Dona Inês Rua W5 N°140",
    "Montenegro Dona Cristina Ao Lado Do Colégio Samatório N°85",
    "arletevasconcelos20 Passagem São Miguel N°20 Rua 8 de Maio",
]


def _digitos(texto: str) -> Counter:
    return Counter(c for c in texto if c.isdigit())


class TestReprocessamentoNaoCorrompe:
    """Reaplicar o parser sobre a própria saída: sem apagar, sem duplicar."""

    def test_reprocessar_e_estavel(self):
        for bruto in JA_FORMATADOS:
            uma = renomear(bruto)["nome_final_contato"]
            duas = renomear(uma)["nome_final_contato"]
            assert duas == uma, f"não idempotente: {bruto!r} -> {uma!r} -> {duas!r}"

    def test_nenhum_digito_some(self):
        for bruto in JA_FORMATADOS:
            saida = renomear(bruto)["nome_final_contato"]
            faltando = _digitos(bruto) - _digitos(saida)
            assert not faltando, f"{bruto!r} perdeu {list(faltando)} -> {saida!r}"

    def test_nome_extraido_nao_duplica(self):
        # "… Dona Josi N°5": aceitar o match inteiro DUPLICAVA o nome no final.
        for bruto in JA_FORMATADOS:
            r = renomear(bruto)
            if not r["nome"]:
                continue
            assert r["nome_final_contato"].count(r["nome"]) == 1, bruto

    def test_cauda_sem_nome_e_preservada(self):
        # Referência sem parêntese e sem travessão antes era descartada.
        saida = renomear("Conjunto Vale Azul Quadra 4 Casa 98 Próximo A Igreja")
        assert "Próximo A Igreja" in saida["nome_final_contato"]

    def test_palavra_de_via_isolada_nao_some(self):
        # O número vem no meio: separar em "Cohab" não pode derrubar a palavra.
        saida = renomear("Cohab N\u2070 92 N°6 - Conceição")
        assert "Cohab" in saida["nome_final_contato"]
        assert "92" in saida["nome_final_contato"]

    def test_nome_a_esquerda_converge_sem_perder_nada(self):
        uma = renomear("Dona Jony Castro Alves N°141 - Perto Da Funai")
        duas = renomear(uma["nome_final_contato"])
        tres = renomear(duas["nome_final_contato"])
        assert tres["nome_final_contato"] == duas["nome_final_contato"]
        for parte in ("Castro Alves", "Perto Da Funai", "Dona Jony"):
            assert parte in uma["nome_final_contato"]
