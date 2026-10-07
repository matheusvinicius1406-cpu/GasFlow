"""Testes da camada de IA do renomeador (híbrido) — sem rede, sem Ollama.

Cobrem: parsing de JSON de modelo, validação estrita ("nada é inventado"),
anonimização de dados sensíveis antes de sair do PC, seleção dos contatos que
pedem IA, lote 1:1 e degradação graciosa (provider com erro => sem exceção).
"""

import json

from app.application.contacts.renamer import renomear
from app.application.contacts import renamer_ai as ia
from app.domain.ai.provider import LLMProvider, LLMMessage, LLMResponse, LLMRole
from app.infrastructure.ai.huggingface_provider import HuggingFaceProvider


class _StubProvider(LLMProvider):
    """Provider de teste: devolve o que for programado, sem rede."""

    def __init__(self, conteudo: str = "", erro: str | None = None) -> None:
        self._conteudo = conteudo
        self._erro = erro
        self.chamadas = 0

    def generate(self, messages, temperature=0.3, max_tokens=2048) -> LLMResponse:
        self.chamadas += 1
        return LLMResponse(content=self._conteudo, error=self._erro)

    def generate_structured(self, messages, schema, temperature=0.1, max_tokens=1024) -> LLMResponse:
        return self.generate(messages)

    def health_check(self) -> bool:
        return self._erro is None

    @property
    def model_name(self) -> str:
        return "stub"


def _obj(**kw) -> dict:
    base = {
        "excluir": False,
        "nome": None,
        "nome_curto": None,
        "endereco": None,
        "numero": None,
        "complemento": None,
        "entre_ruas": None,
        "referencia": None,
        "nome_final_contato": None,
    }
    base.update(kw)
    return base


# ── Parsing da resposta do modelo ──────────────────────────────────────────


def test_extrair_json_remove_cerca_de_codigo():
    assert ia.extrair_json('```json\n[{"a": 1}]\n```') == [{"a": 1}]


def test_extrair_json_acha_array_no_meio_do_texto():
    assert ia.extrair_json('Claro! Aqui esta: [{"n": "x"}] espero que ajude') == [{"n": "x"}]


def test_extrair_json_retorna_none_quando_sem_json():
    assert ia.extrair_json("nao sei processar isso") is None
    assert ia.extrair_json("") is None


# ── Validação (nada é inventado) ───────────────────────────────────────────


def test_validar_aceita_saida_correta():
    bruto = "Nelma Martins Pass.Triangulo N 77"
    dados = _obj(
        nome="Nelma Martins",
        endereco="Pass.Triangulo",
        numero="Nº77",
        nome_final_contato="Pass.Triangulo Nº77 - Nelma Martins",
    )
    saida = ia.validar(bruto, dados)
    assert saida is not None
    assert saida["numero"] == "Nº77"
    assert saida["nome_final_contato"].endswith("- Nelma Martins")


def test_validar_rejeita_digito_inventado():
    """Número que não existe no nome bruto = alucinação (medido no benchmark)."""
    bruto = "Ico Gas 7 Rua"
    dados = _obj(endereco="Ico Gas", numero="Nº16", nome_final_contato="Ico Gas Nº16")
    assert ia.validar(bruto, dados) is None


def test_validar_rejeita_digito_inventado_em_campos_de_texto():
    bruto = "Pass Maura N 300"
    dados = _obj(endereco="Pass Maura", numero="Nº300", complemento="Bloco 42")
    assert ia.validar(bruto, dados) is None  # "42" não está no bruto


def test_validar_rejeita_chave_faltando():
    bruto = "Rua A 10"
    dados = {"endereco": "Rua A", "numero": "Nº10"}  # faltam as demais chaves
    assert ia.validar(bruto, dados) is None


def test_validar_rejeita_tipo_errado():
    bruto = "Rua A 10"
    dados = _obj(endereco="Rua A", numero="Nº10", excluir="sim")  # excluir deve ser bool
    assert ia.validar(bruto, dados) is None


def test_validar_rejeita_numero_fora_do_padrao():
    bruto = "Pass Maura 300"
    dados = _obj(endereco="Pass Maura", numero="300", nome_final_contato="Pass Maura 300")
    assert ia.validar(bruto, dados) is None


def test_validar_rejeita_quando_nao_ha_endereco():
    """Sem endereço, o determinístico faz melhor — descarta a resposta da IA."""
    bruto = "Surper Gas ( Wagner )"
    dados = _obj(nome="Wagner", nome_final_contato="Wagner")
    assert ia.validar(bruto, dados) is None


def test_validar_permite_excluir_true_sem_endereco():
    bruto = "Pix Portaria"
    dados = _obj(excluir=True, nome_final_contato="Pix Portaria")
    saida = ia.validar(bruto, dados)
    assert saida is not None
    assert saida["excluir"] is True


