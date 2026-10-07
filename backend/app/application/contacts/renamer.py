r"""
Renomeador de contatos — nome bruto da agenda → nome final de rota.

Implementa, de forma **determinística e offline** (sem LLM/API), as regras do
prompt do renomeador (§1–§8). O caso de uso é a agenda do WhatsApp da revenda,
onde o ``name`` do contato é um amontoado de código + endereço + complemento +
nome da pessoa:

    "1628= 3⁰ Rua N⁰ 1758 (Soledade E Andradas) Ewerton (Cláudia)"
    "5 Rua Q- 06 Bl:124 Apto: 202 ( Kamily)"
    "Cohab Tv: L4 N⁰ 204 (Socorro)"

O que sai é o ``nome_final_contato`` no padrão combinado com a operação
(**endereço + Nº + complemento + nome do cliente**), que é o texto que volta
para a agenda:

    "3ª Rua Nº1758 Entre Soledade e Andradas - Cláudia"
    "5ª Rua Quadra 06 Bloco 124 Apto 202 - Kamily"
    "Cohab Tv L4 Nº204 - Socorro"

Regras de ouro (mesmas do resto do domínio de contatos):

- **Nada é inventado.** Campo que não aparece na string sai ``None``; o contato
  cuja string não rende endereço nem nome fica intacto (``renomear`` devolve o
  próprio bruto como ``nome_final_contato``).
- **Número sempre ``Nº<digit>``** — sem espaço, com ``º`` (nunca ``N°``/``N⁰``).
- **Exclusão antes de tudo**: contato de teste/operacional (``Pix``, ``Portaria``,
  ``Pesquisa``, ``Concorrente``, só número…) não é renomeado, apenas sinalizado.
- **Idempotência**: renomear um nome já no padrão devolve o mesmo texto.

Módulo puro (sem banco, sem I/O), consumido pelo script local
``scripts/renomear_agenda_local.py`` e testável isoladamente.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════
# Normalização
# ═══════════════════════════════════════════════════════════


def _sem_acento(texto: str) -> str:
    """Remove acentos preservando as letras (``Itaboraí`` → ``Itaborai``)."""
    decomposto = unicodedata.normalize("NFD", texto or "")
    return "".join(ch for ch in decomposto if unicodedata.category(ch) != "Mn")


def _chave(texto: str) -> str:
    """Forma canônica para comparar sem acento e sem caixa."""
    return re.sub(r"\s+", " ", _sem_acento(texto or "").lower()).strip()


def _normaliza_espacos(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


def _limpa_pontas(texto: str) -> str:
    return _normaliza_espacos(texto).strip(" -.,;:()/")


# ═══════════════════════════════════════════════════════════
# §4 — Exclusões (contatos que NÃO são renomeados)
# ═══════════════════════════════════════════════════════════

# Ordem importa: o primeiro que casar define o motivo. ``numero`` vem primeiro
# para "041-919-81578147" não cair em nenhuma regra de texto.
_EXCLUSOES: List[Tuple[str, re.Pattern]] = [
    ("numero", re.compile(r"^[\d\s\-().+/]+$")),
    ("pix", re.compile(r"(^|\s)pix(\s|$)")),
    ("portaria", re.compile(r"\bportaria\b")),
    ("pesquisa", re.compile(r"\bpesquis(a|ar|as)\b|portal gas pesquisa|pesquisa d")),
    ("concorrente", re.compile(r"\bconcorrente\b|^ligou\b|\bligou\b")),
    ("trote", re.compile(r"\btrote\b")),
    ("pedido", re.compile(r"\bpedido\b")),
    ("cliente_novo", re.compile(r"\bcliente novo\b")),
    ("na_ultima", re.compile(r"\bna ultima\b")),
    ("spc", re.compile(r"\bspc\b")),
    ("siga_me", re.compile(r"\bsiga me\b")),
]


def motivo_exclusao(nome_bruto: Optional[str]) -> Optional[str]:
    """Motivo da exclusão (``numero``/``portaria``/``pix``/…) ou ``None``.

    Compara sem acento e sem caixa. Nunca exclui por nome vazio: isso é
    ausência de dado, tratada por quem chama.
    """
    chave = _chave(nome_bruto)
    if not chave:
        return None
    for motivo, padrao in _EXCLUSOES:
        if padrao.search(chave):
            return motivo
    return None


# ═══════════════════════════════════════════════════════════
# Vocabulário
# ═══════════════════════════════════════════════════════════

_TRATAMENTOS = r"dona|seu|senhor|senhora|sr|sra|dr|dra|doutor|doutora|pastor|pastora|don"
_TRATAMENTOS_SET = {
    "dona",
    "seu",
    "senhor",
    "senhora",
    "sr",
    "sra",
    "dr",
    "dra",
    "doutor",
    "doutora",
    "pastor",
    "pastora",
    "don",
}
_CONECTORES = {"e", "ou", "de", "da", "do", "dos", "das", "y", "x"}

# Palavras que indicam ENDEREÇO (não são nome de pessoa) — §4 Regra 4.
_PALAVRAS_ENDERECO = {
    "rua",
    "r",
    "alameda",
    "al",
    "avenida",
    "av",
    "travessa",
    "trav",
    "tv",
    "passagem",
    "pass",
    "praca",
    "rodovia",
    "estrada",
    "est",
    "servidao",
    "viela",
    "largo",
    "vila",
    "conjunto",
    "conj",
    "residencial",
    "resid",
    "res",
    "cohab",
    "parque",
    "park",
    "quadra",
    "qd",
    "q",
    "bloco",
    "bl",
    "apartamento",
    "apto",
    "apt",
    "ap",
    "casa",
    "torre",
    "lote",
    "box",
    "beco",
    "orla",
    "comunidade",
    "c",
    "l",
    "t",
    "numero",
    "numeracao",
    "n",
}

# Pistas de lugar/referência — em um "X E Y" indicam que NÃO é "entre ruas".
_PISTAS_REFERENCIA = {
    "box",
    "pm",
    "igreja",
    "escola",
    "mercado",
    "posto",
    "frente",
    "lado",
    "fundos",
    "altos",
    "prox",
    "proximo",
    "esquina",
    "esq",
    "banco",
    "ubs",
    "rotary",
    "assembleia",
    "rotatoria",
    "hospital",
    "ponto",
    "linha",
    "parada",
    "farmacia",
    "supermercado",
    "panificadora",
    "moto",
    "motos",
    "oficina",
}

# Início de endereço: se aparecer depois de um run de nome, o run é a pessoa
# ("Nelma Martins **Pass**.Triângulo", "Dona Ketelyn **Pass** Da Flores").
_ROAD_START = {
    "rua",
    "r",
    "travessa",
    "trav",
    "tv",
    "passagem",
    "pass",
    "alameda",
    "al",
    "avenida",
    "av",
    "beco",
    "estrada",
    "rodovia",
    "servidao",
    "viela",
    "largo",
    "praca",
    "vila",
    "cohab",
    "conjunto",
    "conj",
    "residencial",
    "resid",
    "parque",
    "park",
    "orla",
}

# Palavras que abrem um conjunto/bairro (não são nome de pessoa) — impedem que
# "Recanto Verde Alameda..." vire o nome "Recanto Verde".
_STOP_ESQUERDA = {
    "recanto",
    "vila",
    "conjunto",
    "conj",
    "cohab",
    "parque",
    "park",
    "residencial",
    "resid",
    "jardim",
    "monte",
    "buraco",
    "furo",
    "paracuri",
    "maraca",
    "cidade",
    "para",
    "fica",
    "atras",
    "perto",
    "quase",
}


def _road_key(token: str) -> str:
    """Primeira palavra significativa do token: ``"Pass.Triângulo"`` → ``pass``."""
    return re.split(r"[.:,;/\\]", _chave(token))[0].strip()


def _tokens_chave(texto: str) -> set:
    """Conjunto de tokens normalizados (sem pontuação) para classificar frases."""
    return {_road_key(t) for t in re.split(r"\s+", _chave(texto)) if t}


# ═══════════════════════════════════════════════════════════
# Padrões
# ═══════════════════════════════════════════════════════════

# Código legado no início: "1628= ", "(2068)", "000145=".
_LEGACY = re.compile(r"^\s*(?:\(\s*\d{1,6}\s*\)|\d{1,6}\s*=)\s*")

# Número de casa: Nº/N°/N⁰/N/Número/Numeração + dígitos (aceita "1457/ 04").
# Valor de número/complemento: aceita o marcador "nº/N" opcional antes dos
# dígitos (ex.: "Casa N⁰ 05", "Apto: 202").
_VAL_NUM = r"(?:n\s*[ºo°⁰⁰`'*.]?\s*)?([0-9]{1,4}[A-Za-z]?)"

_NUMERO = re.compile(
    r"(?<![A-Za-z])(?:numera(?:ç|c)(?:ão|oes|ões|ao)|n[uú]mero|n[uú]mera(?:ç|c)(?:ão|oes|ões)|n\s*[ºo°⁰⁰`'*.]?)\s*[:\-]?\s*"
    r"([0-9]{1,6}(?:[A-Za-z](?![A-Za-z]))?(?:\s*/\s*[0-9]{1,4}[A-Za-z]?)?)",
    re.IGNORECASE,
)

# Complementos — cada um vira "Tipo valor" (ex.: "Bloco 62"). Travessa/Lote
# ficam de fora de propósito: em "Travessa Armando Mendonça" e "Rua L-3" eles
# são o próprio logradouro, não complemento.
_COMPLEMENTOS: List[Tuple[str, re.Pattern]] = [
    ("Torre", re.compile(r"\btorre\b\s*[:\-]?\s*" + _VAL_NUM, re.IGNORECASE)),
    ("Bloco", re.compile(r"\bbl(?:oco)?\b\s*[:\-]?\s*" + _VAL_NUM, re.IGNORECASE)),
    ("Bloco", re.compile(r"(?<![A-Za-z])B\s*[-]\s*" + _VAL_NUM)),
    ("Quadra", re.compile(r"\b(?:qd|quadra|q)\b\s*[:\-]?\s*" + _VAL_NUM, re.IGNORECASE)),
    ("Apto", re.compile(r"\b(?:apartamento|apto|apt|ap)\b\s*[:\-]?\s*" + _VAL_NUM, re.IGNORECASE)),
    # Casa aceita também uma letra solta ("Casa B", "Casa H") — mas nunca uma
    # palavra ("Casa Do Zé" não é complemento "Casa Do").
    (
        "Casa",
        re.compile(r"\bcasa\b\s*[:\-]?\s*" + _VAL_NUM + r"|\bcasa\b\s*[:\-]?\s*([A-Za-z](?![A-Za-z]))", re.IGNORECASE),
    ),
]

# "entre A e B" (par explícito) e "esquina com B" — a palavra-chave precisa ser
# inteira e o par precisa existir, senão "Quase de esquina da Berredos" viraria
# um "entre" falso.
_ENTRE_SOLTO = re.compile(r"\bentre\s+(.+?)\s+e\s+(.+)$", re.IGNORECASE)
_ESQ_COM = re.compile(r"\b(?:esquina|esq)\b\s*(?:com|:)\s*(.+)$", re.IGNORECASE)
_ENTRE_PARES = re.compile(r"^(.+?)\s+(?:e|x|×)\s+(.+)$", re.IGNORECASE)

# "1 Rua" → "1ª Rua"; "3° Rua" → "3ª Rua".
_ORDINAL_RUA = re.compile(r"^(\d{1,2})\s*[°º⁰ª]?\s+(rua)\b", re.IGNORECASE)
_SO_NUMERO_ORDINAL = re.compile(r"^(\d{1,2})\s*[°º⁰ª]?\s*(rua)?$", re.IGNORECASE)

_PARENTESES = re.compile(r"\(([^()]*)\)")

_TRATAMENTO_NOME = re.compile(
    r"\b(" + _TRATAMENTOS + r")\b\.?\s+([A-Za-zÀ-ÿ][\wÀ-ÿ']*(?:\s+[A-Za-zÀ-ÿ][\wÀ-ÿ']*)*)\s*$",
    re.IGNORECASE,
)


def _split_legacy(texto: str) -> str:
    return _LEGACY.sub("", texto or "", count=1).strip()


def _numero_norm(valor: str) -> str:
    """``"16"`` → ``"Nº16"``; ``"1457/ 04"`` → ``"Nº1457/04"``."""
    limpo = re.sub(r"\s+", "", valor or "")
    return f"Nº{limpo}" if limpo else ""


# ═══════════════════════════════════════════════════════════
# Extração dos pedaços do endereço
# ═══════════════════════════════════════════════════════════


def _parece_pessoa(texto: str) -> bool:
    """Um parêntese é nome de pessoa se não tem palavra de endereço/lugar."""
    chave = _chave(texto)
    if not chave:
        return False
    tokens = _tokens_chave(texto)
    if not tokens:
        return False
    if tokens & (_PALAVRAS_ENDERECO | _PISTAS_REFERENCIA):
        return False
    return True


def _classificar_parenteses(texto: str) -> Tuple[Optional[str], Optional[str], str]:
    """Classifica os ``(...)`` e devolve (entre_ruas|None, nome|None, sobra).

    Cada parêntese é **entre ruas** (``X E Y`` sem pista de lugar), **nome**
    (parêntese humano) ou **referência** (contém pista de lugar) — referência é
    recuperada à parte por ``_referencia_do_bruto``.
    """
    entre: Optional[str] = None
    nome: Optional[str] = None
    sobra = texto
    for match in list(_PARENTESES.finditer(texto)):
        interno = _limpa_pontas(match.group(1))
        if interno:
            tokens = _tokens_chave(interno)
            tem_pista = bool(tokens & _PISTAS_REFERENCIA)
            par = _ENTRE_PARES.match(interno)
            if par and not tem_pista:
                a = _limpa_pontas(par.group(1))
                b = _limpa_pontas(par.group(2))
                if a and b:
                    entre = f"Entre {_normaliza_lado(a)} e {_normaliza_lado(b)}"
            elif not tem_pista and _parece_pessoa(interno):
                nome = interno
        sobra = sobra.replace(match.group(0), " ")
    return entre, nome, _normaliza_espacos(sobra)


def _normaliza_lado(lado: str) -> str:
    """``"3°"`` → ``"3ª"``; ``"4 ° Rua"`` → ``"4ª Rua"``; senão inalterado."""
    match = _SO_NUMERO_ORDINAL.match(lado.strip())
    if not match:
        return lado.strip()
    sufixo = " Rua" if match.group(2) else ""
    return f"{match.group(1)}ª{sufixo}"


def _extrair_numero(texto: str) -> Tuple[Optional[str], str, str]:
    """``(número, texto_antes, texto_depois)`` — a posição do número é preservada.

    Devolver a sobra JUNTA (antes + depois) faria o número sair reordenado no
    nome final ("… N3 N°52" → "… N°52 N3" na leitura seguinte) e o parser
    oscilava entre duas formas a cada reaplicação. O texto que vem DEPOIS do
    número (bairro/referência) vira `referencia` e continua no mesmo lugar.
    """
    match = _NUMERO.search(texto)
    if not match:
        return None, texto, ""
    numero = _numero_norm(match.group(1))
    if not numero:
        return None, texto, ""
    antes = _normaliza_espacos(texto[: match.start()])
    depois = _normaliza_espacos(texto[match.end() :])
    return numero, antes, depois


def _extrair_complementos(texto: str) -> Tuple[List[str], str]:
    """Remove os complementos do texto e devolve (na ordem de aparição, sobra).

    A ordem de aparição é a que o nome final usa ("Quadra 06 Bloco 124 Apto
    202") — não a ordem fixa do contrato do campo `complemento`.
    """
    achados: Dict[str, Tuple[int, str]] = {}
    for tipo, padrao in _COMPLEMENTOS:
        match = padrao.search(texto)
        if match and tipo not in achados:
            valor = next((g for g in match.groups() if g), "")
            achados[tipo] = (match.start(), valor.strip())

    restante = texto
    for tipo, padrao in _COMPLEMENTOS:
        if tipo in achados:
            restante = padrao.sub(" ", restante, count=1)

    ordenados = sorted(achados.items(), key=lambda item: item[1][0])
    lista = [f"{tipo} {valor}" for tipo, (_, valor) in ordenados]
    return lista, _normaliza_espacos(restante)


def _limite_endereco(texto: str) -> int:
    """Fim do último marcador de endereço (número/complemento) ou 0.

    É o corte entre endereço e nome: o que vem **depois** do último ``Nº``,
    ``Bloco``, ``Quadra``… é candidato a nome da pessoa.
    """
    fim = 0
    for match in _NUMERO.finditer(texto):
        fim = max(fim, match.end())
    for _, padrao in _COMPLEMENTOS:
        for match in padrao.finditer(texto):
            fim = max(fim, match.end())
    return fim


def _run_nome_com_fim(texto: str) -> Tuple[Optional[str], int, int]:
    """Run de tokens "nome de pessoa" no começo de ``texto``.

    Devolve ``(nome, início, fim)`` com os offsets em ``texto``: é o que permite
    reaproveitar o resto da cauda sem descartar nada (idempotência) — um simples
    ``texto.find(nome)`` falharia quando o run normaliza pontuação ("Esqui:" x
    "Esqui") e aí a cauda inteira seria duplicada.
    """
    coletados: List[str] = []
    fins: List[int] = []
    inicio = 0
    for match in re.finditer(r"\S+", texto):
        token = match.group(0)
        limpo = token.strip(" -.,;:()")
        if not limpo:
            if coletados:
                break
            continue
        chave = _road_key(limpo)
        if chave in _CONECTORES or chave in _TRATAMENTOS_SET:
            if not coletados:
                inicio = match.start()
            coletados.append(limpo)
            fins.append(match.end())
            continue
        # Palavra de endereço/lugar encerra o nome ("Fundos", "Próx:"…).
        if chave in _PALAVRAS_ENDERECO or chave in _PISTAS_REFERENCIA:
            break
        # Nome próprio: começa com maiúscula e tem letra.
        if limpo[:1].isupper() and any(c.isalpha() for c in limpo):
            if not coletados:
                inicio = match.start()
            coletados.append(limpo)
            fins.append(match.end())
            continue
        break
    # Um conector solto no fim ("Dona e") não é nome.
    while coletados and _road_key(coletados[-1]) in _CONECTORES:
        coletados.pop()
        fins.pop()
    if not coletados:
        return None, 0, 0
    nome = _normaliza_espacos(" ".join(coletados)) or None
    if not nome:
        return None, 0, 0
    return nome, inicio, fins[-1]


def _run_nome(texto: str) -> Optional[str]:
    """Run de tokens "nome de pessoa" no começo do texto (após o endereço)."""
    return _run_nome_com_fim(texto)[0]


def _extrair_nome_esquerda(texto: str) -> Tuple[Optional[str], str]:
    """Separa um nome de pessoa no INÍCIO de ``texto`` do endereço que segue.

    O padrão da agenda é o nome antes OU depois do endereço ("Dona Ketelyn
    **Pass** Da Flores…"); o nome à direita sai por ``_run_nome``; aqui é o da
    esquerda. Só dispara com um **tratamento** (Dona/Seu/Senhor/Sr/Dra/Pastora…)
    — é o único sinal de pessoa que não colide com logradouro de duas palavras
    ("Souza Franco Al…" NÃO é pessoa). O run para em conector/tratamento ou no
    primeiro token de via/lugar/bairro, e o texto restante vira endereço (nada é
    descartado).
    """
    tokens = _normaliza_espacos(texto).split()
    if not tokens:
        return None, texto
    # Só dispara com um TRATAMENTO (Dona/Seu/Senhor/Sr/Dra/Pastora…): é o único
    # sinal de pessoa à esquerda que não colide com nome de rua de duas palavras
    # ("Souza Franco Al…" NÃO é pessoa, "Dona Fulana Al…" é).
    if _road_key(tokens[0]) not in _TRATAMENTOS_SET:
        return None, texto

    run: List[str] = []
    for tok in tokens:
        chave = _road_key(tok)
        limpo = tok.strip(" -.,;:()")
        if not limpo:
            break
        if chave in _CONECTORES or chave in _TRATAMENTOS_SET:
            run.append(limpo)
            continue
        if chave in _STOP_ESQUERDA or chave in _PALAVRAS_ENDERECO or chave in _PISTAS_REFERENCIA:
            break
        if limpo[:1].isupper() and any(c.isalpha() for c in limpo):
            run.append(limpo)
            continue
        break

    if len(run) < 2:
        return None, texto
    run = run[:2]  # tratamento + primeiro nome
    nome = _normaliza_espacos(" ".join(run))
    # O resto (inclusive bairro que não é palavra de via) fica no endereço — sem
    # descartar texto.
    return nome, _normaliza_espacos(" ".join(tokens[len(run) :]))


def _aplicar_ordinal(endereco: str) -> str:
    """``5 Rua`` → ``5ª Rua`` (só o ordinal antes de "Rua")."""
    return _ORDINAL_RUA.sub(lambda m: f"{m.group(1)}ª {m.group(2).capitalize()}", endereco)


def nome_curto(nome: Optional[str]) -> Optional[str]:
    """Primeiro nome (+ sobrenome curto) preservando tratamento (§5)."""
    if not nome:
        return None
    tokens = nome.split()
    if not tokens:
        return None
    if _chave(tokens[0]) in _TRATAMENTOS_SET:
        return " ".join(tokens[:2])
    return tokens[0]


def _referencia_do_bruto(bruto: str) -> Optional[str]:
    """Conteúdo de um ``(...)`` que é ponto de referência (não pessoa/endereço)."""
    for match in list(_PARENTESES.finditer(bruto)):
        interno = _limpa_pontas(match.group(1))
        if not interno:
            continue
        # Referência = pista de lugar OU conteúdo de endereço (ex.: "(Al:
        # Quadros)", "(Rua Do Madalena)") — nunca descartar o parêntese.
        tokens = _tokens_chave(interno)
        # Um par "X E Y" já virou "entre ruas" — não repetir como referência.
        if _ENTRE_PARES.match(interno) and not (tokens & _PISTAS_REFERENCIA):
            continue
        if tokens & (_PISTAS_REFERENCIA | _PALAVRAS_ENDERECO | _ROAD_START):
            return interno
    return None


# ═══════════════════════════════════════════════════════════
# Montagem final
# ═══════════════════════════════════════════════════════════


def formatar_nome_final(
    endereco: Optional[str],
    numero: Optional[str],
    complemento: Optional[str],
    entre_ruas: Optional[str],
    referencia: Optional[str],
    nome: Optional[str],
) -> str:
    """Padrão combinado: ``endereço [Nº..] [complemento] [entre] [ref] - Nome``."""
    partes = [p for p in (endereco, numero, complemento, entre_ruas, referencia) if p]
    corpo = " ".join(partes)
    if nome and corpo:
        return f"{corpo} - {nome}"
    return corpo or (nome or "")


def renomear(nome_bruto: Optional[str]) -> Dict[str, Any]:
    """Transforma UM nome bruto no objeto estruturado do renomeador.

    Devolve sempre um dict. Contatos excluídos (``§4``) voltam com
    ``excluido=True`` e ``motivo``; os demais trazem o endereço decomposto, o
    ``nome_final_contato`` e o booleano ``alterado`` (``False`` quando o texto de
    entrada já era o nome final — idempotência).
    """
    bruto = _normaliza_espacos(str(nome_bruto or ""))
    motivo = motivo_exclusao(bruto)
    if motivo:
        return {"excluido": True, "motivo": motivo, "original": bruto}

    vazio = {
        "excluido": False,
        "original": bruto,
        "nome": None,
        "nome_curto": None,
        "endereco": None,
        "numero": None,
        "complemento": None,
        "entre_ruas": None,
        "referencia": None,
        "nome_final_contato": bruto,
        "alterado": False,
    }
    if not bruto:
        return vazio

    texto = _split_legacy(bruto)

    # 1) entre ruas — parênteses primeiro, depois o solto.
    entre, nome_paren, texto = _classificar_parenteses(texto)
    if not entre:
        m = _ENTRE_SOLTO.search(texto)
        if m:
            entre = f"Entre {_normaliza_lado(_limpa_pontas(m.group(1)))} e {_normaliza_lado(_limpa_pontas(m.group(2)))}"
            texto = texto[: m.start()].strip()
        else:
            m = _ESQ_COM.search(texto)
            if m:
                entre = f"Esquina com {_limpa_pontas(m.group(1))}"
                texto = texto[: m.start()].strip()

    # 2) nome à esquerda (antes do endereço) — "Dona Fulana Rua X…".
    nome_esquerda, texto = _extrair_nome_esquerda(texto)

    # 3) corte endereço × nome: o nome vive DEPOIS do último marcador.
    limite = _limite_endereco(texto)
    cauda = texto[limite:] if limite else ""
    endereco_bruto = texto[:limite] if limite else texto

    # 3) número e complementos (do trecho de endereço). O texto depois do
    #    número é preservado à parte: ele continua DEPOIS dele no nome final.
    numero, antes_num, depois_num = _extrair_numero(endereco_bruto)
    comp_antes, antes_num = _extrair_complementos(antes_num)
    comp_depois, depois_num = _extrair_complementos(depois_num)
    lista_comp = comp_antes + comp_depois
    endereco_bruto = antes_num
    sobra_depois = depois_num
    complemento = ", ".join(lista_comp) if lista_comp else None
    complemento_espacos = " ".join(lista_comp) if lista_comp else None

    # 4) nome da pessoa: parêntese humano > run após o endereço > tratamento.
    # O run devolve os offsets justamente para reaproveitar o resto da cauda.
    nome = nome_paren or nome_esquerda
    antes = ""
    depois = ""
    da_cauda = False
    if cauda and not nome:
        desloc = 2 if cauda.startswith("- ") else 0
        alvo = cauda[desloc:]
        nome, ini, fim = _run_nome_com_fim(alvo)
        if not nome:
            # "Parque Guajará - Luis Klaus": o run começa numa palavra de via e
            # para; o nome está DEPOIS do travessão.
            sep = alvo.find(" - ")
            if sep >= 0:
                pos = sep + 3
                nome, ini2, fim2 = _run_nome_com_fim(alvo[pos:])
                if nome:
                    ini, fim = pos + ini2, pos + fim2
        if nome:
            da_cauda = True
            antes = _normaliza_espacos(cauda[: desloc + ini]).strip(" \t-.,;:()")
            depois = _normaliza_espacos(cauda[desloc + fim :]).strip(" \t-.,;:()")

    nome_texto = None
    if not nome:
        trat = _TRATAMENTO_NOME.search(texto)
        if trat:
            candidato = _normaliza_espacos(trat.group(0))
            # Só aceita se o texto existir de verdade onde ainda há texto: em
            # "... Dona Josi N°5" o Nº do imóvel já saiu como número, e o "º"
            # é letra em Unicode (\w) — o match casaria contra um endereço já
            # cortado e o nome sairia DUPLICADO no final.
            if candidato in endereco_bruto or (cauda and candidato in cauda):
                nome_texto = candidato
                nome = nome_texto
    # O nome não pode ficar repetido no endereço ("... Dona Socorro - Dona Socorro").
    if nome_texto:
        endereco_bruto = _normaliza_espacos(endereco_bruto.replace(nome_texto, " "))

    # 4b) nada da cauda é descartado: o que não virou nome vira referência (fica
    #     antes de " - " no nome final); o que vem DEPOIS do nome é reapostado.
    if cauda and not da_cauda:
        indice = cauda.find(nome) if nome else -1
        if indice >= 0:
            antes = _normaliza_espacos(cauda[:indice]).strip(" \t-.,;:()")
            depois = _normaliza_espacos(cauda[indice + len(nome) :]).strip(" \t-.,;:()")
        else:
            # Sem nome na cauda o texto volta INTEIRO (inclusive o " - "
            # inicial): é ele que separa endereço de resto no nome de origem.
            antes = _normaliza_espacos(cauda)

    # Referência junta três fontes, todas na posição em que aparecem no texto
    # original: parênteses, o que ficou DEPOIS do número no endereço e o que
    # sobrou da cauda antes do nome. Nenhuma delas pode ser descartada.
    sobra_depois = _limpa_pontas(sobra_depois) if sobra_depois else ""
    referencia = " ".join(p for p in (_referencia_do_bruto(bruto), sobra_depois, antes) if p) or None

    endereco = _limpa_pontas(re.sub(r"[:]", " ", endereco_bruto))
    endereco = _aplicar_ordinal(endereco) if endereco else None
    # Observação: NÃO existe mais a queda de "palavra de via sozinha". Ela foi
    # escrita para o endereço completo; com o número separado, o pedaço antes
    # dele pode ser uma palavra só ("Cohab Nº92…") — derrubar era apagar texto
    # do nome. "Nada é descartado".
    # Sem marcador (limite=0) o texto inteiro só é endereço se tiver palavra de
    # via — senão "Surper Gas ( Wagner )" viraria um logradouro inventado.
    if endereco and not limite and not (set(_chave(endereco).split()) & _PALAVRAS_ENDERECO):
        endereco = None
    # Sem endereço identificável, o contato fica intacto: nada de renomear nome
    # de empresa para o dono entre parênteses ("nada é inventado").
    if not (endereco or numero or complemento or entre):
        return vazio

    nome_final = formatar_nome_final(endereco, numero, complemento_espacos, entre, referencia, nome) or bruto
    if depois:
        nome_final = f"{nome_final} {depois}"
    nome_final = _normaliza_espacos(nome_final)
    return {
        "excluido": False,
        "original": bruto,
        "nome": nome,
        "nome_curto": nome_curto(nome),
        "endereco": endereco,
        "numero": numero,
        "complemento": complemento,
        "entre_ruas": entre,
        "referencia": referencia,
        "nome_final_contato": nome_final,
        "alterado": nome_final != bruto,
    }
