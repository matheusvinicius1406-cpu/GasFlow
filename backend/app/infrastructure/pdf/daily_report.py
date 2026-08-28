"""
Daily Report PDF Generator — GasFlow

Generates a professional daily business report PDF.
Uses reportlab for PDF generation.

Report sections:
- Header (company name, date)
- Summary (orders, revenue, payments, expenses)
- Orders table
- Financial summary
- Footer (page numbers, generation time)
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from io import BytesIO


def _format_money(value: float) -> str:
    """Format value as Brazilian Real."""
    return f"R$ {value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def _format_date(date_str: str) -> str:
    """Format ISO date to DD/MM/YYYY."""
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime('%d/%m/%Y')
    except (ValueError, AttributeError):
        return str(date_str)[:10]


class DailyReportPDF:
    """
    Generates daily business report PDF.

    Uses reportlab for PDF generation.
    Falls back to simple text-based PDF if reportlab is not available.
    """

    def __init__(self, company_name: str = "MARCOS GAS"):
        self.company_name = company_name

    def generate(self, report_data: Dict[str, Any], date: str = "") -> bytes:
        """
        Generate a daily report PDF.

        Args:
            report_data: Report data with keys:
                - date: Report date
                - summary: {total_orders, delivered, cancelled, revenue, ...}
                - orders: [{codigo, client, items, total, status, payment, driver}]
                - financial: {received, pending, expenses}
                - inventory: {movements: [...]} (optional)
            date: Report date (YYYY-MM-DD)

        Returns:
            bytes: PDF file content
        """
        try:
            return self._generate_with_reportlab(report_data, date)
        except ImportError:
            return self._generate_simple(report_data, date)

    def _generate_with_reportlab(self, report_data: Dict[str, Any], date: str) -> bytes:
        """Generate PDF using reportlab."""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                topMargin=20*mm, bottomMargin=20*mm,
                                leftMargin=15*mm, rightMargin=15*mm)

        styles = getSampleStyleSheet()
        elements = []

        # Custom styles
        title_style = ParagraphStyle('CustomTitle', parent=styles['Title'],
                                      fontSize=20, alignment=TA_CENTER,
                                      spaceAfter=6)
        subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'],
                                         fontSize=12, alignment=TA_CENTER,
                                         textColor=colors.grey, spaceAfter=20)
        heading_style = ParagraphStyle('Heading', parent=styles['Heading2'],
                                        fontSize=14, spaceAfter=10, spaceBefore=20)
        normal_style = ParagraphStyle('NormalCustom', parent=styles['Normal'],
                                       fontSize=10, spaceAfter=6)
        right_style = ParagraphStyle('Right', parent=styles['Normal'],
                                      fontSize=10, alignment=TA_RIGHT)

        # Header
        elements.append(Paragraph(self.company_name, title_style))
        elements.append(Paragraph("RELATORIO DIARIO", subtitle_style))

        report_date = report_data.get('date', date)
        if report_date:
            elements.append(Paragraph(f"Data: {_format_date(report_date)}", subtitle_style))

        elements.append(Spacer(1, 10))

        # Summary section
        summary = report_data.get('summary', {})
        if summary:
            elements.append(Paragraph("RESUMO", heading_style))

            summary_data = [
                ['Metrica', 'Valor'],
                ['Total de Pedidos', str(summary.get('total_orders', 0))],
                ['Pedidos Entregues', str(summary.get('delivered', 0))],
                ['Pedidos Cancelados', str(summary.get('cancelled', 0))],
                ['Faturamento', _format_money(summary.get('revenue', 0))],
                ['Recebimentos', _format_money(summary.get('received', 0))],
                ['Valores Pendentes', _format_money(summary.get('pending_amount', 0))],
            ]

            if summary.get('expenses'):
                summary_data.append(['Despesas', _format_money(summary['expenses'])])

            if summary.get('quantity_p13'):
                summary_data.append(['Quantidade P13', str(summary['quantity_p13'])])

            if summary.get('quantity_water'):
                summary_data.append(['Quantidade Agua', str(summary['quantity_water'])])

            table = Table(summary_data, colWidths=[120, 120])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f4f6')]),
            ]))
            elements.append(table)

        # Orders section
        orders = report_data.get('orders', [])
        if orders:
            elements.append(Spacer(1, 20))
            elements.append(Paragraph("PEDIDOS DO DIA", heading_style))

            orders_header = ['#', 'Horario', 'Cliente', 'Itens', 'Total', 'Pgto', 'Status']
            orders_table_data = [orders_header]

            for order in orders[:50]:  # Limit to 50 orders per page
                created = order.get('created_at', '')
                time_str = ''
                if created:
                    try:
                        dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                        time_str = dt.strftime('%H:%M')
                    except (ValueError, AttributeError):
                        time_str = '--:--'

                items_count = len(order.get('items', []))
                items_str = str(items_count) if items_count else '-'

                orders_table_data.append([
                    str(order.get('codigo', order.get('order_id', '???'))),
                    time_str,
                    str(order.get('client_name', order.get('customer_name', '')))[:20],
                    items_str,
                    _format_money(order.get('total', 0)),
                    str(order.get('payment_method', order.get('payment', '')))[:8],
                    str(order.get('status', ''))[:10],
                ])

            col_widths = [40, 40, 100, 30, 60, 50, 60]
            table = Table(orders_table_data, colWidths=col_widths)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#059669')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (3, 0), (4, -1), 'RIGHT'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0fdf4')]),
            ]))
            elements.append(table)

        # Financial section
        financial = report_data.get('financial', {})
        if financial:
            elements.append(Spacer(1, 20))
            elements.append(Paragraph("FINANCEIRO", heading_style))

            fin_data = [
                ['Categoria', 'Valor'],
                ['Recebido', _format_money(financial.get('received', 0))],
                ['Pendente', _format_money(financial.get('pending', 0))],
            ]

            if financial.get('overdue'):
                fin_data.append(['Vencido', _format_money(financial['overdue'])])

            if financial.get('expenses'):
                fin_data.append(['Despesas', _format_money(financial['expenses'])])

            table = Table(fin_data, colWidths=[120, 120])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(table)

        # Footer
        elements.append(Spacer(1, 30))
        generation_time = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        elements.append(Paragraph(
            f"Gerado em: {generation_time}",
            ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8,
                           textColor=colors.grey, alignment=TA_CENTER)
        ))

        # Build PDF
        doc.build(elements)
        return buffer.getvalue()

    def _generate_simple(self, report_data: Dict[str, Any], date: str) -> bytes:
        """
        Generate a simple PDF without reportlab.
        Creates a basic text-based PDF.
        """
        # Simple PDF generation without external dependencies
        lines = []
        lines.append(f"{self.company_name}")
        lines.append(f"RELATORIO DIARIO")
        lines.append(f"Data: {_format_date(report_data.get('date', date))}")
        lines.append("")

        summary = report_data.get('summary', {})
        if summary:
            lines.append("RESUMO")
            lines.append(f"Total de Pedidos: {summary.get('total_orders', 0)}")
            lines.append(f"Pedidos Entregues: {summary.get('delivered', 0)}")
            lines.append(f"Pedidos Cancelados: {summary.get('cancelled', 0)}")
            lines.append(f"Faturamento: {_format_money(summary.get('revenue', 0))}")
            lines.append(f"Recebimentos: {_format_money(summary.get('received', 0))}")
            lines.append("")

        orders = report_data.get('orders', [])
        if orders:
            lines.append("PEDIDOS DO DIA")
            for order in orders[:30]:
                codigo = order.get('codigo', order.get('order_id', '???'))
                client = order.get('client_name', order.get('customer_name', ''))
                total = _format_money(order.get('total', 0))
                status = order.get('status', '')
                lines.append(f"  #{codigo} - {client[:20]} - {total} - {status}")
            lines.append("")

        financial = report_data.get('financial', {})
        if financial:
            lines.append("FINANCEIRO")
            lines.append(f"Recebido: {_format_money(financial.get('received', 0))}")
            lines.append(f"Pendente: {_format_money(financial.get('pending', 0))}")
            lines.append("")

        lines.append(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

        # Create minimal valid PDF
        text = "\n".join(lines)
        return self._create_minimal_pdf(text)

    def _create_minimal_pdf(self, text: str) -> bytes:
        """Create a minimal valid PDF with text content."""
        # Minimal PDF structure
        content = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj

2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj

3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842]
   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj

4 0 obj
<< /Length {len(text) + 100} >>
stream
/F1 10 Tf
50 800 Td
"""

        # Add text lines
        y = 800
        for line in text.split('\n'):
            safe_line = line.replace('(', '\\(').replace(')', '\\)')
            content += f"({safe_line}) Tj\n0 -14 Td\n"
            y -= 14

        content += """endstream
endobj

5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj

xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000{0:06d} 00000 n 

trailer
<< /Size 6 /Root 1 0 R >>
startxref
{0}
%%EOF"""

        # Calculate offsets
        xref_offsets = [9, 58, 115, 266]
        content_length = len(content)

        return content.encode('latin-1', errors='replace')


