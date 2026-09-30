r"""Formatter do nome de rota dos contatos — Fase 2, etapa 7 (D5/D7).

Monta o nome que volta para a agenda do celular:

    {codigo}= {rua} Nº {numero} entre {A} e {B} - CEP {cep} ({nome})

Cada trecho condicional é **best-effort** (D2): o que não existe é omitido, e
nada é inventado. Os três fallbacks são os travados na D5/ADR-0001:

- sem "entre ruas" → omite ``entre ...``;
- sem CEP → omite ``- CEP ...``;
- sem nome de pessoa → omite ``({nome})``.

``({nome})`` só aparece quando ``client.has_name`` é verdadeiro: o nome
placeholder do import (``Contato 1199...``) não é nome de pessoa e não deve
virar sufixo do endereço.

**Idempotência.** Aplicar o formatter a um contato cujo ``nome`` já é um nome de
rota devolve exatamente o mesmo texto (o prefixo ``^\d+\s*=\s*`` é descartado e
o nome humano é recuperado do sufixo ``(...)``). Sem isso, o segundo apply
empilharia código e endereço.

**Código (D7).** O banco guarda 6 dígitos (``000001``); o nome sai sem zeros à
esquerda (``1=``). A coluna não muda — é só a apresentação.

Este módulo é o consumidor de aplicação do formatter citado na §7 do prompt da
Fase 2 (contrato: idempotente, ``^\d+\s*=\s*``).
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Prefixo de nome já formatado ("1= ", "000001= "). É o gancho da idempotência.
ROTA_PREFIXO = re.compile(r"^\s*\d+\s*=\s*")
# Sufixo humano de um nome já formatado: o `(...)` no fim da linha.
_SUFIXO_NOME = re.compile(r"\(([^()]*)\)\s*$")


def limpar_codigo(nome: Any) -> str:
    """Remove um prefixo de código legado (``114= rua X`` → ``rua X``).

    Usado quando o contato chega com código antigo colado ao nome (D1): o
    código do app sempre vence e o antigo não é copiado.
    """
    return ROTA_PREFIXO.sub("", str(nome or "")).strip()


def codigo_padding_zero(codigo: Any) -> str:
    """``"000001"`` → ``"1"`` (D7). Não-numérico volta como veio."""
    texto = str(codigo or "").strip()
    return str(int(texto)) if texto.isdigit() else texto


def nome_da_pessoa(cliente: Any) -> str:
    """Nome humano do contato, mesmo que ``nome`` já seja um nome de rota.

    - ``nome`` comum (``Maria``) → ``Maria``;
    - ``nome`` já formatado (``1= rua X Nº 145 (Maria)``) → ``Maria``, pelo
      sufixo ``(...)``;
    - nome de rota **sem** sufixo (``1= rua X Nº 145``) → ``""``: o nome da
      pessoa não é recuperável e repetir o endereço como se fosse gente seria
      pior que omitir.

    É essa extração que fecha a idempotência do formatter.
    """
    bruto = str(getattr(cliente, "nome", "") or "").strip()
    if not ROTA_PREFIXO.match(bruto):
        return bruto
    sufixo = _SUFIXO_NOME.search(bruto)
    if sufixo:
        return sufixo.group(1).strip()
    return ""


def formatar_nome_rota(cliente: Any, entre_ruas: Optional[str] = None) -> str:
    """Nome de rota do contato no padrão D5, com os fallbacks da D2.

    ``entre_ruas`` permite injetar o par derivado das interseções (D12) sem
    depender da coluna ``clients.entre_ruas``; quando ``None``, usa a coluna.

    Nunca levanta por campo ausente: contato sem rua sai só com o código (e o
    nome, se houver) — a triagem é por ``geocode_status`` (D3), não por exceção.
    """
    codigo = codigo_padding_zero(getattr(cliente, "codigo", ""))
    rua = str(getattr(cliente, "rua", "") or "").strip()
    numero = str(getattr(cliente, "numero", "") or "").strip()
    cep = str(getattr(cliente, "cep", "") or "").strip()
    entre = entre_ruas if entre_ruas is not None else str(getattr(cliente, "entre_ruas", "") or "")
    entre = (entre or "").strip()

    partes = [f"{codigo}="] if codigo else ["="]
    if rua:
        partes.append(rua)
    if numero:
        partes.append(f"Nº {numero}")
    if entre:
        partes.append(f"entre {entre}")
    # CEP é o único trecho que vem depois de um separador " - " (D5).
    if cep:
        partes.append(f"- CEP {cep}")

    texto = " ".join(partes)

    if getattr(cliente, "has_name", None):
        pessoa = nome_da_pessoa(cliente)
        if pessoa:
            texto = f"{texto} ({pessoa})"
    return texto
