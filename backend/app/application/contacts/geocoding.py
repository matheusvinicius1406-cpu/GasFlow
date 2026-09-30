"""GeocodingService — cache por RUA + interseções (Fase 2 §7 / ADR-0004).

Fluxo (cache-first):

    contato → chave da RUA → cache hit?  → devolve (1 requisição por rua, D12)
                             cache miss? → 1 requisição ao provedor → grava

O "entre A e B" **não** é lido pronto do cache: o cache guarda as interseções
com o número de casa do cruzamento, e o par é derivado por contato em
`escolher_entre_ruas()` — por isso o mesmo logradouro produz pares diferentes
em cada trecho, sem nenhuma requisição extra.

Regra de ouro (D2/D3): nada aqui levanta exceção para o chamador. Provedor fora
do ar vira `PENDENTE`, logradouro não achado vira `NAO_ENCONTRADO` — o contato
nunca é perdido por causa de terceiro.

Segundo elo (etapa 9 — fallback de CEP): quando o provedor não conhece o
logradouro, o CEP ainda resolve endereço **e** coordenada pela cadeia
**ViaCEP → BrasilAPI → PontoFato** (``_resultado_por_cep``). O ponto de CEP é de
*trecho*, não da casa — entra como fallback e grava a própria origem na coluna
``provider`` do cache.

O chamador em lote é a etapa 8 (``ContactJobService``, bounded-batch), e a
prova ponta a ponta de 10.000 contatos é a etapa 9
(``tests/test_contacts_e2e.py``).

Este módulo é o consumidor da tabela `geocode_cache` na camada de aplicação: o
guard de integridade (`tests/integrity_audit.py`) exclui `repositories/` do
scan, então tabela nova sem consumidor aqui reprova como `dado-invisivel`.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.core.texto import normalizar
from app.core.logging import setup_logging
from app.domain.delivery.routing import GeocodeResult, GeocodingProvider
from app.infrastructure.geocoding.cep import (
    CepFallback,
    EnderecoCep,
    somente_digitos_cep,
)
from app.infrastructure.geocoding.factory import get_geocoding_provider
from app.infrastructure.geocoding.viacep import ViaCepClient
from app.infrastructure.repositories.geocode_cache_model import GeocodeCacheModel

logger = setup_logging("INFO")

# D3 — os únicos valores que `clients.geocode_status` aceita.
STATUS_OK = "OK"
STATUS_NAO_ENCONTRADO = "NAO_ENCONTRADO"
STATUS_PENDENTE = "PENDENTE"

# Logradouro ainda não definido: o domínio usa "A definir" como placeholder.
_RUA_VAZIA = {"", "a definir"}

_NAO_DIGITO = re.compile(r"\D+")


# ── Chave e normalização (D12) ────────────────────────────


def normalize_endereco(value: Any) -> str:
    """minúsculas, sem acento, sem pontuação, espaços colapsados.

    Implementação em `app.core.texto` (camada neutra): o provider Overpass da
    etapa 6 precisa casar o MESMO texto contra o nome do OSM, e ele está em
    `infrastructure` — que não pode importar de `application`.
    """
    return normalizar(value)


def chave_rua(rua: str, bairro: str = "", cidade: str = "", uf: str = "") -> str:
    """sha256 de `rua|bairro|cidade|uf` normalizados — a chave do cache (D12).

    É por RUA de propósito: cachear por endereço completo faria 10.000
    requisições onde ~50 bastam (ADR-0004).
    """
    base = "|".join(normalize_endereco(parte) for parte in (rua, bairro, cidade, uf))
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _somente_digitos(valor: Any) -> Optional[int]:
    """Número de casa → int. `"145"`, `"145-A"`, `145` → 145; resto → None."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor if valor > 0 else None
    texto = _NAO_DIGITO.sub("", str(valor))
    if not texto:
        return None
    numero = int(texto)
    return numero if numero > 0 else None


