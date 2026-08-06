from __future__ import annotations

import base64
import gzip
import html
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfbase.ttfonts import TTFont


NAVY = colors.HexColor("#0F172A")
BLUE = colors.HexColor("#2563EB")
LIGHT_BLUE = colors.HexColor("#EFF6FF")
PALE = colors.HexColor("#F8FAFC")
MUTED = colors.HexColor("#64748B")
GRID = colors.HexColor("#D8E2F0")
ROOT = Path(__file__).resolve().parents[1]
CN_FONT_NAME = "AIUsedCarCN"
CN_FONT_PATH = ROOT / "assets" / "fonts" / "AIUsedCarCN.ttf"
CN_FONT_ARCHIVE_PATH = ROOT / "assets" / "fonts" / "AIUsedCarCN.ttf.gz.b64"
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _now_cn() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def _register_cn_font() -> None:
    if CN_FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return
    font_path = CN_FONT_PATH
    if not font_path.is_file() and CN_FONT_ARCHIVE_PATH.is_file():
        runtime_font_dir = Path("/tmp/ai_used_car_fonts")
        runtime_font_dir.mkdir(parents=True, exist_ok=True)
        runtime_font_path = runtime_font_dir / CN_FONT_PATH.name
        if not runtime_font_path.is_file():
            packed = base64.b64decode(CN_FONT_ARCHIVE_PATH.read_text(encoding="ascii"))
            runtime_font_path.write_bytes(gzip.decompress(packed))
        font_path = runtime_font_path
    if not font_path.is_file():
        raise FileNotFoundError(f"pricing PDF Chinese font is missing: {CN_FONT_PATH}")
    pdfmetrics.registerFont(TTFont(CN_FONT_NAME, str(font_path)))


def build_pricing_pdf_report(payload: dict[str, Any]) -> tuple[BytesIO, str]:
    result = _dict(payload.get("result"))
    metrics = _dict(result.get("metrics"))
    report = _dict(payload.get("report"))
    if not report:
        report = _dict(metrics.get("pricing_final_report"))
    if not report:
        report = _dict(_dict(metrics.get("pricing_agent")).get("final_report"))
    if not report:
        raise ValueError("pricing final report is missing")
    slots = _dict(payload.get("slots")) or _dict(metrics.get("six_elements")) or _dict(metrics.get("slots"))
    calculator = _dict(payload.get("calculator"))

    _register_cn_font()
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=16 * mm,
        title="AI懂车价 · 单车定价报告",
        author="AI懂车价",
    )
    styles = _styles()
    story: list[Any] = []
    story.extend(_header(report, slots, styles))
    story.extend(_ai_summary(report, styles))
    story.extend(_four_prices(report, styles))
    story.extend(_confidence_breakdown(report, styles))
    story.extend(_vehicle_elements(slots, styles))
    story.extend(_price_formation(report, styles))
    story.extend(_comparable_evidence(report, styles))
    story.extend(_profit(calculator, report, styles))
    story.extend(_pricing_evidence(report, metrics, styles))
    story.extend(_action_guide(report, styles))
    document.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    output.seek(0)
    vehicle = _clean_filename(report.get("vehicle_title") or slots.get("standard_vehicle") or "当前车辆")
    stamp = _now_cn().strftime("%Y%m%d_%H%M%S")
    return output, f"AI懂车价_单车定价报告_{vehicle}_{stamp}.pdf"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("cn_title", parent=base["Title"], fontName=CN_FONT_NAME, fontSize=23, leading=30, textColor=colors.white, alignment=TA_LEFT),
        "subtitle": ParagraphStyle("cn_subtitle", parent=base["BodyText"], fontName=CN_FONT_NAME, fontSize=9, leading=14, textColor=colors.HexColor("#CBD5E1")),
        "h2": ParagraphStyle("cn_h2", parent=base["Heading2"], fontName=CN_FONT_NAME, fontSize=15, leading=21, textColor=NAVY, spaceBefore=8, spaceAfter=8),
        "h3": ParagraphStyle("cn_h3", parent=base["Heading3"], fontName=CN_FONT_NAME, fontSize=11, leading=16, textColor=NAVY, spaceAfter=4),
        "body": ParagraphStyle("cn_body", parent=base["BodyText"], fontName=CN_FONT_NAME, fontSize=9.3, leading=15, textColor=colors.HexColor("#334155")),
        "small": ParagraphStyle("cn_small", parent=base["BodyText"], fontName=CN_FONT_NAME, fontSize=7.8, leading=12, textColor=MUTED),
        "value": ParagraphStyle("cn_value", parent=base["BodyText"], fontName=CN_FONT_NAME, fontSize=16, leading=21, textColor=NAVY),
        "blue_value": ParagraphStyle("cn_blue_value", parent=base["BodyText"], fontName=CN_FONT_NAME, fontSize=20, leading=26, textColor=BLUE),
    }