def build_daily_report_data(
    orders: List[Dict[str, Any]],
    payments: List[Dict[str, Any]] = None,
    expenses: List[Dict[str, Any]] = None,
    date: str = "",
) -> Dict[str, Any]:
    """
    Build report data from raw data.

    Args:
        orders: List of order dictionaries
        payments: List of payment dictionaries
        expenses: List of expense dictionaries
        date: Report date (YYYY-MM-DD)

    Returns:
        Dict with summary, orders, and financial data
    """
    # Summary
    total_orders = len(orders)
    delivered = sum(1 for o in orders if o.get('status') == 'DELIVERED')
    cancelled = sum(1 for o in orders if o.get('status') == 'CANCELLED')
    revenue = sum(o.get('total', 0) for o in orders if o.get('status') == 'DELIVERED')

    # Payments
    received = sum(p.get('amount', 0) for p in (payments or []) if p.get('status') == 'PAID')
    pending_amount = sum(o.get('total', 0) for o in orders
                         if o.get('payment_status') == 'PENDING' and o.get('status') != 'CANCELLED')

    # Expenses
    total_expenses = sum(e.get('amount', 0) for e in (expenses or [])
                         if e.get('status') == 'ACTIVE')

    # Product quantities
    quantity_p13 = 0
    quantity_water = 0
    for order in orders:
        for item in order.get('items', []):
            qty = item.get('quantity', 0)
            name = (item.get('product_nome', '') or item.get('name', '')).lower()
            if 'p13' in name or 'gás' in name or 'gas' in name:
                quantity_p13 += qty
            elif 'água' in name or 'agua' in name or '20l' in name:
                quantity_water += qty

    return {
        "date": date or datetime.now().strftime('%Y-%m-%d'),
        "summary": {
            "total_orders": total_orders,
            "delivered": delivered,
            "cancelled": cancelled,
            "revenue": revenue,
            "received": received,
            "pending_amount": pending_amount,
            "expenses": total_expenses,
            "quantity_p13": quantity_p13,
            "quantity_water": quantity_water,
        },
        "orders": orders,
        "financial": {
            "received": received,
            "pending": pending_amount,
            "overdue": 0,
            "expenses": total_expenses,
        },
    }