def test_validar_rejeita_final_vazio():
    bruto = "Rua A 10"
    dados = _obj(endereco="Rua A", numero="Nº10", nome_final_contato=None)
    assert ia.validar(bruto, dados) is None


# ── Privacidade ────────────────────────────────────────────────────────────


def test_anonimizar_remove_telefone_e_preserva_numero_de_logradouro():
    texto = "5511999999999 Fulano Rua X 123"
    saida = ia.anonimizar(texto)
    assert "5511999999999" not in saida
    assert "123" in saida  # número da casa permanece


def test_anonimizar_remove_jid_e_telefone_formatado():
    assert "932" not in ia.anonimizar("Fulano 932-478-141").replace("-", "").split(" ")[0]
    assert "@s.whatsapp.net" not in ia.anonimizar("Fulano@s.whatsapp.net Rua A")


def test_prompt_nao_contem_exemplo_literal_de_numero():
    """Modelo pequeno copia o exemplo literal do prompt e o devolve como dado."""
    assert "Nº16" not in ia._SYSTEM


def test_montar_mensagens_anonimiza_a_entrada():
    mensagens = ia.montar_mensagens(["5511988887777 Rua A 10"])
    assert mensagens[0].role is LLMRole.SYSTEM
    assert "5511988887777" not in mensagens[1].content


# ── Seleção de quem precisa de IA ──────────────────────────────────────────


def test_precisa_ia_quando_nao_ha_endereco():
    assert ia.precisa_ia(renomear("Surper Gas ( Wagner )")) is True


def test_nao_precisa_ia_quando_ha_endereco():
    assert ia.precisa_ia(renomear("2811= Cohab S5 Casa 249 (Mary)")) is False


def test_nao_precisa_ia_para_contato_excluido():
    assert ia.precisa_ia(renomear("Pix Portaria")) is False


# ── Lote ───────────────────────────────────────────────────────────────────


def test_renomear_com_ia_valida_o_lote():
    brutos = ["Nelma Martins Pass.Triangulo N 77", "Pass Maura N 300"]
    resposta = json.dumps(
        [
            _obj(
                nome="Nelma Martins",
                endereco="Pass.Triangulo",
                numero="Nº77",
                nome_final_contato="Pass.Triangulo Nº77 - Nelma Martins",
            ),
            _obj(
                nome="Pass Maura",
                endereco="Pass Maura",
                numero="Nº300",
                nome_final_contato="Pass Maura Nº300",
            ),
        ]
    )
    stub = _StubProvider(conteudo=resposta)
    saida = ia.renomear_com_ia(brutos, stub, lote=8)
    assert len(saida) == 2
    assert saida[brutos[0]]["numero"] == "Nº77"
    assert stub.chamadas == 1


def test_renomear_com_ia_descarta_item_invalido_e_mantem_ordem():
    brutos = ["Pass Maura N 300", "Ico Gas 7 Rua"]
    resposta = json.dumps(
        [
            _obj(endereco="Pass Maura", numero="Nº300", nome_final_contato="Pass Maura Nº300"),
            _obj(endereco="Ico Gas", numero="Nº16", nome_final_contato="Ico Gas Nº16"),  # alucinou
        ]
    )
    saida = ia.renomear_com_ia(brutos, _StubProvider(conteudo=resposta))
    assert brutos[0] in saida
    assert brutos[1] not in saida


def test_renomear_com_ia_nao_lanca_quando_o_provider_falha():
    assert ia.renomear_com_ia(["Rua A 10"], _StubProvider(erro="LLM_UNAVAILABLE:ConnectError")) == {}
    assert ia.renomear_com_ia(["Rua A 10"], _StubProvider(conteudo="desculpe, nao entendi")) == {}
    assert ia.renomear_com_ia([], _StubProvider()) == {}


def test_renomear_com_ia_respeta_o_tamanho_do_lote():
    brutos = [f"Rua A {n}" for n in range(1, 6)]
    resposta = json.dumps([_obj(endereco="Rua A", nome_final_contato="Rua A") for _ in range(5)])
    stub = _StubProvider(conteudo=resposta)
    ia.renomear_com_ia(brutos, stub, lote=2)
    assert stub.chamadas == 3  # 2 + 2 + 1


# ── Provider Hugging Face ──────────────────────────────────────────────────


def test_hf_sem_token_devolve_erro_e_nao_chama_rede():
    provedor = HuggingFaceProvider(api_token="")
    assert provedor.health_check() is False
    resposta = provedor.generate([LLMMessage(role=LLMRole.USER, content="oi")])
    assert resposta.error == "HF_MISSING_TOKEN"


def test_hf_repr_nao_vaza_o_token():
    provedor = HuggingFaceProvider(api_token="hf_segredo_super_secreto")
    assert "hf_segredo_super_secreto" not in repr(provedor)
    assert "<oculto>" in repr(provedor)
