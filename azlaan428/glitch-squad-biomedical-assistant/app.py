import sys, os, json, time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context
from agent.agent import (run_pipeline, run_query_architect, run_literature_scout,
                         run_evidence_synthesiser, run_citation_builder, llm_invoke_with_retry, get_llm,
                         get_backend_status)
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
                                 Table, TableStyle, KeepTogether)
from reportlab.lib.enums import TA_LEFT
from xml.sax.saxutils import escape as xml_escape
import io

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/backend-status", methods=["GET"])
def backend_status():
    return jsonify(get_backend_status())

@app.route("/query", methods=["POST"])
def query():
    data = request.get_json()
    user_query = data.get("query", "").strip()
    if not user_query:
        return jsonify({"error": "Empty query"}), 400
    try:
        result = run_pipeline(user_query)
        return jsonify({
            "synthesis": result["synthesis"],
            "citations": result["citations"],
            "paper_count": result["paper_count"],
            "queries": result["queries"]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/stream", methods=["GET"])
def stream():
    user_query = request.args.get("query", "").strip()
    if not user_query:
        return jsonify({"error": "Empty query"}), 400

    def generate():
        def emit(event, data):
            return "event: " + event + "\ndata: " + json.dumps(data) + "\n\n"
        try:
            print("[STREAM] Pipeline started")                       # ADD
            backend = get_backend_status()
            print(f"[STREAM] Backend: {backend['backend']}")          # ADD
            yield emit("backend", backend)
            # Stage 1
            yield emit("stage", {"stage": 1, "pct": 10})
            print("[STREAM] Calling run_query_architect...")         # ADD
            queries = run_query_architect(user_query)
            print(f"[STREAM] Queries returned: {queries}")          # ADD
            yield emit("queries", {"queries": queries, "pct": 25})
            # Stage 2
            yield emit("stage", {"stage": 2, "pct": 35})
            print("[STREAM] Calling run_literature_scout...")        # ADD
            papers = run_literature_scout(queries)
            print(f"[STREAM] Papers retrieved: {len(papers)}")      # ADD
            yield emit("papers", {"paper_count": len(papers), "pct": 50})
            # PRISMA filter
            yield emit("stage", {"stage": 3, "pct": 55})
            print("[STREAM] Calling run_prisma_filter...")           # ADD
            from agent.agent import run_prisma_filter
            filtered = run_prisma_filter(user_query, papers)
            print(f"[STREAM] PRISMA done, included: {len([p for p in filtered.values() if p['included']])}")  # ADD
            included = {pmid: p for pmid, p in filtered.items() if p["included"]}
            yield emit("prisma", {
                "filtered": {
                    pmid: {"title": p.get("title", ""), "included": p["included"], "reason": p["reason"]}
                    for pmid, p in filtered.items()
                },
                "included_count": len(included),
                "excluded_count": len(filtered) - len(included),
                "pct": 65
            })
            print("[STREAM] Sleeping 12s...")                        # ADD
            time.sleep(12)

            # Stage 4 - synthesise on included papers only
            yield emit("stage", {"stage": 4, "pct": 70})
            synthesis = run_evidence_synthesiser(user_query, included)
            yield emit("synthesis", {"synthesis": synthesis, "pct": 88})

            # Stage 5
            yield emit("stage", {"stage": 5, "pct": 90})
            citations = run_citation_builder(included)
            yield emit("done", {
                "synthesis": synthesis,
                "citations": citations,
                "paper_count": len(included),
                "queries": queries,
                "backend": backend,
                "papers": {
                    pmid: {
                        "title": p.get("title", ""),
                        "abstract": p.get("abstract", ""),
                        "authors": p.get("authors", ""),
                        "journal": p.get("journal", ""),
                        "year": p.get("year", "")
                    } for pmid, p in included.items()
                },
                "pct": 100
            })

        except Exception as e:
            yield emit("error", {"message": str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )

@app.route("/suggest-queries", methods=["POST"])
def suggest_queries():
    data = request.get_json()
    original_query = data.get("query", "")
    synthesis = data.get("synthesis", "")
    if not synthesis:
        return jsonify({"error": "No synthesis provided"}), 400
    try:
        llm = get_llm()
        prompt = (
            f"You are a biomedical research strategist. A researcher asked:\n\"{original_query}\"\n\n"
            f"Based on this evidence synthesis, identify 3 high-value follow-up research questions "
            f"that would fill gaps or extend the findings. Return ONLY a JSON array of 3 strings, "
            f"each a specific, searchable research question. No preamble, no markdown, just the JSON array.\n\n"
            f"Synthesis excerpt:\n{synthesis[:1200]}"
        )
        response = llm_invoke_with_retry(llm, prompt)
        raw = response.content.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        suggestions = json.loads(raw.strip())
        if not isinstance(suggestions, list):
            suggestions = []
        return jsonify({"suggestions": suggestions[:3]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

PDF_CONTENT_WIDTH = 170 * mm
PDF_DARK = colors.HexColor("#111827")
AUDIT_FLAG_COLOR = colors.HexColor("#00997a")
AUDIT_EMPTY_STYLE = ParagraphStyle("auditEmpty", fontName="Helvetica-Oblique", fontSize=8.5,
    textColor=colors.HexColor("#5a6a7a"), spaceAfter=6)
AUDIT_GROUP_STYLE = ParagraphStyle("auditGroup", fontName="Helvetica-Bold", fontSize=9,
    textColor=PDF_DARK, spaceBefore=8, spaceAfter=4)
AUDIT_SUBSECTION_STYLE = ParagraphStyle("auditSub", fontName="Helvetica-Bold", fontSize=8.5,
    textColor=AUDIT_FLAG_COLOR, spaceBefore=6, spaceAfter=3)
TABLE_HEADER_STYLE = ParagraphStyle("tblHeader", fontName="Helvetica-Bold", fontSize=8.5,
    textColor=colors.white, leading=11)
TABLE_CELL_STYLE = ParagraphStyle("tblCell", fontName="Helvetica", fontSize=8.5,
    textColor=PDF_DARK, leading=12)
AUDIT_CARD_STYLE = ParagraphStyle("auditCard", fontName="Helvetica", fontSize=8.5,
    leading=12.5, textColor=PDF_DARK)


def pdf_truncate(s, n):
    s = s or ""
    return (s[:n].strip() + "…") if len(s) > n else s


def pdf_humanize(flag):
    if not flag:
        return "Unknown"
    return " ".join(w.capitalize() for w in str(flag).split("_"))


def pdf_data_table(columns, rows, col_widths=None):
    n = max(len(columns), 1)
    if not col_widths:
        w = PDF_CONTENT_WIDTH / n
        col_widths = [w] * n
    data = [[Paragraph(xml_escape(str(c)), TABLE_HEADER_STYLE) for c in columns]]
    for row in rows:
        row = list(row) if isinstance(row, (list, tuple)) else [row]
        if len(row) < n:
            row = row + [""] * (n - len(row))
        elif len(row) > n:
            row = row[:n]
        data.append([Paragraph(xml_escape(str(cell)) if cell not in (None, "") else "—", TABLE_CELL_STYLE)
                     for cell in row])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b3d33")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dbe2e8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fb")]),
    ]))
    return t


