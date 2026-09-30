"""Interpolação do número de casa no eixo do logradouro (etapa 6).

O contrato de `intersecoes` está congelado em
``[{"nome": str, "numero": int}, ...]`` — cada cruzamento precisa de um
**número**, não só da posição geométrica. Mas o OSM-BR quase não tem número de
casa (§18), então um provider que devolvesse só a ordenada do cruzamento não
teria o que gravar no contrato.

Aqui está a conta que fecha essa lacuna a partir de **âncoras**: pontos do
logradouro cuja posição no eixo *e* o número são conhecidos. Com duas âncoras, o
número de qualquer posição entre elas sai por interpolação linear.

Fora da faixa coberta, devolve `None`. Extrapolar número de casa é chute, e um
"entre ruas" chutado é pior que a triagem (D2): o provider simplesmente deixa
esse cruzamento fora da lista.

O outro lado da mesma conta é ``projetar_no_eixo``: transformar (lat, lng) na
posição 0..1 da polilinha — é ela que dá a `posicao` tanto da âncora quanto do
cruzamento (§8.3.1), e devolve também o deslocamento perpendicular para o
chamador decidir se o ponto pertence mesmo àquela via.
"""

from __future__ import annotations

import math

from typing import List, Optional, Sequence, Tuple

# (posição no eixo 0..1, número de casa conhecido naquele ponto)
Ancora = Tuple[float, int]


def estimar_numero(posicao: Optional[float], ancoras: Sequence[Ancora]) -> Optional[int]:
    """Número de casa estimado na `posicao`, ou `None` se não der para estimar.

    Devolve `None` quando: a posição está fora de 0..1; há menos de duas âncoras
    distintas; ou a posição cai fora da faixa coberta pelas âncoras.
    """
    if posicao is None:
        return None
    try:
        alvo = float(posicao)
    except (TypeError, ValueError):
        return None
    if not 0.0 <= alvo <= 1.0:
        return None

    # Âncora é DADO (vem do cache/provedor): uma quebrada é ignorada, nunca
    # levanta. Derrubar aqui significaria perder a formatação de 10.000 contatos
    # por causa de uma linha estranha no JSON.
    validas: List[Ancora] = []
    for pos, numero in ancoras or []:
        try:
            posicao_ancora = float(pos)
            numero_ancora = int(numero)
        except (TypeError, ValueError):
            continue
        if not 0.0 <= posicao_ancora <= 1.0:
            continue
        validas.append((posicao_ancora, numero_ancora))
    validas.sort()

    ordenadas: List[Ancora] = []
    for item in validas:
        # Duas âncoras no MESMO ponto não definem reta — a segunda é descartada.
        if not ordenadas or item[0] != ordenadas[-1][0]:
            ordenadas.append(item)

    if len(ordenadas) < 2:
        return None
    if not ordenadas[0][0] <= alvo <= ordenadas[-1][0]:
        return None  # fora da faixa: extrapolar seria inventar (D2)

    for (p0, n0), (p1, n1) in zip(ordenadas, ordenadas[1:]):
        if p0 <= alvo <= p1:
            if p1 == p0:  # pragma: no cover — a dedup acima impede
                return n0
            fracao = (alvo - p0) / (p1 - p0)
            return int(round(n0 + fracao * (n1 - n0)))
    return None  # pragma: no cover — coberto pela checagem de faixa


# ── Geometria do eixo (§8.3.1) ────────────────────────────

_RAIO_TERRA_M = 6371008.8
# Metros por grau na linha do equador; a longitude é corrigida por cos(lat).
_M_POR_GRAU_LAT = 110574.0
_M_POR_GRAU_LNG = 111320.0


def haversine_m(a: Sequence[float], b: Sequence[float]) -> float:
    """Distância em metros entre dois pontos ``(lat, lng)``."""
    try:
        lat1, lon1 = float(a[0]), float(a[1])
        lat2, lon2 = float(b[0]), float(b[1])
    except (TypeError, ValueError, IndexError, KeyError):
        return 0.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _RAIO_TERRA_M * math.asin(min(1.0, math.sqrt(h)))


