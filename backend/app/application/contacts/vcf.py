"""
Parser de .vcf do renomeador de contatos (.vcf) — ADR-0001 / Fase 2 §8.

Parser próprio, sem dependência externa (convenção do repo: `quopri` é stdlib).
Além do par ``FN``+``TEL`` do parser original, lê:

- ``ADR`` na ordem do spec vCard (``pobox;ext;rua;cidade;região;CEP;país``),
  respeitando ``\\;`` escapado;
- ``NOTE`` como fonte secundária de "entre ruas" e CEP;
- o **padrão de nome legado** da revenda:
  ``1443= berredos 145`` / ``1= berredos Nº 145 entre Rua A e Rua B - CEP 00000-000``;
- *line folding* (linha continuada por espaço/tab) e ``QUOTED-PRINTABLE``/
  ``CHARSET`` de export antigo.

Contrato de saída (um item por CARD, §8.4):
- ``telefone`` = 1º TEL; ``telefone_secundario`` = 2º TEL;
- ``telefones_ignorados`` = quantos TELs além dos dois (contados, nunca
  descartados em silêncio);
- ``nome`` = **só nome de pessoa**; ``nome_importado`` = nome bruto da
  importação, com o código legado preservado para rastreabilidade (§8.3).

Precedência dos dados de endereço: ``ADR`` > ``NOTE`` > nome legado.
Regra de ouro: nada é inventado. O que não resolver sai vazio e cai na triagem
(``geocode_status``), nunca num valor chutado.
"""

import quopri
import re
from typing import Any, Dict, List, Optional, Tuple

# Código sequencial legado no início do nome: "114= ", "000145=", "  12 =".
_LEGACY_CODE = re.compile(r"^\s*\d+\s*=\s*")

# CEP no fim da string: "... - CEP 00000-000" / "... CEP: 00000000".
_CEP_TAIL = re.compile(r"\s*-?\s*CEP[:\s]*(\d{5}-?\d{3})\s*$", re.IGNORECASE)
# CEP em qualquer posição (usado no NOTE).
_CEP_ANY = re.compile(r"\bCEP[:\s]*(\d{5}-?\d{3})\b", re.IGNORECASE)

# "entre Rua A e Rua B" — o "entre" precisa ser palavra inteira.
_ENTRE = re.compile(r"\s+entre\s+(.+?)\s+e\s+(.+?)\s*$", re.IGNORECASE)
# Guarda contra falso positivo de horário ("entre 14h e 18h").
_TIME_LIKE = re.compile(r"\d\s*h\b|\d{1,2}:\d{2}", re.IGNORECASE)

# Número de casa: "Nº 145", "N. 145", "N°145".
_NUMERO = re.compile(r"\s*N[ºo°]\.?\s*(\S+)\s*$", re.IGNORECASE)
# Alguns aparelhos exportam "Rua X, 145".
_NUMERO_COMMA = re.compile(r",\s*([0-9]+\s*[A-Za-z]?)\s*$")
# Último recurso: número solto no fim ("berredos 145").
_NUMERO_SOLTO = re.compile(r"\s+([0-9]{1,6}[A-Za-z]?)\s*$")
# Tipo de via sozinho ("Rua", "Av.") — remanescente assim NÃO vira logradouro.
_ROAD_ONLY = re.compile(
    r"^(?:rua|r\.?|avenida|av\.?|travessa|alameda|praça|praca|rodovia|estrada|"
    r"servidão|servidao|passagem|viela|largo)$",
    re.IGNORECASE,
)
# "({nome})" no fim — permite reimportar a própria saída sem perder a pessoa.
_PERSON_SUFFIX = re.compile(r"\(([^()]+)\)\s*$")