def pdf_audit_card(badge_text, header_text, confidence, claim_text, explanation_text, extra_text=None):
    lines = []
    conf = "  ({0}% conf.)".format(confidence) if confidence is not None else ""
    lines.append("<b>[{0}]</b> <b>{1}</b>{2}".format(
        xml_escape(str(badge_text)), xml_escape(header_text or ""), xml_escape(conf)))
    if claim_text:
        lines.append("<i>“{0}”</i>".format(xml_escape(pdf_truncate(claim_text, 220))))
    if explanation_text:
        lines.append(xml_escape(explanation_text))
    if extra_text:
        lines.append(xml_escape(extra_text))
    p = Paragraph("<br/>".join(lines), AUDIT_CARD_STYLE)
    t = Table([[p]], colWidths=[PDF_CONTENT_WIDTH])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#dbe2e8")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7f9fb")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def pdf_ghost_card(r):
    header = pdf_truncate(r.get("paper_title") or "", 60) or ("PMID " + str(r.get("pmid", "")))
    return pdf_audit_card(pdf_humanize(r.get("flag")), header, r.get("confidence"), r.get("claim"), r.get("explanation"))


def pdf_drift_card(r):
    header = pdf_truncate(r.get("title") or "", 60) or ("PMID " + str(r.get("pmid", "")))
    return pdf_audit_card(pdf_humanize(r.get("flag")), header, r.get("confidence"), None, r.get("explanation"))


