"""
PDF Export Tool

Generates a professionally formatted PDF report combining
Requirements, Design Alternatives, and Feasibility Report sections.
"""

import re
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak
)
from loguru import logger


BLUE      = colors.HexColor("#2E75B6")
DARK_BLUE = colors.HexColor("#1F4E79")
LIGHT_BLUE = colors.HexColor("#D5E8F0")
GREY      = colors.HexColor("#666666")
LIGHT_GREY = colors.HexColor("#F5F5F5")


def build_styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("title", parent=base["Title"],
            fontSize=22, textColor=DARK_BLUE, spaceAfter=6, fontName="Helvetica-Bold"),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"],
            fontSize=11, textColor=BLUE, spaceAfter=16, fontName="Helvetica"),
        "h1": ParagraphStyle("h1", parent=base["Heading1"],
            fontSize=14, textColor=DARK_BLUE, spaceBefore=18, spaceAfter=6,
            fontName="Helvetica-Bold", borderPadding=(0,0,4,0)),
        "h2": ParagraphStyle("h2", parent=base["Heading2"],
            fontSize=12, textColor=BLUE, spaceBefore=12, spaceAfter=4,
            fontName="Helvetica-Bold"),
        "body": ParagraphStyle("body", parent=base["Normal"],
            fontSize=10, textColor=colors.black, spaceAfter=6,
            fontName="Helvetica", leading=14),
        "bullet": ParagraphStyle("bullet", parent=base["Normal"],
            fontSize=10, textColor=colors.black, spaceAfter=3,
            leftIndent=16, fontName="Helvetica", leading=13),
        "label": ParagraphStyle("label", parent=base["Normal"],
            fontSize=9, textColor=GREY, spaceAfter=2, fontName="Helvetica"),
        "code": ParagraphStyle("code", parent=base["Code"],
            fontSize=9, textColor=colors.HexColor("#333333"),
            backColor=LIGHT_GREY, fontName="Courier"),
        "recommend": ParagraphStyle("recommend", parent=base["Normal"],
            fontSize=11, textColor=DARK_BLUE, spaceBefore=8, spaceAfter=8,
            fontName="Helvetica-Bold"),
    }
    return styles