def escolher_entre_ruas(intersecoes: List[Dict[str, Any]], numero: Any) -> Optional[str]:
    """As duas vias que CERCAM o número → ``"Rua A e Rua B"`` (D12).

    **CONTRATO CONGELADO** (etapa 6 — não muda depois):
    ``intersecoes = [{"nome": str, "numero": int}, ...]``. Cada item traz o
    nome da via que cruza e o **número de casa em que o cruzamento acontece**;
    a lista vem em ordem crescente de numeração.

    Consequência direta para a etapa 6: quem preenche é o provider Overpass, e
    ele só pode incluir um cruzamento quando consegue atribuir um `numero` — sem
    número, o cruzamento sai da lista (não entra com `numero` nulo ou chutado).
    O país quase não tem número de casa no OSM (§18), então o provider precisa
    **estimar o número por interpolação entre âncoras conhecidas**
    (``infrastructure/geocoding/axis.py::estimar_numero``, com teste próprio).
    Cruzamento sem número estimável ⇒ fora da lista ⇒ "entre" vazio ⇒ triagem
    (D2). A lista nunca é completada com um palpite.

    Itens malformados (sem nome, `numero` não numérico, item que não é dict) são
    ignorados em silêncio — o cache é dado, não código, e uma coluna editada à
    mão não pode derrubar a formatação de 10.000 contatos.

    Devolve `None` — caindo na triagem em vez de sair chutado (D2) — quando:
    não há número utilizável no contato, há menos de duas interseções úteis, ou
    o número está **fora** da faixa coberta (não existe par que o cerque, e o
    vizinho mais próximo seria invenção).

    Ordem de leitura: "A" é a interseção de baixo (maior número ≤ alvo) e "B" a
    de cima (menor número > alvo) — como quem sobe a numeração na rua.
    """
    alvo = _somente_digitos(numero)
    if alvo is None:
        return None

    pontos: List[Tuple[int, str]] = []
    for item in intersecoes or []:
        if not isinstance(item, dict):
            continue
        posicao = _somente_digitos(item.get("numero"))
        nome = str(item.get("nome") or "").strip()
        if posicao is None or not nome:
            continue
        pontos.append((posicao, nome))

    if len(pontos) < 2:
        return None

    pontos.sort()
    abaixo = [p for p in pontos if p[0] <= alvo]
    acima = [p for p in pontos if p[0] > alvo]
    if not abaixo or not acima:
        return None
    return f"{abaixo[-1][1]} e {acima[0][1]}"


# ── Serviço ───────────────────────────────────────────────


