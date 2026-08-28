"""
ESC/POS Receipt Formatter — GasFlow

Generates ESC/POS command streams for 80mm thermal printers.
Compatible with Goldentec GT710 and similar ESC/POS printers.

Usage:
    formatter = ReceiptFormatter()
    commands = formatter.format_order(order_data)
    # commands is a bytes object ready to send to printer
"""

from typing import Any, Dict, List, Optional
from datetime import datetime


class ESCPOSCommands:
    """Low-level ESC/POS command builder."""

    # Initialize
    INIT = b'\x1b\x40'  # ESC @ - Initialize printer
    RESET = b'\x1b\x3f\x0a'  # ESC ? LF

    # Text formatting
    BOLD_ON = b'\x1b\x45\x01'
    BOLD_OFF = b'\x1b\x45\x00'
    UNDERLINE_ON = b'\x1b\x2d\x01'
    UNDERLINE_OFF = b'\x1b\x2d\x00'
    DOUBLE_HEIGHT = b'\x1b\x21\x10'
    DOUBLE_WIDTH = b'\x1b\x21\x20'
    DOUBLE_SIZE = b'\x1b\x21\x30'
    NORMAL_SIZE = b'\x1b\x21\x00'

    # Alignment
    ALIGN_LEFT = b'\x1b\x61\x00'
    ALIGN_CENTER = b'\x1b\x61\x01'
    ALIGN_RIGHT = b'\x1b\x61\x02'

    # Line spacing
    LINE_SPACING_DEFAULT = b'\x1b\x32'
    LINE_SPACING_SMALL = b'\x1b\x33\x08'

    # Cut
    CUT_FULL = b'\x1b\x69'
    CUT_PARTIAL = b'\x1b\x6d\x01'

    # Feed
    FEED_AND_CUT = b'\x1b\x69'

    @classmethod
    def text(cls, value: str, encoding: str = 'cp850') -> bytes:
        """Encode text for ESC/POS."""
        try:
            return value.encode(encoding, errors='replace')
        except (UnicodeDecodeError, LookupError):
            return value.encode('utf-8', errors='replace')

    @classmethod
    def line(cls, text: str = '', width: int = 48, align: str = 'left') -> bytes:
        """Format a line with proper padding."""
        if not text:
            return b'\n'

        encoded = ESCPOSCommands.text(text)

        if align == 'center':
            # Center alignment handled by ESC/POS command
            return ESCPOSCommands.ALIGN_CENTER + encoded + b'\n' + ESCPOSCommands.ALIGN_LEFT
        elif align == 'right':
            return ESCPOSCommands.ALIGN_RIGHT + encoded + b'\n' + ESCPOSCommands.ALIGN_LEFT

        return encoded + b'\n'

    @classmethod
    def separator(cls, char: str = '-', width: int = 48) -> bytes:
        """Print a separator line."""
        line_text = str(char) * width
        return ESCPOSCommands.text(line_text) + b'\n'

    @classmethod
    def double_separator(cls, width: int = 48) -> bytes:
        """Print a double separator line."""
        line_text = '=' * width
        return ESCPOSCommands.text(line_text) + b'\n'