def pdf_calibration_card(r):
    header = pdf_truncate(r.get("paper_title") or "", 60) or ("PMID " + str(r.get("pmid", "")))
    return pdf_audit_card(pdf_humanize(r.get("flag")), header, r.get("confidence"), r.get("claim"), r.get("explanation"))


def pdf_contradiction_card(r):
    header = "{0} ↔ {1}".format(r.get("paper_a", ""), r.get("paper_b", ""))
    return pdf_audit_card(pdf_humanize(r.get("flag")), header, r.get("confidence"), None, r.get("explanation"))


def pdf_repro_card(r):
    header = pdf_truncate(r.get("title") or "", 60) or ("PMID " + str(r.get("pmid", "")))
    breakdown = r.get("breakdown") or {}
    parts = []
    for k, v in breakdown.items():
        present = bool(v.get("present")) if isinstance(v, dict) else bool(v)
        parts.append(pdf_humanize(k) + ": " + ("present" if present else "missing"))
    extra = "; ".join(parts) if parts else None
    score = r.get("score")
    badge = "{0}/100".format(score) if score is not None else "N/A"
    return pdf_audit_card(badge, header, None, None, r.get("explanation"), extra)


def pdf_render_audit_check(label, result_obj, card_fn):
    result_obj = result_obj or {}
    if result_obj.get("error"):
        return [Paragraph(label, AUDIT_SUBSECTION_STYLE),
                Paragraph("Check failed: " + xml_escape(str(result_obj["error"])), AUDIT_EMPTY_STYLE),
                Spacer(1, 4 * mm)]
    items = result_obj.get("results") or []
    if not items:
        return [Paragraph(label, AUDIT_SUBSECTION_STYLE),
                Paragraph("No data available for this check.", AUDIT_EMPTY_STYLE),
                Spacer(1, 4 * mm)]
    header = Paragraph("{0} ({1})".format(label, len(items)), AUDIT_SUBSECTION_STYLE)
    # Glue the subsection header to its first card so the header never gets
    # orphaned alone at the bottom of a page with all its cards pushed over.
    flows = [KeepTogether([header, card_fn(items[0])]), Spacer(1, 3 * mm)]
    for item in items[1:]:
        flows.append(KeepTogether([card_fn(item)]))
        flows.append(Spacer(1, 3 * mm))
    return flows


