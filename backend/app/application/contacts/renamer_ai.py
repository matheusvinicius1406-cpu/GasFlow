"""Renomeador de contatos com IA — camada opcional sobre o parser determinístico.

Hierarquia (decisão de privacidade + desempenho):

1. ``renamer.renomear()`` — determinístico, offline, <1s para a agenda inteira.
   É a fonte primária e continua obrigatório: nenhum contato é reescrito só
   porque a IA disse (quando o determinístico já achou endereço).
2. A IA só é consultada para os contatos marcados por :func:`precisa_ia` — os
   que o parser não conseguiu separar (sem endereço/número/complemento/entre).
3. Camada padrão: **Ollama local** (nada sai do PC). A Hugging Face (``hf``)
   existe como opção opt-in e passa por :func:`anonimizar` antes de qualquer
   chamada externa — telefone/jid saem do payload.
4. :func:`validar` aplica o princípio "nada é inventado": todo dígito citado
   pela IA precisa existir no nome bruto. Se a saída não passar, devolvemos
   ``None`` e o chamador fica com o resultado determinístico.

O prompt NÃO contém exemplos com valores reais (modelo pequeno copia o
exemplo literal e o devolve como dado — medido no benchmark local).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app.domain.ai.provider import LLMMessage, LLMProvider, LLMRole

# Telefone completo (E.164/BR) e sequências longas: removidos antes de sair do
# PC. Dígitos de logradouro (1–4) ficam — são endereço, não identificador.
_TELEFONE = re.compile(r"(?<!\d)(?:\+?55)?\d{9,15}(?!\d)")
_JID = re.compile(r"@(?:s\.whatsapp\.net|g\.us|lid)\b", re.IGNORECASE)
# Número com formatação de telefone (932-478-141 / 041-919-81578147).
_TELEFONE_FORMATADO = re.compile(r"(?<!\d)\d{2,4}[-.\s]\d{2,4}[-.\s]\d{3,9}(?!\d)")

_NUMERO = re.compile(r"^Nº\s*\d{1,6}[A-Za-z]?(?:\s*/\s*\d{1,4})?$")
_FENCES = re.compile(r"```(?:json)?\s*|\s*```", re.IGNORECASE)

_SYSTEM = (
    "RENOMEADOR DE CONTATOS DE UMA AGENDA DE GAS.\n"
    "Entrada: array JSON de nomes brutos de contatos.\n"
    "Saida: array JSON, um objeto por entrada, com ESTAS chaves exatas:\n"
    '- "excluir": true SOMENTE se for telefone puro, portaria, pix, pesquisa\n'
    "  de precos, trote, spc ou ligacao descartavel; caso contrario false.\n"
    '- "nome": nome da pessoa, sem trecho de endereco; null se nao houver.\n'
    '- "nome_curto": primeiro nome da pessoa; null se nao houver.\n'
    '- "endereco": rua/logradouro; null se nao houver.\n'
    '- "numero": logradouro numerado, no formato letra N seguida do simbolo\n'
    "  de grau e os digitos do imovel (sem espaco entre elas); null se nao\n"
    "  houver numero.\n"
    '- "complemento": bloco, quadra, apto, casa ou torre, separados por\n'
    "  virgula (ex.: Bloco 1, Apto 101); null se nao houver.\n"
    '- "entre_ruas": "Entre <via1> e <via2>" quando houver; null se nao.\n'
    '- "referencia": referencia ja presente no nome bruto; null se nao houver.\n'
    '- "nome_final_contato": endereco, numero, complemento e entre_ruas nessa\n'
    "  ordem, depois ' - ' e o nome da pessoa (use so o que existir).\n"
    "REGRAS OBRIGATORIAS:\n"
    "1. NAO invente nada. Todo digito citado deve existir no nome bruto.\n"
    "2. NAO copie formato de exemplo: monte a saida a partir dos dados.\n"
    "3. Sem endereco, devolva endereco null e nome_final_contato igual ao\n"
    "   nome bruto (mesmo que pareca sujo).\n"
    "4. Responda SOMENTE com o array JSON, sem cercas de codigo e sem texto."
)

_CHAVAS = (
    "excluir",
    "nome",
    "nome_curto",
    "endereco",
    "numero",
    "complemento",
    "entre_ruas",
    "referencia",
    "nome_final_contato",
)


# ── Entrada: quem precisa de IA ────────────────────────────────────────────


def precisa_ia(resultado: Dict[str, Any]) -> bool:
    """True quando o parser determinístico não achou endereço nenhum.

    É a única situação em que a IA agrega valor; quando o determinístico já
    separou rua/número/complemento, perguntar à IA só custa latência e risco
    de alucinação.
    """
    if resultado.get("excluido"):
        return False
    return not any(resultado.get(campo) for campo in ("endereco", "numero", "complemento", "entre_ruas"))


# ── Privacidade ────────────────────────────────────────────────────────────


def anonimizar(bruto: str) -> str:
    """Remove telefone/jid do texto antes de qualquer chamada externa.

    Dígitos de logradouro (1 a 4 dígitos) são preservados: são endereço.
    """
    texto = _JID.sub(" ", bruto)
    texto = _TELEFONE_FORMATADO.sub(" <telefone> ", texto)
    texto = _TELEFONE.sub(" <telefone> ", texto)
    return re.sub(r"\s+", " ", texto).strip()


# ── Prompt ─────────────────────────────────────────────────────────────────


def montar_mensagens(brutos: Sequence[str]) -> List[LLMMessage]:
    """Monta o par (system, user) para um lote de nomes brutos."""
    entrada = json.dumps([anonimizar(b) for b in brutos], ensure_ascii=False)
    return [
        LLMMessage(role=LLMRole.SYSTEM, content=_SYSTEM),
        LLMMessage(role=LLMRole.USER, content=entrada),
    ]


# ── Parsing da resposta ────────────────────────────────────────────────────


def extrair_json(texto: str) -> Optional[Any]:
    """Extrai o primeiro JSON (array ou objeto) de uma resposta de modelo."""
    if not texto:
        return None
    limpo = _FENCES.sub(" ", texto).strip()
    for candidato in (
        limpo,
        limpo[limpo.find("[") :] if "[" in limpo else "",
        limpo[limpo.find("{") :] if "{" in limpo else "",
    ):
        if not candidato:
            continue
        try:
            return json.loads(candidato)
        except (ValueError, TypeError):
            continue
    # Fallback: recorte entre o primeiro [ e o último ].
    ini, fim = limpo.find("["), limpo.rfind("]")
    if 0 <= ini < fim:
        try:
            return json.loads(limpo[ini : fim + 1])
        except (ValueError, TypeError):
            return None
    return None


# ── Validação ("nada é inventado") ─────────────────────────────────────────


def _digitos(texto: str) -> Counter:
    return Counter(c for c in texto if c.isdigit())


def _sem_digitos_novos(campo: str, bruto: str) -> bool:
    """Todo dígito do campo precisa existir no nome bruto (com multiplicidade)."""
    return not (_digitos(campo) - _digitos(bruto))


def validar(bruto: str, dados: Any) -> Optional[Dict[str, Any]]:
    """Valida estritamente um objeto de saída da IA; ``None`` se falhar.

    Rejeita: JSON com chaves erradas, tipos errados, número fora do padrão,
    dígitos inexistentes no original (alucinação) e final absurdamente longo.
    """
    if not isinstance(dados, dict):
        return None
    if any(chave not in dados for chave in _CHAVAS):
        return None
    if not isinstance(dados.get("excluir"), bool):
        return None

    saida: Dict[str, Any] = {"excluir": dados["excluir"]}
    for campo in _CHAVAS:
        if campo == "excluir":
            continue
        valor = dados.get(campo)
        if valor is None:
            saida[campo] = None
            continue
        if not isinstance(valor, str):
            return None
        valor = re.sub(r"\s+", " ", valor).strip(" \t-–—,")
        if not valor:
            saida[campo] = None
            continue
        if len(valor) > max(160, 3 * len(bruto)):
            return None
        if not _sem_digitos_novos(valor, bruto):
            return None
        saida[campo] = valor

    # Formato do número já passou pelo corte de dígitos novos no laço acima;
    # aqui só garante o padrão "N" + símbolo de grau + dígitos.
    numero = saida.get("numero")
    if numero is not None and not re.match(r"^Nº\s*\d", numero):
        return None

    if not saida.get("nome_final_contato"):
        return None
    if saida["excluir"]:
        return saida
    # Sem endereço nenhum, o determinístico faz melhor: descarta.
    if not any(saida.get(c) for c in ("endereco", "numero", "complemento", "entre_ruas")):
        return None
    return saida


def validar_lote(brutos: Sequence[str], dados: Any, esperados: int) -> Optional[List[Optional[Dict[str, Any]]]]:
    """Valida um lote mantendo 1:1 com a entrada (ordem preservada)."""
    if not isinstance(dados, list) or len(dados) != esperados or len(brutos) != esperados:
        return None
    return [validar(bruto, item) for bruto, item in zip(brutos, dados)]


def renomear_com_ia(
    brutos: Sequence[str],
    provider: LLMProvider,
    lote: int = 8,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Renomeia um conjunto de nomes brutos via IA, com validação estrita.

    Retorna ``{bruto: resultado_validado}``; contatos cuja resposta não passou
    em :func:`validar` simplesmente não entram no dicionário (o chamador mantém
    o resultado determinístico). Nunca levanta exceção.
    """
    saida: Dict[str, Optional[Dict[str, Any]]] = {}
    if not brutos:
        return saida
    for inicio in range(0, len(brutos), max(1, lote)):
        bloco = list(brutos[inicio : inicio + max(1, lote)])
        resposta = provider.generate(montar_mensagens(bloco), temperature=0.1, max_tokens=900)
        if resposta.error or not resposta.content:
            continue
        dados = extrair_json(resposta.content)
        if not isinstance(dados, list) or len(dados) != len(bloco):
            continue
        for bruto, item in zip(bloco, dados):
            validado = validar(bruto, item)
            if validado:
                saida[bruto] = validado
    return saida


def selecionar_para_ia(brutos: Iterable[str], resultados: Dict[str, Dict[str, Any]]) -> List[str]:
    """Filtra os brutos cujo resultado determinístico pede IA."""
    return [b for b in brutos if precisa_ia(resultados.get(b, {}))]
