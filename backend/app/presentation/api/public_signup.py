"""
Public Referral Signup — F10.1 (fallback (b) do spec §5: web público).

Endpoints PÚBLICOS (sem auth) consumidos pela página de cadastro hospedada
na Vercel (rota /cadastro do frontend). Proteções:

- Rate limit por telefone (3/hora) e por IP (5/hora) via WhatsAppLimitStore
  (Redis quando RATE_LIMIT_MODE=redis, fallback in-memory — F4.5);
- Token single-use (409), 11ª indicação do mês bloqueada no generate (429);
- Só cria/consulta: nunca lista nem expõe dados de terceiros (LGPD). A
  resposta confirma o cadastro (ou a validade do convite) e devolve apenas o
  que o PRÓPRIO indicado ganha — nunca o nome/dados de quem indicou.

Aqui o rate limit por IP funciona de verdade (R1 da F4.5 resolvido):
a requisição vem do navegador do cliente, não do webhook do WhatsApp.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from typing import Optional

from app.core.whatsapp_limits import get_whatsapp_limit_store
from app.infrastructure.database.dependencies import get_db

router = APIRouter(prefix="/public/referral", tags=["Public Signup"])

# Mesmos limites do auto-cadastro por IA (tools_impl.py).
SIGNUP_PHONE_LIMIT = 3  # cadastros por telefone por hora
SIGNUP_IP_LIMIT = 5  # cadastros por IP por hora
SIGNUP_WINDOW = 3600  # segundos
# Consulta do convite: generosa (o cliente pode recarregar a página), mas
# limita varredura de tokens a partir de um mesmo endereço.
INVITE_PEEK_IP_LIMIT = 60  # consultas por IP por hora


class PublicSignupRequest(BaseModel):
    """Payload do formulário de cadastro (página pública)."""

    model_config = ConfigDict(populate_by_name=True)

    invite_token: str = Field(..., min_length=1, alias="inviteToken")
    name: str = Field(..., min_length=3, max_length=120)
    phone: str = Field(..., min_length=8, max_length=30)
    rua: str = Field(..., min_length=1, max_length=200)
    numero: str = Field(..., min_length=1, max_length=20)
    bairro: str = Field(..., min_length=1, max_length=100)
    complemento: Optional[str] = Field(default=None, max_length=120)
    lgpd_consent: bool = Field(..., alias="lgpdConsent")


class PublicInvitePeekResponse(BaseModel):
    """Situação do convite ANTES do formulário (F10.6).

    Sem PII: identifica o convite, não quem indicou — a página só precisa
    saber se dá para prosseguir e o que o indicado ganha.
    """

    valid: bool
    reason: str  # ok | already_used | not_found | malformed
    coupon_value: Optional[float] = None
    coupon_type: Optional[str] = None
    validity_days: Optional[int] = None


class PublicSignupResponse(BaseModel):
    status: str
    referred_codigo: Optional[str] = None
    coupon_code: Optional[str] = None
    coupon_value: Optional[float] = None
    coupon_valid_until: Optional[str] = None
    message: str


def _client_ip(request: Request) -> str:
    """IP real do cliente (behind proxy/túnel: X-Forwarded-For primeiro)."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.get("/invite/{token}", response_model=PublicInvitePeekResponse)
def public_invite_peek(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
) -> PublicInvitePeekResponse:
    """Consulta o convite antes de mostrar o formulário.

    Devolve 200 com `valid`/`reason`: é uma consulta, não uma ação — "já
    usado" é resposta esperada (não erro) e evita o cliente preencher tudo
    para só então descobrir que o link morreu.
    """
    ip = _client_ip(request)
    if ip:
        allowed, _ = get_whatsapp_limit_store().allow(f"invite_peek:ip:{ip}", INVITE_PEEK_IP_LIMIT, SIGNUP_WINDOW)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Muitas consultas deste endereço. Tente novamente mais tarde.",
            )

    from app.application.coupon.referral_service import ReferralService

    return PublicInvitePeekResponse(**ReferralService(db, tenant_id="default").peek_invite(token))


@router.post("/signup", response_model=PublicSignupResponse)
def public_referral_signup(
    body: PublicSignupRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> PublicSignupResponse:
    """Auto-cadastro público via token de convite (single-use)."""
    from app.application.coupon.referral_service import ReferralService, ReferralError

    if not body.lgpd_consent:
        raise HTTPException(status_code=422, detail="Consentimento LGPD obrigatório.")

    token = body.invite_token.strip()
    if not token.startswith("GF-INV-"):
        raise HTTPException(status_code=422, detail="Token de convite inválido.")

    # ── Rate limit (telefone + IP) ────────────────────────
    store = get_whatsapp_limit_store()
    phone = "".join(ch for ch in body.phone if ch.isdigit())
    allowed, _ = store.allow(f"signup:phone:{phone}", SIGNUP_PHONE_LIMIT, SIGNUP_WINDOW)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas com este telefone. Aguarde 1 hora ou fale com a loja.",
        )
    ip = _client_ip(request)
    if ip:
        allowed, _ = store.allow(f"signup:ip:{ip}", SIGNUP_IP_LIMIT, SIGNUP_WINDOW)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Muitas tentativas deste endereço. Tente novamente mais tarde.",
            )

    # ── Cadastro (reuso total do ReferralService da F4) ───
    try:
        svc = ReferralService(db, tenant_id="default")
        result = svc.complete_signup(
            invite_token=token,
            name=body.name.strip(),
            phone=phone,
            address={"rua": body.rua.strip(), "numero": body.numero.strip(), "bairro": body.bairro.strip()},
        )
        referred_coupon = (result.get("coupons") or {}).get("referred") or {}
        client = result.get("referred_client")
        # Reenvio do mesmo telefone depois de resposta perdida → devolve o
        # MESMO cupom (o frontend reenvia sozinho quando a API volta).
        replayed = bool(result.get("idempotent_replay"))
        return PublicSignupResponse(
            status="replayed" if replayed else "created",
            referred_codigo=getattr(client, "codigo", None),
            coupon_code=referred_coupon.get("code"),
            coupon_value=referred_coupon.get("value"),
            coupon_valid_until=referred_coupon.get("end_date"),
            message=(
                "Seu cadastro já estava concluído — este é o seu cupom."
                if replayed
                else "Cadastro realizado! Seu cupom de boas-vindas já está disponível."
            ),
        )
    except ReferralError as e:
        # 404 token inexistente, 409 já usado — mapeia direto.
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
