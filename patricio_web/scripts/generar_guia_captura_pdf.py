#!/usr/bin/env python3
"""Genera PDF de la guía de captura de foto web con estilo Patricio."""

from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PKG_DIR = Path(__file__).resolve().parents[1]
MD_PATH = PKG_DIR / 'GUIA_CAPTURA_FOTO_WEB.md'
OUT_PATH = PKG_DIR / 'GUIA_CAPTURA_FOTO_WEB.pdf'

COLOR_PRIMARY = colors.HexColor('#1a237e')
COLOR_ACCENT = colors.HexColor('#f54aa1')
COLOR_ACCENT2 = colors.HexColor('#3949ab')
COLOR_CODE_BG = colors.HexColor('#eef1f8')
COLOR_MUTED = colors.HexColor('#546e7a')
COLOR_WHITE = colors.white


def _esc(text: str) -> str:
    return (
        text.replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )


def _inline_md(text: str) -> str:
    text = _esc(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'`([^`]+)`', r'<font face="Courier" color="#3949ab">\1</font>', text)
    text = re.sub(r'«(.+?)»', r'<i>\1</i>', text)
    return text


def _parse_table(lines: list[str]) -> tuple[list[list[str]], list[str]]:
    rows = []
    for line in lines:
        if not line.strip().startswith('|'):
            break
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if all(re.match(r'^[-:]+$', c) for c in cells):
            continue
        rows.append(cells)
    return rows, lines[len(rows) + (1 if rows else 0):]


def _build_styles():
    base = getSampleStyleSheet()
    return {
        'cover_title': ParagraphStyle(
            'CoverTitle',
            parent=base['Title'],
            fontSize=26,
            leading=32,
            textColor=COLOR_WHITE,
            alignment=TA_CENTER,
            spaceAfter=12,
        ),
        'cover_sub': ParagraphStyle(
            'CoverSub',
            parent=base['Normal'],
            fontSize=13,
            leading=18,
            textColor=colors.HexColor('#e8eaf6'),
            alignment=TA_CENTER,
        ),
        'h2': ParagraphStyle(
            'H2',
            parent=base['Heading2'],
            fontSize=16,
            leading=20,
            textColor=COLOR_PRIMARY,
            spaceBefore=16,
            spaceAfter=8,
            borderPadding=(0, 0, 4, 0),
        ),
        'h3': ParagraphStyle(
            'H3',
            parent=base['Heading3'],
            fontSize=12,
            leading=15,
            textColor=COLOR_ACCENT2,
            spaceBefore=10,
            spaceAfter=6,
        ),
        'body': ParagraphStyle(
            'Body',
            parent=base['Normal'],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#263238'),
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ),
        'bullet': ParagraphStyle(
            'Bullet',
            parent=base['Normal'],
            fontSize=10,
            leading=14,
            leftIndent=14,
            bulletIndent=0,
            spaceAfter=4,
        ),
        'code': ParagraphStyle(
            'Code',
            parent=base['Code'],
            fontSize=8.5,
            leading=11,
            fontName='Courier',
            textColor=colors.HexColor('#1a237e'),
            backColor=COLOR_CODE_BG,
            borderPadding=8,
            spaceAfter=8,
        ),
        'footer': ParagraphStyle(
            'Footer',
            parent=base['Normal'],
            fontSize=8,
            textColor=COLOR_MUTED,
            alignment=TA_CENTER,
        ),
    }


def _draw_header_footer(canvas, doc):
    canvas.saveState()
    w, h = A4
    if canvas.getPageNumber() == 1:
        canvas.setFillColor(COLOR_ACCENT)
        canvas.rect(0, h - 8 * mm, w, 8 * mm, fill=1, stroke=0)
        canvas.setFillColor(COLOR_PRIMARY)
        canvas.rect(0, 0, w, 6 * mm, fill=1, stroke=0)
    else:
        canvas.setFillColor(COLOR_ACCENT)
        canvas.rect(0, h - 5 * mm, w, 5 * mm, fill=1, stroke=0)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(COLOR_MUTED)
        canvas.drawString(2 * cm, 1.2 * cm, 'Patricio — Captura de foto (Web)')
        canvas.drawRightString(w - 2 * cm, 1.2 * cm, f'Página {canvas.getPageNumber()}')
    canvas.restoreState()


