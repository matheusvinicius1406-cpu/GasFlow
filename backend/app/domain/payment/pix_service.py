"""
PIX Service — geração de BR Code (copia-e-cola) e QR Code.

Implementa a spec do PIX (EMV® QR Code + campos definidos pelo BACEN) de
forma determinística — sem depender de biblioteca externa não verificada:

    Payload Format Indicator       00 "01"
    Merchant Account Information   26 [ GUI(00)="br.gov.bcb.pix" + Key(01) ]
    Merchant Category Code         52 "0000"
    Transaction Currency           53 "986" (BRL)
    Transaction Amount             54 "150,00" (somente quando informado)
    Country Code                   58 "BR"
    Merchant Name                  59 (máx 25)
    Merchant City                  60 (máx 15)
    Additional Data Field          62 [ TXID(05) máx 25 alfanumérico ]
    CRC16-CCITT                    63 (4 hex, polinômio 0x1021, init 0xFFFF)

O BR Code gerado é o "copia e cola" exibido ao cliente; o QR Code é a
representação visual do mesmo payload.
"""

import base64
import re
import unicodedata
from io import BytesIO
from typing import Optional

import qrcode


def _normalize(value: str) -> str:
    """Remove acentos e mantém apenas caracteres ASCII imprimíveis."""
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^\x20-\x7E]", " ", value).strip()


def _sanitize_txid(txid: str) -> str:
    """TXID: máx 25 caracteres alfanuméricos maiúsculos."""
    clean = re.sub(r"[^A-Za-z0-9]", "", txid or "").upper()
    return clean[:25]


def _crc16_ccitt(data: str) -> int:
    """CRC16-CCITT (polinômio 0x1021, init 0xFFFF) sobre bytes ASCII."""
    crc = 0xFFFF
    for char in data.encode("ascii", errors="replace"):
        crc ^= char << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def _field(field_id: str, value: str) -> str:
    """Campo EMV: ID (2) + tamanho (2) + valor."""
    return f"{field_id}{len(value):02d}{value}"


def validate_pix_key(key: str, key_type: str) -> None:
    """Valida a chave PIX conforme o tipo. Levanta ValueError se inválida."""
    key = (key or "").strip()
    if not key:
        raise ValueError("Chave PIX é obrigatória")
    kt = key_type.upper()
    digits = re.sub(r"\D", "", key)
    if kt == "CPF" and len(digits) != 11:
        raise ValueError("Chave CPF deve ter 11 dígitos")
    if kt == "CNPJ" and len(digits) != 14:
        raise ValueError("Chave CNPJ deve ter 14 dígitos")
    if kt == "EMAIL" and "@" not in key:
        raise ValueError("Chave EMAIL inválida")
    if kt == "PHONE" and not digits:
        raise ValueError("Chave PHONE deve conter apenas dígitos")
    if kt == "RANDOM" and len(re.sub(r"[^0-9A-Fa-f-]", "", key)) not in (32, 36):
        raise ValueError("Chave RANDOM inválida")


def build_pix_copy_paste(
    key: str,
    key_type: str = "RANDOM",
    merchant_name: str = "GasFlow",
    merchant_city: str = "SAO PAULO",
    amount: Optional[float] = None,
    description: str = "",
    txid: str = "***",
) -> str:
    """Gera o BR Code (copia-e-cola PIX) com CRC16 válido."""
    validate_pix_key(key, key_type)

    merchant_account_info = _field("00", "br.gov.bcb.pix") + _field("01", key.strip())
    if description:
        merchant_account_info += _field("02", _normalize(description))

    payload = "000201"
    payload += _field("26", merchant_account_info)
    payload += _field("52", "0000")
    payload += _field("53", "986")
    if amount is not None:
        payload += _field("54", f"{amount:.2f}".replace(".", ","))
    payload += _field("58", "BR")
    payload += _field("59", _normalize(merchant_name)[:25])
    payload += _field("60", _normalize(merchant_city)[:15])
    # TXID: '***' é o valor literal do PIX estático (não sanitizar).
    clean_txid = "***" if txid == "***" else _sanitize_txid(txid)
    payload += _field("62", _field("05", clean_txid))
    payload += "6304"
    return payload + f"{_crc16_ccitt(payload):04X}"


def _qr_code_base64(payload: str) -> str:
    """Gera imagem PNG do QR Code e retorna como data URI base64."""
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


class PixService:
    """Geração de payload PIX (BR Code + QR Code)."""

    def generate_payload(
        self,
        amount: float,
        description: str = "",
        key: Optional[str] = None,
        key_type: str = "RANDOM",
        merchant_name: str = "GasFlow",
        merchant_city: str = "SAO PAULO",
        txid: Optional[str] = None,
    ) -> dict:
        """Gera BR Code + QR para um valor. Lança ValueError se inválido."""
        if amount <= 0:
            raise ValueError("Valor do PIX deve ser maior que zero")
        if not key:
            raise ValueError("Chave PIX é obrigatória")

        br_code = build_pix_copy_paste(
            key=key,
            key_type=key_type,
            merchant_name=merchant_name,
            merchant_city=merchant_city,
            amount=amount,
            description=description,
            txid=txid or "***",
        )
        return {
            "br_code": br_code,
            "qr_code": _qr_code_base64(br_code),
            "txid": _sanitize_txid(txid) if txid else "***",
            "amount": amount,
            "description": description,
            "key": key.strip(),
            "key_type": key_type.upper(),
            "merchant_name": _normalize(merchant_name)[:25],
            "merchant_city": _normalize(merchant_city)[:15],
        }