class GeocodingService:
    """Geocoding cache-first por rua; falha de terceiro nunca derruba o lote."""

    def __init__(
        self,
        db: DBSession,
        provider: Optional[GeocodingProvider] = None,
        viacep: Optional[ViaCepClient] = None,
        cep_fallback: Optional[CepFallback] = None,
    ):
        self.db = db
        self.provider = provider
        self._viacep = viacep
        self._cep_fallback = cep_fallback

    # ── Cache ────────────────────────────────────────────

    def _buscar_cache(self, chave: str) -> Optional[GeocodeCacheModel]:
        return self.db.query(GeocodeCacheModel).filter(GeocodeCacheModel.chave == chave).first()

    def _gravar_cache(
        self,
        chave: str,
        rua: str,
        bairro: str,
        cidade: str,
        uf: str,
        resultado: Optional[GeocodeResult],
        provider_name: Optional[str] = None,
    ) -> None:
        """Grava UMA linha do cache em transação própria.

        `resultado=None` grava o **negativo** (lat/lng nulos): sem isso, um
        logradouro que o OSM não conhece seria reconsultado a cada contato da
        mesma rua — exatamente o custo que o cache existe para evitar.

        A transação é própria porque o cache é independente do cadastro: um
        rollback do lote não pode apagar o que já foi consultado (e o cache é
        idempotente pela `chave`, então perder uma linha não é erro).
        """
        provider = self._provider()
        self.db.add(
            GeocodeCacheModel(
                chave=chave,
                rua=rua or None,
                bairro=bairro or None,
                cidade=cidade or None,
                uf=uf or None,
                # Quem respondeu de fato: o provedor do OSM ou o fallback de
                # CEP (etapa 9). Sem isso, um ponto de CEP ficaria registrado
                # como se fosse do Nominatim — dado auditável tem de dizer a
                # própria origem.
                provider=provider_name or getattr(provider, "name", None),
                lat=resultado.lat if resultado else None,
                lng=resultado.lng if resultado else None,
                cep=(resultado.cep or None) if resultado else None,
                intersecoes=(resultado.intersecoes or None) if resultado else None,
            )
        )
        try:
            self.db.commit()
        except IntegrityError:
            # Corrida: outro worker gravou a MESMA rua entre o SELECT e o
            # INSERT. A chave é única — desfaz e segue (quem gravou já tem o
            # dado, e a próxima leitura pega o cache dele).
            self.db.rollback()
        except Exception as exc:  # pragma: no cover — banco indisponível
            self.db.rollback()
            logger.warning("geocoding.cache_write_failed", extra={"error": str(exc)})

    @staticmethod
    def _do_model(linha: GeocodeCacheModel) -> GeocodeResult:
        # `isinstance` e não `list(...)`: se o JSON voltar como dict (coluna
        # editada na mão, dado de uma versão futura), `list(dict)` viraria uma
        # lista de chaves e a derivação compararia nomes de campo como se
        # fossem interseções — erro silencioso.
        intersecoes = linha.intersecoes if isinstance(linha.intersecoes, list) else []
        return GeocodeResult(
            lat=float(linha.lat or 0.0),
            lng=float(linha.lng or 0.0),
            rua=linha.rua or "",
            bairro=linha.bairro or "",
            cidade=linha.cidade or "",
            uf=linha.uf or "",
            cep=linha.cep or "",
            intersecoes=intersecoes,
        )

    # ── Provedor ─────────────────────────────────────────

    def _provider(self) -> GeocodingProvider:
        """Provider injetado (testes) ou resolvido do factory na 1ª consulta."""
        if self.provider is None:
            self.provider = get_geocoding_provider()
        return self.provider

    def buscar_cep(self, cidade: str, uf: str, rua: str) -> Optional[str]:
        """CEP via ViaCEP — só com cidade/uf e só se estiver habilitado."""
        if not settings.viacep_enabled:
            return None
        if not (cidade or "").strip() or not (uf or "").strip():
            # §7: o ViaCEP por endereço exige cidade e UF. A guarda fica aqui
            # (e não só no cliente HTTP) porque é regra do serviço, não do
            # transporte — assim vale para qualquer cliente injetado.
            return None
        if self._viacep is None:
            self._viacep = ViaCepClient(settings.viacep_base_url)
        try:
            return self._viacep.buscar_cep(uf, cidade, rua)
        except Exception as exc:  # pragma: no cover — rede
            logger.warning("geocoding.viacep_failed", extra={"error": str(exc)})
            return None

    def buscar_endereco_por_cep(self, cep: str) -> Optional[EnderecoCep]:
        """CEP → endereço + coordenada (BrasilAPI → PontoFato). Nunca levanta.

        É o segundo elo do D2: só faz sentido quando o provedor do OSM não
        conheceu o logradouro. Desligado por env, devolve `None` — o contato
        cai na triagem em vez de o serviço sumir da conta.
        """
        if not settings.cep_fallback_enabled:
            return None
        if not somente_digitos_cep(cep):
            return None
        if self._cep_fallback is None:
            self._cep_fallback = CepFallback()
        try:
            return self._cep_fallback.buscar(cep)
        except Exception as exc:  # pragma: no cover — rede
            logger.warning("geocoding.cep_fallback_failed", extra={"error": str(exc)})
            return None

    def _resultado_por_cep(
        self, rua: str, bairro: str, cidade: str, uf: str, cep_hint: str
    ) -> Tuple[Optional[GeocodeResult], Optional[str]]:
        """Monta o `GeocodeResult` do CEP quando o OSM não achou a rua.

        Fecha a cadeia **ViaCEP → BrasilAPI → PontoFato**: usa o CEP que o
        contato já trazia e, se não havia, o ViaCEP por endereço para descobrir
        um. Devolve `(resultado|None, provider|None)`.

        A coordenada do CEP é de *trecho* (não da casa) — por isso entra como
        fallback e com a origem registrada, nunca no lugar do OSM.
        """
        cep = somente_digitos_cep(cep_hint) or somente_digitos_cep(self.buscar_cep(cidade, uf, rua))
        if not cep:
            return None, None
        endereco = self.buscar_endereco_por_cep(cep)
        if endereco is None or not endereco.tem_coordenada:
            return None, None
        return (
            GeocodeResult(
                lat=float(endereco.lat),
                lng=float(endereco.lng),
                rua=endereco.rua or rua,
                bairro=endereco.bairro or bairro,
                cidade=endereco.cidade or cidade,
                uf=endereco.uf or uf,
                cep=endereco.cep or f"{cep[:5]}-{cep[5:]}",
            ),
            endereco.provider,
        )

    # ── Contrato principal ───────────────────────────────

    def get_or_geocode(
        self, rua: str, bairro: str = "", cidade: str = "", uf: str = "", cep_hint: str = ""
    ) -> Tuple[Optional[GeocodeResult], str]:
        """Devolve `(resultado, status)`. Cache-first; nunca levanta.

        `cep_hint` é o CEP que o contato já trazia: entra só como atalho do
        fallback (etapa 9) e **não** faz parte da chave do cache — a chave é da
        rua (D12).
        """
        rua = (rua or "").strip()
        if normalize_endereco(rua) in _RUA_VAZIA:
            return None, STATUS_PENDENTE

        chave = chave_rua(rua, bairro, cidade, uf)
        cache = self._buscar_cache(chave)
        if cache is not None:
            if cache.lat is None:
                return None, STATUS_NAO_ENCONTRADO  # negativo cacheado
            return self._do_model(cache), STATUS_OK

        if not settings.geocoding_enabled:
            # Desligado por env: nada de requisição — o contato fica para a
            # triagem em vez de sumir.
            return None, STATUS_PENDENTE

        try:
            resultado = self._provider().geocode_street(rua, bairro, cidade, uf)
        except Exception as exc:
            # Provider é plugável: não se assume que ele é total.
            logger.warning("geocoding.provider_failed", extra={"error": str(exc)})
            return None, STATUS_PENDENTE

        origem: Optional[str] = None
        if resultado is None:
            # Segundo elo (D2/etapa 9): o OSM não conhece o logradouro, mas o
            # CEP pode resolvê-lo — ViaCEP (endereço→CEP) → BrasilAPI →
            # PontoFato (CEP→coordenada).
            resultado, origem = self._resultado_por_cep(rua, bairro, cidade, uf, cep_hint)

        if resultado is None:
            self._gravar_cache(chave, rua, bairro, cidade, uf, None)
            return None, STATUS_NAO_ENCONTRADO

        # CEP: o postcode do OSM primeiro (já veio no resultado); ViaCEP só
        # quando ele faltou — e o ViaCEP exige cidade/uf.
        if not resultado.cep:
            resultado.cep = self.buscar_cep(cidade, uf, rua) or ""

        self._gravar_cache(chave, rua, bairro, cidade, uf, resultado, provider_name=origem)
        return resultado, STATUS_OK

    def geocodificar_cliente(self, cliente) -> str:
        """Geocodifica o logradouro do contato e preenche os campos dele (D3).

        Não persiste o contato: quem grava é o chamador (convenção do
        repositório). O cache, sim, já ficou gravado — ele não depende do
        cadastro dar certo.
        """
        rua = (cliente.rua or "").strip()
        if normalize_endereco(rua) in _RUA_VAZIA:
            cliente.geocode_status = STATUS_PENDENTE
            return STATUS_PENDENTE

        # Cidade/UF default de system_settings (D11) entram ANTES da chave: sem
        # isso, um contato sem cidade geraria uma chave diferente do mesmo
        # logradouro já cacheado com a cidade padrão.
        cidade = (cliente.cidade or "").strip() or self.default_city()
        uf = (cliente.uf or "").strip() or self.default_uf()

        resultado, status = self.get_or_geocode(rua, cliente.bairro or "", cidade, uf, cep_hint=cliente.cep or "")
        cliente.geocode_status = status

        if resultado is not None:
            cliente.lat = resultado.lat
            cliente.lng = resultado.lng
            if not cliente.cep and resultado.cep:
                cliente.cep = resultado.cep
            if not cliente.cidade and resultado.cidade:
                cliente.cidade = resultado.cidade
            if not cliente.uf and resultado.uf:
                cliente.uf = resultado.uf
        return status

    def entre_ruas_do_contato(self, cliente) -> Optional[str]:
        """Deriva "entre A e B" do cache da rua + número do contato (D12).

        Zero requisição: o par sai das interseções já cacheadas. `None` quando
        não há cache (ou ele não trouxe interseções) — vazio é triagem, não
        chute.
        """
        rua = (cliente.rua or "").strip()
        if normalize_endereco(rua) in _RUA_VAZIA:
            return None
        cidade = (cliente.cidade or "").strip() or self.default_city()
        uf = (cliente.uf or "").strip() or self.default_uf()
        linha = self._buscar_cache(chave_rua(rua, cliente.bairro or "", cidade, uf))
        if linha is None:
            return None
        return escolher_entre_ruas(list(linha.intersecoes or []), cliente.numero)

    # ── Cidade/UF default (D11) ──────────────────────────

    def default_city(self) -> str:
        return self._setting("contacts.default_city")

    def default_uf(self) -> str:
        return self._setting("contacts.default_uf")

    def _setting(self, chave: str) -> str:
        """Valor de `system_settings` (D11). Ausente/tabela fora do ar → \"\"."""
        try:
            from app.application.settings.settings_service import SettingsService

            return str(SettingsService(self.db).get_value(chave, "") or "")
        except Exception:
            return ""