class ReceiptFormatter:
    """
    Formats order receipts for ESC/POS thermal printers.

    Supports 80mm paper width (~48 characters per line).
    """

    COMPANY_NAME = "MARCOS GAS"
    DEFAULT_WIDTH = 48

    def __init__(self, company_name: str = "MARCOS GAS", width: int = 48):
        self.company_name = company_name
        self.width = width

    def format_order(self, order: Dict[str, Any], extra: Optional[Dict] = None) -> bytes:
        """
        Generate ESC/POS bytes for an order receipt.

        Args:
            order: Order data dictionary with keys:
                - codigo, client_name, client_address, items, total,
                  payment_method, notes, created_at, driver_name, etc.
            extra: Optional extra data (company info, etc.)

        Returns:
            bytes: ESC/POS command stream ready to send to printer.
        """
        buf = bytearray()

        # Initialize printer
        buf.extend(ESCPOSCommands.INIT)
        buf.extend(ESCPOSCommands.LINE_SPACING_DEFAULT)

        # Company header
        buf.extend(ESCPOSCommands.DOUBLE_SIZE)
        buf.extend(ESCPOSCommands.text(self.company_name).center(self.width))
        buf.extend(b'\n')
        buf.extend(ESCPOSCommands.NORMAL_SIZE)

        # Separator
        buf.extend(ESCPOSCommands.double_separator(self.width))

        # Order number and date
        codigo = order.get('codigo', order.get('order_id', '???'))
        created_at = order.get('created_at', '')
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                date_str = dt.strftime('%d/%m/%Y %H:%M')
            except (ValueError, AttributeError):
                date_str = str(created_at)[:16]
        else:
            date_str = datetime.now().strftime('%d/%m/%Y %H:%M')

        buf.extend(ESCPOSCommands.BOLD_ON)
        buf.extend(ESCPOSCommands.line(f"PEDIDO #{codigo}", align='center'))
        buf.extend(ESCPOSCommands.BOLD_OFF)
        buf.extend(ESCPOSCommands.line(date_str, align='center'))
        buf.extend(ESCPOSCommands.separator(self.width))

        # Customer info
        client_name = order.get('client_name', order.get('customer_name', ''))
        if client_name:
            buf.extend(ESCPOSCommands.BOLD_ON)
            buf.extend(ESCPOSCommands.text("CLIENTE:"))
            buf.extend(ESCPOSCommands.BOLD_OFF)
            buf.extend(b'\n')
            buf.extend(ESCPOSCommands.line(client_name))

        # Address
        address = order.get('client_address', order.get('address', ''))
        if address:
            buf.extend(ESCPOSCommands.BOLD_ON)
            buf.extend(ESCPOSCommands.text("ENDERECO:"))
            buf.extend(ESCPOSCommands.BOLD_OFF)
            buf.extend(b'\n')
            # Word wrap long addresses
            for line_text in self._wrap_text(address, self.width):
                buf.extend(ESCPOSCommands.line(line_text))

        # Reference
        reference = order.get('client_reference', order.get('reference', ''))
        if reference:
            buf.extend(ESCPOSCommands.line(f"Ref: {reference}"))

        buf.extend(ESCPOSCommands.separator(self.width))

        # Items header
        buf.extend(ESCPOSCommands.BOLD_ON)
        header = f"{'ITEM':<24} {'QTD':>4} {'TOTAL':>10}"
        buf.extend(ESCPOSCommands.text(header))
        buf.extend(ESCPOSCommands.BOLD_OFF)
        buf.extend(b'\n')
        buf.extend(ESCPOSCommands.separator(self.width))

        # Items
        items = order.get('items', [])
        for item in items:
            name = item.get('product_nome', item.get('name', '???'))
            qty = item.get('quantity', 0)
            unit_price = item.get('unit_price', item.get('price', 0))
            subtotal = item.get('subtotal', qty * unit_price)

            # Truncate name if too long
            name_display = name[:22] if len(name) > 22 else name

            line_text = f"{name_display:<24} {qty:>4} {self._format_money(subtotal):>10}"
            buf.extend(ESCPOSCommands.line(line_text))

        buf.extend(ESCPOSCommands.separator(self.width))

        # Totals
        subtotal = order.get('subtotal', 0)
        delivery_fee = order.get('delivery_fee', 0)
        discount = order.get('discount', 0)
        total = order.get('total', 0)

        if delivery_fee:
            buf.extend(ESCPOSCommands.line(f"{'Subtotal:':<34} {self._format_money(subtotal):>14}"))
            buf.extend(ESCPOSCommands.line(f"{'Entrega:':<34} {self._format_money(delivery_fee):>14}"))

        if discount:
            buf.extend(ESCPOSCommands.line(f"{'Desconto:':<34} -{self._format_money(discount):>13}"))

        buf.extend(ESCPOSCommands.BOLD_ON)
        buf.extend(ESCPOSCommands.line(f"{'TOTAL:':<34} {self._format_money(total):>14}"))
        buf.extend(ESCPOSCommands.BOLD_OFF)

        # Payment method
        payment = order.get('payment_method', order.get('payment', ''))
        if payment:
            buf.extend(ESCPOSCommands.line(f"FORMA PGTO: {payment}"))

        buf.extend(ESCPOSCommands.separator(self.width))

        # Notes
        notes = order.get('notes', '')
        if notes:
            buf.extend(ESCPOSCommands.BOLD_ON)
            buf.extend(ESCPOSCommands.text("OBS:"))
            buf.extend(ESCPOSCommands.BOLD_OFF)
            buf.extend(b'\n')
            for line_text in self._wrap_text(notes, self.width):
                buf.extend(ESCPOSCommands.line(line_text))
            buf.extend(ESCPOSCommands.separator(self.width))

        # Driver info
        driver_name = order.get('driver_name', '')
        if driver_name:
            buf.extend(ESCPOSCommands.line(f"Motorista: {driver_name}"))

        # Footer
        buf.extend(ESCPOSCommands.double_separator(self.width))
        buf.extend(ESCPOSCommands.line("OBRIGADO!", align='center'))
        buf.extend(ESCPOSCommands.line(self.company_name, align='center'))
        buf.extend(ESCPOSCommands.double_separator(self.width))

        # Feed and cut
        buf.extend(b'\n\n\n')
        buf.extend(ESCPOSCommands.CUT_FULL)

        return bytes(buf)

    def format_status_check(self) -> bytes:
        """Generate a small test print to verify printer connection."""
        buf = bytearray()
        buf.extend(ESCPOSCommands.INIT)
        buf.extend(ESCPOSCommands.DOUBLE_SIZE)
        buf.extend(ESCPOSCommands.line("GASFLOW", align='center'))
        buf.extend(ESCPOSCommands.NORMAL_SIZE)
        buf.extend(ESCPOSCommands.separator(self.width))
        buf.extend(ESCPOSCommands.line("Teste de impressora", align='center'))
        buf.extend(ESCPOSCommands.line(datetime.now().strftime('%d/%m/%Y %H:%M:%S'), align='center'))
        buf.extend(ESCPOSCommands.separator(self.width))
        buf.extend(ESCPOSCommands.line("OK", align='center'))
        buf.extend(b'\n\n\n')
        buf.extend(ESCPOSCommands.CUT_FULL)
        return bytes(buf)

    def _format_money(self, value: float) -> str:
        """Format value as Brazilian Real."""
        return f"R$ {value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    def _wrap_text(self, text: str, width: int) -> List[str]:
        """Simple word wrap for receipt paper."""
        words = text.split()
        lines = []
        current_line = ''
        for word in words:
            test_line = f"{current_line} {word}".strip()
            if len(test_line) <= width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return lines or ['']