def projetar_no_eixo(
    pontos: Sequence[Sequence[float]], alvo: Optional[Sequence[float]]
) -> Optional[Tuple[float, float]]:
    """`(posição 0..1, deslocamento perpendicular em metros)` de `alvo`.

    `pontos` é a sequência de ``(lat, lng)`` do logradouro, já na ordem do OSM;
    `alvo` é o nó ou cruzamento a projetar. Devolve ``None`` com polilinha
    degenerada (menos de 2 pontos, comprimento 0) ou alvo inválido — quem chama
    trata como "não deu para posicionar", nunca como posição zero.

    O **deslocamento perpendicular** é o filtro da §8.3.1: casa da via
    transversal ou paralela projeta longe do eixo e não pode virar âncora. A
    tolerância é escolha de quem chama (precisa de teste, §8.8.4), não daqui.
    """
    if alvo is None or not pontos or len(pontos) < 2:
        return None
    try:
        alat, alng = float(alvo[0]), float(alvo[1])
    except (TypeError, ValueError, IndexError):
        return None

    acumulado = [0.0]
    for i in range(1, len(pontos)):
        acumulado.append(acumulado[-1] + haversine_m(pontos[i - 1], pontos[i]))
    total = acumulado[-1]
    if total <= 0:
        return None

    melhor: Optional[Tuple[float, float]] = None
    for i in range(len(pontos) - 1):
        lat0, lng0 = float(pontos[i][0]), float(pontos[i][1])
        lat1, lng1 = float(pontos[i + 1][0]), float(pontos[i + 1][1])
        tam = haversine_m(pontos[i], pontos[i + 1])
        if tam <= 0:
            continue
        # Aproximação planar local (m << raio da Terra): metros por grau.
        kx = _M_POR_GRAU_LNG * math.cos(math.radians(lat0))
        ky = _M_POR_GRAU_LAT
        vx, vy = (lng1 - lng0) * kx, (lat1 - lat0) * ky
        wx, wy = (alng - lng0) * kx, (alat - lat0) * ky
        vv = vx * vx + vy * vy
        t = 0.0 if vv <= 0 else (wx * vx + wy * vy) / vv
        t = min(1.0, max(0.0, t))
        perp = math.hypot(wx - t * vx, wy - t * vy)
        if melhor is None or perp < melhor[0]:
            melhor = (perp, (acumulado[i] + t * tam) / total)

    if melhor is None:
        return None
    return melhor[1], melhor[0]


def juntar_segmentos(
    caminhos: Sequence[Sequence[Sequence[float]]],
) -> List[Tuple[float, float]]:
    """Costura as ways de um mesmo logradouro numa polilinha só (0..1 coerente).

    O OSM guarda um logradouro longo como **várias** ways (`segmentos_rua` no
    spike variou de 2 a 23). Se cada uma virasse um eixo, o 0..1 de uma way
    colidiria com o da outra e duas âncoras do mesmo trecho levariam a
    interpolações incompatíveis.

    Costura pelo **endpoint** compartilhado (o mesmo nó OSM ⇒ mesma coordenada).
    O que não encaixa é **descartado**, não jogado no fim: são geometrias
    desconectadas e inventar o trecho faria posição de uma via virar posição de
    outra (D2 — nunca completar com palpite).
    """
    pecas: List[List[Tuple[float, float]]] = [
        [(float(p[0]), float(p[1])) for p in c] for c in caminhos if c and len(c) >= 2
    ]
    if not pecas:
        return []
    pecas.sort(key=len, reverse=True)
    linha = pecas.pop(0)
    descartadas = 0
    while pecas:
        for i, peca in enumerate(pecas):
            if linha[-1] == peca[0]:
                linha.extend(peca[1:])
            elif linha[-1] == peca[-1]:
                linha.extend(reversed(peca[:-1]))
            elif linha[0] == peca[-1]:
                linha[:0] = peca[:-1]
            elif linha[0] == peca[0]:
                linha[:0] = list(reversed(peca))[1:]
            else:
                continue
            pecas.pop(i)
            break
        else:
            descartadas += 1
            pecas.pop(0)
    del descartadas
    return linha