def _cover_page(styles) -> list:
    flow = []
    flow.append(Spacer(1, 3.5 * cm))
    flow.append(Paragraph('Patricio', styles['cover_sub']))
    flow.append(Spacer(1, 0.4 * cm))
    flow.append(
        Paragraph(
            'Guía de instalación y pruebas<br/>Captura de foto desde admin.html',
            styles['cover_title'],
        )
    )
    flow.append(Spacer(1, 0.8 * cm))
    flow.append(
        Paragraph(
            'Stream cámara · Canvas · Descarga JPG · H11-T9',
            styles['cover_sub'],
        )
    )
    flow.append(Spacer(1, 2 * cm))
    info = Table(
        [
            ['Panel web', 'admin.html → Vista de cámara'],
            ['Stream', ':8080 /patricio/camera_processed'],
            ['Archivo descargado', 'captura_patricio_fecha.jpg'],
        ],
        colWidths=[5 * cm, 9 * cm],
    )
    info.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#3949ab')),
                ('TEXTCOLOR', (0, 0), (-1, -1), COLOR_WHITE),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Courier'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#3949ab'), colors.HexColor('#5c6bc0')]),
            ]
        )
    )
    flow.append(info)
    flow.append(Spacer(1, 1.5 * cm))
    flow.append(Paragraph('Patricio 2026 · Documento para el equipo educativo', styles['cover_sub']))
    flow.append(PageBreak())
    return flow


def _md_to_flowables(md_text: str, styles) -> list:
    flow = []
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped == '---':
            flow.append(Spacer(1, 6))
            flow.append(HRFlowable(width='100%', thickness=0.5, color=COLOR_ACCENT, spaceAfter=8))
            i += 1
            continue

        if stripped.startswith('## '):
            title = stripped[3:].strip()
            if title.startswith('1. '):
                pass
            flow.append(Paragraph(_inline_md(title), styles['h2']))
            i += 1
            continue

        if stripped.startswith('### '):
            flow.append(Paragraph(_inline_md(stripped[4:]), styles['h3']))
            i += 1
            continue

        if stripped.startswith('```'):
            lang = stripped[3:].strip()
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1
            code = '\n'.join(code_lines).rstrip()
            if lang:
                flow.append(Paragraph(f'<font size="8" color="#f54aa1">{_esc(lang)}</font>', styles['body']))
            flow.append(Preformatted(code, styles['code']))
            continue

        if stripped.startswith('|') and '|' in stripped[1:]:
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1
            rows, _ = _parse_table(table_lines)
            if rows:
                t = Table(rows, repeatRows=1, hAlign='LEFT')
                t.setStyle(
                    TableStyle(
                        [
                            ('BACKGROUND', (0, 0), (-1, 0), COLOR_ACCENT2),
                            ('TEXTCOLOR', (0, 0), (-1, 0), COLOR_WHITE),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, -1), 9),
                            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COLOR_WHITE, COLOR_CODE_BG]),
                            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#cfd8dc')),
                            ('LEFTPADDING', (0, 0), (-1, -1), 8),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                            ('TOPPADDING', (0, 0), (-1, -1), 6),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ]
                    )
                )
                flow.append(Spacer(1, 4))
                flow.append(t)
                flow.append(Spacer(1, 8))
            continue

        if stripped.startswith('- [ ] '):
            text = '☐  ' + stripped[6:]
            flow.append(Paragraph(_inline_md(text), styles['bullet']))
            i += 1
            continue

        if stripped.startswith('- '):
            flow.append(Paragraph('• ' + _inline_md(stripped[2:]), styles['bullet']))
            i += 1
            continue

        if re.match(r'^\d+\.\s', stripped):
            flow.append(Paragraph(_inline_md(stripped), styles['bullet']))
            i += 1
            continue

        if stripped.startswith('*') and stripped.endswith('*') and not stripped.startswith('**'):
            flow.append(Paragraph(f'<i>{_esc(stripped.strip("*"))}</i>', styles['footer']))
            i += 1
            continue

        if stripped:
            flow.append(Paragraph(_inline_md(stripped), styles['body']))
        i += 1

    return flow


def main():
    if not MD_PATH.is_file():
        raise SystemExit(f'No encontrado: {MD_PATH}')

    md_text = MD_PATH.read_text(encoding='utf-8')
    # Omitir título duplicado del MD (va en portada)
    md_body = re.sub(r'^# .+\n+', '', md_text, count=1)

    styles = _build_styles()
    doc = SimpleDocTemplate(
        str(OUT_PATH),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2.2 * cm,
        bottomMargin=2 * cm,
        title='Guía Patricio — Captura foto web',
        author='Patricio',
    )

    story = []
    story.extend(_cover_page(styles))
    story.extend(_md_to_flowables(md_body, styles))

    def first_page(canvas, doc):
        w, h = A4
        canvas.saveState()
        canvas.setFillColor(COLOR_PRIMARY)
        canvas.rect(0, 0, w, h, fill=1, stroke=0)
        canvas.setFillColor(COLOR_ACCENT)
        canvas.circle(w - 2.5 * cm, h - 3 * cm, 2.2 * cm, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor('#5c6bc0'))
        canvas.circle(2 * cm, 2.5 * cm, 1.8 * cm, fill=1, stroke=0)
        canvas.restoreState()
        _draw_header_footer(canvas, doc)

    doc.build(story, onFirstPage=first_page, onLaterPages=_draw_header_footer)
    print(f'PDF generado: {OUT_PATH}')


if __name__ == '__main__':
    main()