def _header(report: dict[str, Any], slots: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    vehicle = _text(report.get("vehicle_title") or slots.get("standard_vehicle") or "当前车辆")
    data = [[
        Paragraph("AI懂车价 · 单车定价报告", styles["title"]),
        Paragraph(f"估价对象<br/><font size='13'>{_escape(vehicle)}</font><br/>生成时间 {_escape(_now_cn().strftime('%Y-%m-%d %H:%M'))}", styles["subtitle"]),
    ]]
    table = Table(data, colWidths=[118 * mm, 62 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    return [table, Spacer(1, 6 * mm)]


def _ai_summary(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    summary = _dict(report.get("ai_summary"))
    decision_summary = _dict(report.get("decision_summary"))
    decision = _text(
        decision_summary.get("decision")
        or summary.get("decision")
        or report.get("headline")
        or report.get("summary_action")
    )
    why_items = [str(item) for item in summary.get("why_items") or [] if item]
    if not why_items:
        why_items = [str(item) for item in report.get("internal_basis") or [] if item]
    risks = [str(item) for item in report.get("main_risks") or [] if item][:2]
    next_action = _text(
        _dict(report.get("decision_card")).get("next_best_action")
        or decision_summary.get("next_action")
        or report.get("summary_action")
    )
    body: list[Any] = [Paragraph("收车决策摘要", styles["h2"])]
    body.append(_callout("业务结论", decision, styles, "#EFF6FF"))
    if why_items:
        body.extend([
            Spacer(1, 2 * mm),
            Paragraph("<b>核心依据</b><br/>" + "<br/>".join(f"· {_escape(item)}" for item in why_items[:3]), styles["body"]),
        ])
    if risks:
        body.extend([
            Spacer(1, 2 * mm),
            Paragraph("<b>主要风险</b><br/>" + "<br/>".join(f"· {_escape(item)}" for item in risks), styles["body"]),
        ])
    if next_action:
        body.extend([Spacer(1, 2 * mm), Paragraph(f"<b>下一步：</b>{_escape(next_action)}", styles["body"])])
    return [KeepTogether(body), Spacer(1, 3 * mm)]


def _four_prices(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    rows = [
        ("建议挂牌价", report.get("listing_price_yuan"), report.get("listing_price_low_yuan"), report.get("listing_price_high_yuan")),
        ("预计实际售车价", report.get("sale_price_yuan"), report.get("sale_price_low_yuan"), report.get("sale_price_high_yuan")),
        ("建议收车价", report.get("purchase_price_yuan") or report.get("point_price_yuan"), report.get("purchase_price_low_yuan") or report.get("lower_yuan"), report.get("purchase_price_high_yuan") or report.get("upper_yuan")),
        ("最高收车价", report.get("max_c2b_price_yuan") or report.get("upper_yuan"), None, None),
    ]
    cards = []
    for label, point, low, high in rows:
        cards.append(Paragraph(f"<font color='#64748B' size='8'>{_escape(label)}</font><br/><font size='14'><b>{_escape(_wan(point))}</b></font><br/><font color='#2563EB' size='8'>{_escape(_range(low, high) if low or high else '内部安全上限')}</font>", styles["body"]))
    table = Table([cards], colWidths=[45 * mm] * 4)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.7, GRID),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return [Paragraph("四个核心价格", styles["h2"]), table, Spacer(1, 3 * mm)]


def _confidence_breakdown(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    breakdown = _dict(report.get("confidence_breakdown"))
    entries = []
    for key, label in (("model", "模型置信度"), ("evidence", "证据置信度"), ("execution", "执行置信度")):
        item = _dict(breakdown.get(key))
        level = _text(item.get("level") or "待判断")
        reason = _text(item.get("reason") or "暂无足够结构化信息")
        entries.append(Paragraph(f"<font color='#64748B' size='8'>{label}</font><br/><b>{_escape(level)}</b><br/><font size='7' color='#64748B'>{_escape(reason)}</font>", styles["body"]))
    table = Table([entries], colWidths=[60 * mm] * 3)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("BOX", (0, 0), (-1, -1), 0.5, GRID),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return [Paragraph("置信度说明", styles["h2"]), table, Spacer(1, 3 * mm)]


def _vehicle_elements(slots: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    condition = _condition_display(slots)
    values = [
        ("标准车型", slots.get("standard_vehicle") or slots.get("trim") or slots.get("series")),
        ("上牌时间", slots.get("first_license_date") or slots.get("first_license_year")),
        ("里程", f"{slots.get('mileage_wan_km')}万公里" if slots.get("mileage_wan_km") not in (None, "") else "-"),
        ("城市", slots.get("city")),
        ("过户次数", f"{slots.get('transfer_count')}次" if slots.get("transfer_count") not in (None, "") else "-"),
        ("颜色", slots.get("color")),
        ("车况", condition),
    ]
    cells = [Paragraph(f"<font color='#64748B' size='8'>{_escape(label)}</font><br/><b>{_escape(_text(value) or '-')}</b>", styles["body"]) for label, value in values]
    table = Table([cells[:4], cells[4:] + [""]], colWidths=[45 * mm] * 4)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("BOX", (0, 0), (-1, -1), 0.5, GRID),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return [Paragraph("车辆七要素", styles["h2"]), table, Spacer(1, 4 * mm)]


def _price_formation(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    items = [_dict(item) for item in report.get("price_formation") or []]
    if not items:
        return []
    rows = [["步骤", "阶段结论", "如何影响最终报价"]]
    for item in items[:6]:
        rows.append([
            _text(item.get("title")),
            _text(item.get("conclusion")),
            _text(item.get("detail")),
        ])
    table = Table([[Paragraph(_escape(cell), styles["small"]) for cell in row] for row in rows], colWidths=[38 * mm, 58 * mm, 84 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, -1), PALE),
        ("BOX", (0, 0), (-1, -1), 0.5, GRID),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return [Paragraph("价格形成过程", styles["h2"]), table, Spacer(1, 3 * mm)]


def _comparable_evidence(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    items = [_dict(item) for item in report.get("comparable_evidence") or []]
    count = int(_number(report.get("candidate_count")) or len(items))
    if not items:
        note = "当前没有可展示的逐车明细，可比车只用于模型内部方向校验，不作为单独追价依据。"
        return [Paragraph("可比车与证据", styles["h2"]), _callout(f"严格可比车 {count} 条", note, styles, "#FFF7ED"), Spacer(1, 3 * mm)]
    intro = (
        f"当前展示 {len(items)} 条可比证据。"
        + ("样本仍偏少，只能校验价格方向，不能单独支撑高置信决策。" if count < 3 else "系统已按车辆条件差异决定纳入或降权。")
    )
    rows = [["可比车", "关键条件", "价格口径", "日期", "差异与使用方式"]]
    for item in items[:10]:
        condition_parts = []
        if item.get("model_year") not in (None, ""):
            condition_parts.append(f"{item.get('model_year')}款")
        if item.get("mileage_wan_km") not in (None, ""):
            condition_parts.append(f"{item.get('mileage_wan_km')}万公里")
        if item.get("city"):
            condition_parts.append(str(item.get("city")))
        if item.get("transfer_count") not in (None, ""):
            condition_parts.append(f"过户{item.get('transfer_count')}次")
        differences = [str(value) for value in item.get("differences") or [] if value]
        use = "；".join(differences + [_text(item.get("inclusion_reason"))])
        rows.append([
            _text(item.get("title") or "相近车源"),
            " / ".join(condition_parts) or "车辆明细不足",
            f"{_text(item.get('price_type') or '市场参考')} {_wan(item.get('price_yuan'))}",
            _text(item.get("data_date") or "未提供"),
            use,
        ])
    table = Table([[Paragraph(_escape(cell), styles["small"]) for cell in row] for row in rows], colWidths=[35 * mm, 38 * mm, 35 * mm, 24 * mm, 48 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, GRID),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return [Paragraph("可比车与证据", styles["h2"]), Paragraph(_escape(intro), styles["body"]), Spacer(1, 2 * mm), table, Spacer(1, 3 * mm)]


def _profit(calculator: dict[str, Any], report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    purchase = _number(calculator.get("currentPurchaseYuan")) or _number(report.get("purchase_price_yuan"))
    sale = _number(calculator.get("currentSaleYuan")) or _number(report.get("sale_price_yuan"))
    recon = _number(calculator.get("reconYuan")) or _number(report.get("estimated_recon_cost_yuan"))
    platform = _number(calculator.get("platformYuan")) or _number(report.get("platform_service_cost_yuan"))
    buffer = _number(calculator.get("bufferYuan")) or _number(report.get("risk_buffer_yuan"))
    spread = sale - purchase
    costs = recon + platform + buffer
    gross = spread - costs
    rate = gross / sale if sale else 0
    if costs > 0:
        data = [
            ["试算售车价", "试算收车价", "收售价格差", "成本合计", "预计净毛利 / 毛利率"],
            [_wan(sale), _wan(purchase), _signed_wan(spread), _wan(costs), f"{_signed_wan(gross)} / {rate * 100:.1f}%"],
        ]
        col_widths = [36 * mm] * 5
        breakdown = (
            f"净毛利 = 售车价 {_wan(sale)} - 收车价 {_wan(purchase)}"
            f" - 整备 {_wan(recon)} - 平台/运营 {_wan(platform)} - 风险缓冲 {_wan(buffer)}。"
        )
    else:
        data = [
            ["预计实际售车价", "建议收车价", "收售价格差 / 差价率"],
            [_wan(sale), _wan(purchase), f"{_signed_wan(spread)} / {rate * 100:.1f}%"],
        ]
        col_widths = [60 * mm] * 3
        breakdown = "页面默认只展示售车价与收车价的差额；各门店可在利润计算器中按自身口径补充整备、运营和风险成本。"
    table = Table([[Paragraph(_escape(str(cell)), styles["small"]) for cell in row] for row in data], colWidths=col_widths)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, 1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.6, GRID),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, GRID),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return [Paragraph("利润测算", styles["h2"]), table, Spacer(1, 2 * mm), Paragraph(_escape(breakdown), styles["small"]), Spacer(1, 4 * mm)]


def _pricing_evidence(report: dict[str, Any], metrics: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    summary = _dict(report.get("ai_summary"))
    data_items = [_dict(item) for item in summary.get("data_analysis") or []]
    rows = [["证据", "结果", "业务含义"]]
    for item in data_items[:6]:
        rows.append([_text(item.get("label")), _text(item.get("value")), _text(item.get("explanation"))])
    if len(rows) == 1:
        rows.extend([
            ["定价模型参考", _wan(report.get("baseline_price_yuan")), "连接车型历史价格与本车条件"],
            ["可比车证据", f"{int(_number(report.get('candidate_count')))}条", "判断市场价格分布与置信度"],
        ])
    table = Table([[Paragraph(_escape(cell), styles["small"]) for cell in row] for row in rows], colWidths=[48 * mm, 42 * mm, 90 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, -1), PALE),
        ("BOX", (0, 0), (-1, -1), 0.6, GRID),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    why = [str(item) for item in report.get("internal_basis") or [] if item]
    output: list[Any] = [Paragraph("数据分析与定价依据", styles["h2"]), table]
    if why:
        output.extend([Spacer(1, 2 * mm), Paragraph("<br/>".join(f"· {_escape(item)}" for item in why[:5]), styles["body"])])
    output.append(Spacer(1, 4 * mm))
    return output


def _action_guide(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    actions = [str(item) for item in report.get("action_guide") or [] if item]
    risks = [str(item) for item in report.get("main_risks") or [] if item]
    blocks: list[Any] = [Paragraph("一线执行建议", styles["h2"])]
    if actions:
        blocks.append(_callout("怎么做", "；".join(actions[:4]), styles, "#EFF6FF"))
    if risks:
        blocks.extend([Spacer(1, 2 * mm), _callout("风险边界", "；".join(risks[:4]), styles, "#FFF7ED")])
    return blocks


def _callout(title: str, text: str, styles: dict[str, ParagraphStyle], background: str) -> Table:
    table = Table([[Paragraph(f"<b>{_escape(title)}</b><br/>{_escape(text or '-')}", styles["body"])]], colWidths=[180 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(background)),
        ("BOX", (0, 0), (-1, -1), 0.5, GRID),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _page_footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setFont(CN_FONT_NAME, 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(15 * mm, 8 * mm, "AI懂车价 · 定价结果仅用于当前车辆与当前七要素")
    canvas.drawRightString(195 * mm, 8 * mm, f"第 {document.page} 页")
    canvas.restoreState()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _condition_display(slots: dict[str, Any]) -> str:
    raw = _text(slots.get("condition_group") or slots.get("inspection_grade") or slots.get("condition"))
    verified = bool(
        slots.get("inspection_verified")
        or slots.get("has_real_inspection")
        or _text(slots.get("inspection_status")).lower() in {"verified", "completed", "已检测", "已验车"}
    )
    if verified:
        return raw or "已完成实车检测"
    if slots.get("condition_is_default") or "系统默认良好" in raw:
        return "良好（默认估算，未实车检测）"
    if raw:
        return f"{raw}（按输入估算，未实车检测）"
    return "良好（默认估算，未实车检测）"


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _wan(value: Any) -> str:
    amount = _number(value)
    if not amount:
        return "-"
    return f"{amount / 10000:.2f}".rstrip("0").rstrip(".") + "万"


def _signed_wan(value: Any) -> str:
    amount = _number(value)
    if not amount:
        return "0万"
    sign = "+" if amount > 0 else "-"
    return sign + _wan(abs(amount))


def _range(low: Any, high: Any) -> str:
    lo, hi = _number(low), _number(high)
    if lo and hi:
        return f"{_wan(lo)} - {_wan(hi)}"
    if lo:
        return f"{_wan(lo)}以上"
    if hi:
        return f"{_wan(hi)}以内"
    return "-"


def _escape(value: Any) -> str:
    return html.escape(_text(value), quote=True)


def _clean_filename(value: Any) -> str:
    text = _text(value) or "当前车辆"
    return "".join("_" if char in '\\/:*?\"<>|' else char for char in text)[:60]