@app.route("/export-pdf", methods=["POST"])
def export_pdf():
    data = request.get_json()
    synthesis = data.get("synthesis", "")
    citations = data.get("citations", "")
    query = data.get("query", "Biomedical Research Query")
    paper_count = data.get("paper_count", 0)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm)

    accent = colors.HexColor("#00e5a0")
    dark = colors.HexColor("#111827")

    title_style = ParagraphStyle("title",
        fontName="Helvetica-Bold", fontSize=18,
        textColor=dark, spaceAfter=4)
    meta_style = ParagraphStyle("meta",
        fontName="Helvetica", fontSize=9,
        textColor=colors.HexColor("#5a6a7a"), spaceAfter=16)
    section_label_style = ParagraphStyle("sec_label",
        fontName="Helvetica-Bold", fontSize=10,
        textColor=accent, spaceBefore=14, spaceAfter=4)
    body_style = ParagraphStyle("body",
        fontName="Helvetica", fontSize=10,
        leading=16, textColor=dark, spaceAfter=6)
    cite_style = ParagraphStyle("cite",
        fontName="Helvetica", fontSize=8,
        leading=13, textColor=colors.HexColor("#444444"),
        spaceAfter=4)

    story = []
    story.append(Paragraph("ARIA — Autonomous Research Intelligence Agent", title_style))
    story.append(Paragraph(
        "Query: " + query + "  |  " + str(paper_count) + " papers retrieved  |  Groq LLaMA-3.1",
        meta_style))
    story.append(HRFlowable(width="100%", thickness=1,
        color=colors.HexColor("#1e2936"), spaceAfter=16))

    SECTIONS = [
        ("## Background", "Background"),
        ("## Key Findings", "Key Findings"),
        ("## Level of Evidence", "Level of Evidence"),
        ("## Conflicting Evidence", "Conflicting Evidence"),
        ("## Research Gaps", "Research Gaps"),
        ("## Clinical Implications", "Clinical Implications"),
    ]
    for marker, label in SECTIONS:
        start = synthesis.find(marker)
        if start == -1:
            continue
        content_start = start + len(marker)
        next_markers = [synthesis.find(m) for m, _ in SECTIONS if synthesis.find(m) > start]
        end = min(next_markers) if next_markers else len(synthesis)
        text = synthesis[content_start:end].strip()
        if not text:
            continue
        story.append(Paragraph(label.upper(), section_label_style))
        for para in text.split("\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(para, body_style))

    story.append(Spacer(1, 8*mm))

    comparison_table = data.get("comparison_table")
    if comparison_table and comparison_table.get("rows"):
        table_columns = comparison_table.get("columns") or []
        table_rows = comparison_table.get("rows") or []
        table_title = comparison_table.get("title") or "Evidence Comparison Table"
        story.append(KeepTogether([
            Paragraph("COMPARISON TABLE", section_label_style),
            Paragraph(xml_escape(table_title), body_style),
            pdf_data_table(table_columns, table_rows),
        ]))
        story.append(Spacer(1, 8*mm))

    prisma_excluded = data.get("prisma_excluded") or []
    if prisma_excluded:
        prisma_rows = [[p.get("pmid", ""), p.get("title") or "—", p.get("reason") or "Not specified"]
                       for p in prisma_excluded]
        story.append(KeepTogether([
            Paragraph("PRISMA EXCLUSIONS ({0} EXCLUDED)".format(len(prisma_excluded)), section_label_style),
            pdf_data_table(["PMID", "Title", "Reason Excluded"], prisma_rows,
                            col_widths=[22*mm, 88*mm, 60*mm]),
        ]))
        story.append(Spacer(1, 8*mm))

    audit_results = data.get("audit_results") or {}
    audit_has_data = any((audit_results.get(k) or {}).get("results")
                          for k in ("ghost", "drift", "calibration", "contradiction", "repro"))
    if audit_has_data:
        story.append(Paragraph("INTEGRITY AUDIT", section_label_style))

        story.append(Paragraph("Internal Consistency", AUDIT_GROUP_STYLE))
        story += pdf_render_audit_check("Methodology Drift", audit_results.get("drift"), pdf_drift_card)
        story += pdf_render_audit_check("Confidence Calibration", audit_results.get("calibration"), pdf_calibration_card)

        story.append(Paragraph("External Validity", AUDIT_GROUP_STYLE))
        story += pdf_render_audit_check("Citation Ghost Check", audit_results.get("ghost"), pdf_ghost_card)
        story += pdf_render_audit_check("Cross-Paper Contradiction", audit_results.get("contradiction"), pdf_contradiction_card)
        story += pdf_render_audit_check("Reproducibility Score", audit_results.get("repro"), pdf_repro_card)

        story.append(Spacer(1, 8*mm))

    story.append(HRFlowable(width="100%", thickness=1,
        color=colors.HexColor("#1e2936"), spaceAfter=8))
    story.append(Paragraph("REFERENCES", section_label_style))
    for line in citations.split("\n"):
        line = line.strip()
        if line:
            story.append(Paragraph(line, cite_style))

    story.append(Spacer(1, 6*mm))
    story.append(Paragraph(
        "AI-generated synthesis — verify against primary sources before clinical use.",
        ParagraphStyle("disclaimer", fontName="Helvetica-Oblique",
            fontSize=8, textColor=colors.HexColor("#999999"))))

    doc.build(story)
    buf.seek(0)
    safe_query = "".join(c for c in query[:40] if c.isalnum() or c in " -_").strip()
    filename = "ARIA_" + safe_query.replace(" ", "_") + ".pdf"
    return send_file(buf, mimetype="application/pdf",
        as_attachment=True, download_name=filename)

@app.route("/score", methods=["POST"])
def score():
    data = request.get_json()
    synthesis = data.get("synthesis", "")
    if not synthesis:
        return jsonify({"error": "No synthesis provided"}), 400
    try:
        from agent.agent import run_confidence_scorer
        scores = run_confidence_scorer(synthesis)
        return jsonify({"scores": scores})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/selective-review", methods=["POST"])
def selective_review():
    data = request.get_json()
    question = data.get("question", "")
    selected_papers = data.get("papers", {})
    if not selected_papers:
        return jsonify({"error": "No papers selected"}), 400
    try:
        from agent.agent import run_selective_review
        review = run_selective_review(question, selected_papers)
        return jsonify({"review": review})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()
    question = data.get("question", "")
    synthesis = data.get("synthesis", "")
    if not synthesis:
        return jsonify({"error": "No synthesis provided"}), 400
    try:
        from agent.agent import run_predictive_model
        prediction = run_predictive_model(question, synthesis)
        print(f"[PREDICT] Response: {prediction[:200]}")
        return jsonify({"prediction": prediction})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/citation-ghost-check", methods=["POST"])
def citation_ghost_check():
    data = request.get_json()
    claims = data.get("claims", [])
    if not claims:
        return jsonify({"error": "No claims provided"}), 400
    try:
        from agent.citation_ghost_detector import run_citation_ghost_detector
        results = run_citation_ghost_detector(claims)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/methodology-drift-check", methods=["POST"])
def methodology_drift_check():
    data = request.get_json()
    papers = data.get("papers", [])
    if not papers:
        return jsonify({"error": "No papers provided"}), 400
    try:
        from agent.methodology_drift_tracker import run_methodology_drift_tracker
        results = run_methodology_drift_tracker(papers)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/confidence-calibration-check", methods=["POST"])
def confidence_calibration_check():
    data = request.get_json()
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "No items provided"}), 400
    try:
        from agent.confidence_calibration_check import run_confidence_calibration_check
        results = run_confidence_calibration_check(items)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/cross-paper-contradiction-check", methods=["POST"])
