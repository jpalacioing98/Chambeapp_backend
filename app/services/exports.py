"""Service layer: PDF and CSV exports for reports (P2-3)."""

import csv
import io
from datetime import datetime, timezone


def generar_pdf_certificado(data: dict) -> bytes:
    """Generate a PDF income certificate.

    Uses reportlab to create a formatted PDF with the certificate data.
    Returns raw PDF bytes.
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75*inch, bottomMargin=0.75*inch)
        styles = getSampleStyleSheet()
        elements = []

        # Title
        title_style = ParagraphStyle('Title2', parent=styles['Title'], fontSize=18, spaceAfter=20)
        elements.append(Paragraph("Certificado de Ingresos", title_style))
        elements.append(Spacer(1, 12))

        # User info
        info_style = styles['Normal']
        elements.append(Paragraph(f"<b>Nombre:</b> {data.get('nombre', 'N/A')}", info_style))
        elements.append(Paragraph(f"<b>Verificado:</b> {'Si' if data.get('verificado') else 'No'}", info_style))
        elements.append(Paragraph(f"<b>Calificacion Promedio:</b> {data.get('calificacion_promedio', 0):.1f}", info_style))

        periodo = data.get('periodo', {})
        elements.append(Paragraph(
            f"<b>Periodo:</b> {periodo.get('desde', 'N/A')} al {periodo.get('hasta', 'N/A')}",
            info_style
        ))
        elements.append(Spacer(1, 12))

        # Summary
        elements.append(Paragraph(f"<b>Total Ingresos:</b> ${data.get('total_ingresos', 0):,} COP", info_style))
        elements.append(Paragraph(f"<b>Promedio Mensual:</b> ${data.get('promedio_mensual', 0):,} COP", info_style))
        elements.append(Paragraph(f"<b>Servicios Completados:</b> {data.get('servicios_completados', 0)}", info_style))
        elements.append(Spacer(1, 12))

        # History table
        historial = data.get('historial', [])
        if historial:
            elements.append(Paragraph("<b>Historial Mensual:</b>", info_style))
            table_data = [["Mes", "Ingreso (COP)", "Servicios"]]
            for h in historial:
                table_data.append([
                    h.get('mes', ''),
                    f"${h.get('ingreso', 0):,}",
                    str(h.get('servicios', 0)),
                ])

            table = Table(table_data, colWidths=[2*inch, 2.5*inch, 1.5*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            elements.append(table)

        # Footer
        elements.append(Spacer(1, 24))
        footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        elements.append(Paragraph(f"Documento generado automaticamente por ChambeApp - {now}", footer_style))

        doc.build(elements)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

    except ImportError:
        # Fallback: return a minimal PDF if reportlab not installed
        return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<</Font<</F1 4 0 R>>>>>>endobj 4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj xref 0 5 0000000000 65535 f 0000000009 00000 n 0000000058 00000 n 0000000115 00000 n 0000000266 00000 n 0000000340 00000 n trailer<</Size 5/Root 1 0 R>>startxref 419 %%EOF"


def generar_csv_historial(payments: list) -> bytes:
    """Generate a CSV of payment history.

    Takes a list of payment dicts (or objects with the right attributes).
    Returns raw CSV bytes encoded in UTF-8.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "ID", "Contrato", "Monto", "Comision PDS", "Comision Solicitante",
        "Estado", "Pasarela", "Referencia", "Creado", "Liberado",
    ])

    for p in payments:
        if hasattr(p, '__dict__'):
            writer.writerow([
                p.id,
                p.contract_id,
                p.monto,
                p.comision_pds,
                p.comision_solicitante,
                p.estado.value if hasattr(p.estado, 'value') else p.estado,
                p.pasarela,
                p.referencia_pasarela or "",
                p.creado_en.isoformat() if p.creado_en else "",
                p.liberado_en.isoformat() if p.liberado_en else "",
            ])
        else:
            writer.writerow([
                p.get("id", ""),
                p.get("contract_id", ""),
                p.get("monto", ""),
                p.get("comision_pds", ""),
                p.get("comision_solicitante", ""),
                p.get("estado", ""),
                p.get("pasarela", ""),
                p.get("referencia_pasarela", ""),
                p.get("creado_en", ""),
                p.get("liberado_en", ""),
            ])

    csv_bytes = output.getvalue().encode("utf-8")
    output.close()
    return csv_bytes