def clean(text: str) -> str:
    """Remove markdown symbols for plain text in PDF."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'`(.+?)`', r'\1', text)
    return text.strip()


def export_pdf(result: dict, output_path: str = None) -> str:
    """
    Generate a PDF report from the agent pipeline result.

    Args:
        result:      Full result dict from DesignAgent.run()
        output_path: Optional path to save PDF

    Returns:
        Path to generated PDF
    """
    req   = result.get("requirements", {})
    alts  = result.get("alternatives", [])
    ev    = result.get("evaluation", {})
    rep   = result.get("report", {})

    if not output_path:
        ts          = datetime.now().strftime("%Y%m%d%H%M%S")
        report_id   = rep.get("report_id", f"GDA-{ts}")
        output_path = f"outputs/reports/{report_id}.pdf"

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize     = letter,
        leftMargin   = 0.8 * inch,
        rightMargin  = 0.8 * inch,
        topMargin    = 0.9 * inch,
        bottomMargin = 0.8 * inch,
        title        = f"Generative Design Report — {req.get('component_name', '')}",
        author       = "Generative Design Assistant v1.0",
    )

    S     = build_styles()
    story = []

    # ── Cover ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("GENERATIVE DESIGN FEASIBILITY REPORT", S["label"]))
    story.append(Paragraph(req.get("component_name", "Engineering Component"), S["title"]))
    story.append(Paragraph(
        f"Report ID: {rep.get('report_id', 'N/A')}  &nbsp;&nbsp;|&nbsp;&nbsp;  "
        f"Generated: {datetime.now().strftime('%d %B %Y %H:%M')}",
        S["subtitle"]
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=BLUE, spaceAfter=16))

    # Executive Summary
    exec_summary = rep.get("executive_summary", "")
    if exec_summary:
        story.append(Paragraph("Executive Summary", S["h1"]))
        story.append(HRFlowable(width="100%", thickness=0.5, color=LIGHT_BLUE, spaceAfter=6))
        story.append(Paragraph(clean(exec_summary), S["body"]))
        story.append(Spacer(1, 0.1 * inch))

    # ── Section 1: Requirements ────────────────────────────────────────
    story.append(Paragraph("1. Engineering Requirements", S["h1"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LIGHT_BLUE, spaceAfter=6))

    req_data = [
        ["Field", "Value"],
        ["Component", req.get("component_name", "")],
        ["Priority", req.get("priority", "").upper()],
        ["Design Space", req.get("design_space", "Not specified")],
    ]
    req_table = Table(req_data, colWidths=[1.8*inch, 5.2*inch])
    req_table.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), DARK_BLUE),
        ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,-1), 9),
        ("BACKGROUND",   (0,1), (0,-1), LIGHT_BLUE),
        ("FONTNAME",     (0,1), (0,-1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT_GREY]),
        ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
    ]))
    story.append(req_table)
    story.append(Spacer(1, 0.1 * inch))

    func_reqs = req.get("functional_requirements", [])
    if func_reqs:
        story.append(Paragraph("Functional Requirements:", S["h2"]))
        for r in func_reqs:
            story.append(Paragraph(f"• {clean(str(r))}", S["bullet"]))

    perf = req.get("performance_targets", {})
    if perf:
        story.append(Paragraph("Performance Targets:", S["h2"]))
        for k, v in perf.items():
            story.append(Paragraph(f"• {k}: {v}", S["bullet"]))

    constraints = req.get("constraints", [])
    if constraints:
        story.append(Paragraph("Constraints:", S["h2"]))
        for c in constraints:
            story.append(Paragraph(f"• {clean(str(c))}", S["bullet"]))

    # ── Section 2: Design Alternatives ────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("2. Design Alternatives", S["h1"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LIGHT_BLUE, spaceAfter=6))

    rec_id = ev.get("recommended", "B")

    for alt in alts:
        is_rec = alt["id"] == rec_id
        alt_title = f"Alternative {alt['id']}: {alt.get('name', '')}{'  ★ RECOMMENDED' if is_rec else ''}"
        story.append(Paragraph(alt_title, S["h2"]))

        alt_data = [
            ["Metric", "Value"],
            ["Material", alt.get("material", "")],
            ["Manufacturing Process", alt.get("manufacturing_process", "")],
            ["Estimated Weight", f"{alt.get('estimated_weight_kg', '')} kg"],
            ["Cost Index", f"{alt.get('estimated_cost_index', '')}/5"],
            ["Performance Score", f"{alt.get('performance_score', '')}/5"],
            ["Sustainability Score", f"{alt.get('sustainability_score', '')}/5"],
            ["Feasibility", alt.get("feasibility", "")],
            ["Overall Score", f"{ev.get('scores', {}).get(alt['id'], 'N/A')}/100"],
        ]
        alt_table = Table(alt_data, colWidths=[2.2*inch, 4.8*inch])
        bg = LIGHT_BLUE if is_rec else LIGHT_GREY
        alt_table.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,0), DARK_BLUE),
            ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
            ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",     (0,0), (-1,-1), 9),
            ("BACKGROUND",   (0,1), (0,-1), bg),
            ("FONTNAME",     (0,1), (0,-1), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
            ("LEFTPADDING",  (0,0), (-1,-1), 8),
            ("TOPPADDING",   (0,0), (-1,-1), 4),
            ("BOTTOMPADDING",(0,0), (-1,-1), 4),
        ]))
        story.append(alt_table)
        story.append(Spacer(1, 0.06 * inch))

        story.append(Paragraph(clean(alt.get("concept", "")), S["body"]))

        advantages = alt.get("advantages", [])
        if advantages:
            story.append(Paragraph("Advantages:", S["label"]))
            for a in advantages:
                story.append(Paragraph(f"• {clean(str(a))}", S["bullet"]))

        disadvantages = alt.get("disadvantages", [])
        if disadvantages:
            story.append(Paragraph("Disadvantages:", S["label"]))
            for d in disadvantages:
                story.append(Paragraph(f"• {clean(str(d))}", S["bullet"]))

        story.append(Spacer(1, 0.15 * inch))

    # ── Section 3: Evaluation & Recommendation ────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("3. Evaluation & Recommendation", S["h1"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LIGHT_BLUE, spaceAfter=6))

    ranking = ev.get("ranking", [])
    if ranking:
        story.append(Paragraph(f"Ranking: {' > '.join(ranking)}", S["body"]))

    rec_rationale = ev.get("recommendation_rationale", "")
    if rec_rationale:
        story.append(Paragraph(
            f"Recommendation: Alternative {rec_id}", S["recommend"]
        ))
        story.append(Paragraph(clean(rec_rationale), S["body"]))

    next_steps = rep.get("next_steps", [])
    if next_steps:
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph("Next Steps:", S["h2"]))
        for i, step in enumerate(next_steps, 1):
            story.append(Paragraph(f"{i}. {clean(str(step))}", S["bullet"]))

    # Knowledge sources
    sources = rep.get("knowledge_sources", [])
    if sources:
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph("Knowledge Sources:", S["h2"]))
        for s in sources:
            story.append(Paragraph(f"• {clean(str(s))}", S["bullet"]))

    # ── Footer note ────────────────────────────────────────────────────
    story.append(Spacer(1, 0.3 * inch))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LIGHT_BLUE, spaceAfter=6))
    story.append(Paragraph(
        f"Generated by Generative Design Assistant v1.0  |  "
        f"{datetime.now().strftime('%d %B %Y')}",
        S["label"]
    ))

    doc.build(story)
    logger.success(f"PDF exported: {output_path}")
    return output_path