def normalize_cep(value: Optional[str]) -> Optional[str]:
    """Normaliza para ``00000-000``; qualquer coisa fora de 8 dígitos → None."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 8:
        return None
    return f"{digits[:5]}-{digits[5:]}"


def strip_legacy_code(nome: Optional[str]) -> str:
    """Remove o código antigo do início do nome.

    Nunca destrói o nome: um nome que seja *só* o código (ex.: ``"114="``)
    volta como veio, para não virar vazio.
    """
    raw = (nome or "").strip()
    stripped = _LEGACY_CODE.sub("", raw, count=1).strip()
    return stripped or raw


def _split_numero(text: str) -> Tuple[str, Optional[str]]:
    """Separa o número de casa do logradouro. Devolve (rua, numero|None).

    Ordem deliberada: ``Nº`` → ``,`` → número solto no fim. O número solto
    exige que o logradouro remanescente tenha letra e **não** seja só o tipo
    da via — senão ``"Rua 25"`` viraria ``rua="Rua"``.
    """
    for pattern in (_NUMERO, _NUMERO_COMMA):
        match = pattern.search(text)
        if match:
            return text[: match.start()].strip(), match.group(1).strip()

    match = _NUMERO_SOLTO.search(text)
    if match:
        rua = text[: match.start()].strip()
        if any(ch.isalpha() for ch in rua) and not _ROAD_ONLY.match(rua):
            return rua, match.group(1).strip()
    return text.strip(), None


def _split_escaped(value: str, sep: str = ";") -> List[str]:
    """Divide respeitando ``\\;`` / ``\\,`` / ``\\\\`` / ``\\n`` do vCard."""
    parts: List[str] = []
    current: List[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value):
            nxt = value[index + 1]
            if nxt in (";", ",", "\\", ":"):
                current.append(nxt)
                index += 2
                continue
            if nxt in ("n", "N"):
                current.append("\n")
                index += 2
                continue
        if char == sep:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current))
    return parts


def _extract_cep(text: str) -> Tuple[Optional[str], str]:
    """CEP no fim da string. Devolve (cep|None, sobra)."""
    match = _CEP_TAIL.search(text)
    if not match:
        return None, text
    cep = normalize_cep(match.group(1))
    if not cep:
        return None, text
    return cep, text[: match.start()].strip()


def _extract_entre(text: str) -> Tuple[Optional[str], str]:
    """ "entre A e B" no fim da string. Devolve ("A e B"|None, sobra)."""
    match = _ENTRE.search(text)
    if not match:
        return None, text
    first = match.group(1).strip().rstrip(".,;")
    second = match.group(2).strip().rstrip(".,;")
    if not first or not second:
        return None, text
    # "entre 14h e 18h" é horário, não rua.
    if _TIME_LIKE.search(first) or _TIME_LIKE.search(second):
        return None, text
    return f"{first} e {second}", text[: match.start()].strip()


def parse_legacy_name(nome: Optional[str]) -> Optional[Dict[str, Any]]:
    """Extrai endereço do padrão de nome legado. None se não for o padrão.

    Ex.: ``"1443= berredos 145"`` → ``{"rua": "berredos", "numero": "145"}``.
    """
    raw = (nome or "").strip()
    match = _LEGACY_CODE.match(raw)
    if not match:
        return None
    rest = raw[match.end() :].strip()
    if not rest:
        return None

    data: Dict[str, Any] = {}
    # O sufixo "({nome})" vem por ÚLTIMO — sai antes de CEP/entre, senão o
    # regex ancorado no fim não reconhece o CEP e o "entre" engole o resto.
    suffix = _PERSON_SUFFIX.search(rest)
    if suffix:
        rest = rest[: suffix.start()].strip()
    cep, rest = _extract_cep(rest)
    if cep:
        data["cep"] = cep
    entre, rest = _extract_entre(rest)
    if entre:
        data["entre_ruas"] = entre
    rua, numero = _split_numero(rest)
    if numero:
        data["numero"] = numero
    if rua:
        data["rua"] = rua
    return data


def parse_adr(value: Optional[str]) -> Dict[str, Any]:
    """Lê um ``ADR`` de vCard (``pobox;ext;rua;cidade;região;CEP;país``)."""
    parts = _split_escaped(value or "", ";")

    def at(index: int) -> str:
        return parts[index].strip() if index < len(parts) else ""

    data: Dict[str, Any] = {}
    if at(1):
        data["complemento"] = at(1)
    if at(3):
        data["bairro"] = at(3)
    if at(4):
        data["cidade"] = at(4)
    cep = normalize_cep(at(5))
    if cep:
        data["cep"] = cep
    rua, numero = _split_numero(at(2))
    if numero:
        data["numero"] = numero
    if rua:
        data["rua"] = rua
    return data


def parse_note(value: Optional[str]) -> Dict[str, Any]:
    """Fonte secundária: CEP e "entre ruas" escritos no ``NOTE``."""
    text = (value or "").strip()
    if not text:
        return {}
    data: Dict[str, Any] = {}
    cep_match = _CEP_ANY.search(text)
    if cep_match:
        cep = normalize_cep(cep_match.group(1))
        if cep:
            data["cep"] = cep
            # Remove o trecho do CEP para ele não colar na rua do "entre".
            text = f"{text[: cep_match.start()]} {text[cep_match.end() :]}".strip()
    entre, _ = _extract_entre(text)
    if entre:
        data["entre_ruas"] = entre
    return data


# ═══════════════════════════════════════════════════════════
# Leitura do vCard (folding + charset + params)
# ═══════════════════════════════════════════════════════════


def _logical_lines(raw: str) -> List[str]:
    """Desfaz o *line folding*: linha continuada começa com espaço/tab."""
    lines: List[str] = []
    for physical in (raw or "").splitlines():
        if physical[:1] in (" ", "\t") and lines:
            lines[-1] += physical[1:]
        else:
            lines.append(physical.strip())
    return lines


def _parse_line(line: str) -> Tuple[str, Dict[str, str], str]:
    """Devolve (tag, params, value) — params em maiúsculas, sem aspas."""
    if ":" not in line:
        return "", {}, ""
    head, value = line.split(":", 1)
    chunks = head.split(";")
    tag = chunks[0].strip().upper()
    params: Dict[str, str] = {}
    for chunk in chunks[1:]:
        if "=" in chunk:
            key, val = chunk.split("=", 1)
            params[key.strip().upper()] = val.strip().strip('"').upper()
        elif chunk.strip():
            params.setdefault("TYPE", chunk.strip().upper())
    return tag, params, value.strip()


def _decode_value(value: str, params: Dict[str, str]) -> str:
    """Decodifica ``QUOTED-PRINTABLE`` (com ``CHARSET``) quando declarado."""
    if params.get("ENCODING") != "QUOTED-PRINTABLE":
        return value
    raw = quopri.decodestring(value.encode("latin-1", "replace"))
    charset = params.get("CHARSET") or "UTF-8"
    try:
        return raw.decode(charset, "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


def _name_from_n(value: Optional[str]) -> Optional[str]:
    """Fallback quando o card não tem ``FN``: usa família + nome do ``N``."""
    parts = _split_escaped(value or "", ";")
    if len(parts) >= 2:
        joined = " ".join(p.strip() for p in (parts[1], parts[0]) if p.strip())
        return joined or None
    return (value or "").strip() or None


def _person_name(raw_name: Optional[str], legacy: Optional[Dict[str, Any]]) -> Optional[str]:
    """``nome`` é só nome de PESSOA (§8.3).

    O padrão legado é endereço, não pessoa → None. Se o bruto trouxer o sufixo
    ``({nome})`` (a própria saída do renomeador), a pessoa é recuperada — o que
    torna reimportar a saída idempotente.
    """
    if not raw_name:
        return None
    cleaned = strip_legacy_code(raw_name).strip()
    suffix = _PERSON_SUFFIX.search(cleaned)
    if suffix and suffix.group(1).strip():
        return suffix.group(1).strip()
    if legacy is not None:
        return None
    return cleaned or None


def _new_card() -> Dict[str, Any]:
    return {"fn": None, "n": None, "adr": [], "note": None, "tel": []}


def _build_contact(card: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Monta o contato final. None quando o card não tem telefone."""
    tels = [t for t in card["tel"] if t]
    if not tels:
        return None

    raw_name = card["fn"] or _name_from_n(card["n"])
    legacy = parse_legacy_name(raw_name) if raw_name else None
    structured: Dict[str, Any] = {}
    for adr in card["adr"]:
        structured.update({k: v for k, v in parse_adr(adr).items() if v})
    from_note = parse_note(card["note"]) if card["note"] else {}

    data: Dict[str, Any] = {
        "telefone": tels[0],
        "telefone_secundario": tels[1] if len(tels) > 1 else None,
        "telefones_ignorados": max(0, len(tels) - 2),
        "nome": _person_name(raw_name, legacy),
        "nome_importado": (raw_name or "").strip() or None,
        "is_whatsapp": None,
    }
    for field in ("rua", "numero", "complemento", "bairro", "cidade", "cep", "entre_ruas"):
        value = structured.get(field) or from_note.get(field) or (legacy or {}).get(field)
        if value:
            data[field] = value
    return data


def parse_vcf(raw: str) -> List[Dict[str, Any]]:
    """Extrai contatos de um vCard 2.1/3.0/4.0 — **um item por card**.

    Campos lidos: ``FN``, ``N`` (fallback de nome), ``TEL`` (1º principal, 2º
    secundário), ``ADR``, ``NOTE``.
    """
    contacts: List[Dict[str, Any]] = []
    card = _new_card()

    for line in _logical_lines(raw):
        if not line:
            continue
        tag, params, value = _parse_line(line)
        if tag == "BEGIN" and value.upper() == "VCARD":
            card = _new_card()
            continue
        if tag == "END" and value.upper() == "VCARD":
            contact = _build_contact(card)
            if contact:
                contacts.append(contact)
            card = _new_card()
            continue
        if tag == "FN":
            card["fn"] = _decode_value(value, params) or None
        elif tag == "N":
            card["n"] = _decode_value(value, params) or None
        elif tag == "ADR":
            card["adr"].append(_decode_value(value, params))
        elif tag == "NOTE":
            card["note"] = _decode_value(value, params) or None
        elif tag == "TEL":
            decoded = _decode_value(value, params)
            if decoded:
                card["tel"].append(decoded)

    return contacts