def cross_paper_contradiction_check():
    data = request.get_json()
    pairs = data.get("pairs", [])
    if not pairs:
        return jsonify({"error": "No pairs provided"}), 400
    try:
        from agent.cross_paper_contradiction_finder import run_cross_paper_contradiction_finder
        results = run_cross_paper_contradiction_finder(pairs)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/reproducibility-score", methods=["POST"])
def reproducibility_score():
    data = request.get_json()
    papers = data.get("papers", [])
    if not papers:
        return jsonify({"error": "No papers provided"}), 400
    try:
        from agent.reproducibility_score import run_reproducibility_score
        results = run_reproducibility_score(papers)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

import json as _json
from datetime import datetime
SESSIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions.json")

def load_sessions():
    try:
        return _json.load(open(SESSIONS_FILE))
    except:
        return []

def save_session(entry):
    sessions = load_sessions()
    sessions.insert(0, entry)
    sessions = sessions[:20]
    _json.dump(sessions, open(SESSIONS_FILE, "w"), indent=2)

@app.route("/sessions", methods=["GET"])
def get_sessions():
    return jsonify({"sessions": load_sessions()})

@app.route("/sessions/save", methods=["POST"])
def save_session_route():
    data = request.get_json()
    save_session({
        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
        "timestamp": datetime.now().strftime("%b %d, %H:%M"),
        "query": data.get("query", ""),
        "synthesis": data.get("synthesis", ""),
        "citations": data.get("citations", ""),
        "paper_count": data.get("paper_count", 0),
        "queries": data.get("queries", []),
        "papers": data.get("papers", {})
    })
    return jsonify({"ok": True})

@app.route("/extract-table", methods=["POST"])
def extract_table():
    data = request.get_json()
    question = data.get("question", "")
    synthesis = data.get("synthesis", "")
    papers = data.get("papers", {})
    if not synthesis:
        return jsonify({"error": "No synthesis provided"}), 400
    try:
        from agent.agent import run_table_extractor
        table = run_table_extractor(question, synthesis, papers)
        return jsonify({"table": table})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/followup", methods=["POST"])
def followup():
    data = request.get_json()
    question = data.get("question", "")
    original_question = data.get("original_question", "")
    synthesis = data.get("synthesis", "")
    papers = data.get("papers", {})
    if not question or not synthesis:
        return jsonify({"error": "Missing question or synthesis"}), 400
    try:
        llm = get_llm()
        corpus = "\n\n".join(
            f"[PMID {pmid}] {p.get('title','')}\n{p.get('abstract','')[:300]}"
            for pmid, p in list(papers.items())[:6]
        )
        prompt = (
            f"You are a biomedical research assistant. The user previously asked:\n"
            f"\"{original_question}\"\n\n"
            f"Based on this evidence synthesis and retrieved papers, answer their follow-up question.\n"
            f"Be concise and cite PMIDs where relevant.\n\n"
            f"Synthesis:\n{synthesis[:1500]}\n\n"
            f"Papers:\n{corpus}\n\n"
            f"Follow-up Question: {question}"
        )
        response = llm_invoke_with_retry(llm, prompt)
        return jsonify({"answer": response.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)