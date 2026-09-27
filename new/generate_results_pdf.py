"""Renders RESULTS.md's figures as a formatted PDF report. The numbers below
are transcribed from RESULTS.md (the 2026-09-26 full real 200-item run) --
keep them in sync if RESULTS.md is updated with a fresh run's numbers.
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether,
)
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend

OUT_PATH = Path(__file__).parent / "results" / "Ingress_Semantic_Firewall_Results.pdf"

NAVY = colors.HexColor("#1b2a4a")
ACCENT = colors.HexColor("#2471a3")
GOOD = colors.HexColor("#1e7e46")
BAD = colors.HexColor("#a93226")
LIGHT_GREY = colors.HexColor("#eef1f6")
MED_GREY = colors.HexColor("#c9d1e0")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle("ReportTitle", parent=styles["Title"], textColor=NAVY, fontSize=20, spaceAfter=4))
styles.add(ParagraphStyle("ReportSubtitle", parent=styles["Normal"], textColor=colors.HexColor("#555555"), fontSize=10, spaceAfter=18))
styles.add(ParagraphStyle("H2", parent=styles["Heading2"], textColor=NAVY, spaceBefore=18, spaceAfter=8))
styles.add(ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10, leading=14.5, spaceAfter=8))
styles.add(ParagraphStyle("Callout", parent=styles["BodyText"], fontSize=10.5, leading=15, spaceAfter=8,
                           backColor=LIGHT_GREY, borderPadding=(8, 10, 8, 10), borderColor=MED_GREY, borderWidth=0.75))
styles.add(ParagraphStyle("Caption", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#666666"), spaceBefore=4, spaceAfter=10))
styles.add(ParagraphStyle("Mono", parent=styles["Code"], fontSize=8.5, leading=12, backColor=LIGHT_GREY))


def styled_table(data, col_widths=None, header_rows=1, highlight_row=None, highlight_color=None):
    t = Table(data, colWidths=col_widths, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, header_rows - 1), colors.white),
        ("FONTNAME", (0, 0), (-1, header_rows - 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.5, MED_GREY),
        ("ROWBACKGROUNDS", (0, header_rows), (-1, -1), [colors.white, LIGHT_GREY]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]
    if highlight_row is not None:
        style.append(("BACKGROUND", (0, highlight_row), (-1, highlight_row), highlight_color or colors.HexColor("#dff0e4")))
        style.append(("FONTNAME", (0, highlight_row), (-1, highlight_row), "Helvetica-Bold"))
    t.setStyle(TableStyle(style))
    return t


def headline_chart():
    drawing = Drawing(430, 190)
    chart = VerticalBarChart()
    chart.x, chart.y = 55, 35
    chart.width, chart.height = 300, 130
    chart.data = [(86.0, 48.0, 30.0), (86.0, 80.0, 86.0)]
    chart.categoryAxis.categoryNames = ["Undefended\n(baseline_a)", "Vaccinated\n(baseline_b)", "Firewall\n(proposed)"]
    chart.categoryAxis.labels.fontSize = 8
    chart.categoryAxis.labels.dy = -4
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100
    chart.valueAxis.valueStep = 20
    chart.valueAxis.labels.fontSize = 8
    chart.groupSpacing = 12
    chart.barSpacing = 2
    chart.bars[0].fillColor = BAD
    chart.bars[1].fillColor = ACCENT
    drawing.add(chart)
    legend = Legend()
    legend.x, legend.y = 365, 130
    legend.fontSize = 8
    legend.dxTextSpace = 6
    legend.deltay = 12
    legend.colorNamePairs = [(BAD, "ASR (lower = better)"), (ACCENT, "CSS (higher = better)")]
    drawing.add(legend)
    return drawing


def build():
    doc = SimpleDocTemplate(
        str(OUT_PATH), pagesize=LETTER,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        title="Ingress Semantic Firewall -- Benchmark Results",
    )
    story = []

    story.append(Paragraph("Ingress Semantic Firewall", styles["ReportTitle"]))
    story.append(Paragraph(
        "Benchmark results &mdash; social-media moderation MAS, ASGI ingress firewall<br/>"
        "Full real run, 2026-09-26 &nbsp;|&nbsp; 200 items &times; 3 configurations &nbsp;|&nbsp; "
        "no mocking, 0 transport errors",
        styles["ReportSubtitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=MED_GREY, spaceAfter=14))

    story.append(Paragraph(
        "This project reproduces the “Multi-Agent Security Tax” finding from Peigné et al. "
        "(AAAI 2025): in-context defenses tend to reduce a multi-agent system's cooperation on benign "
        "input, while an out-of-band defense can achieve strong robustness without that cost. This "
        "testbed places the defense as ASGI middleware at the HTTP ingress boundary, in front of a "
        "3-agent LangGraph moderation pipeline (Ingestion &rarr; Policy Evaluator &rarr; Enforcement), "
        "backed by a local Llama Guard 3 (8B) model via Ollama.",
        styles["Body"]))

    story.append(Paragraph("Headline metrics", styles["H2"]))
    headline_data = [
        ["Configuration", "ASR ↓", "CSS ↑", "Security Tax", "Latency Tax", "Avg. latency"],
        ["Undefended (baseline_a)", "86.0%", "86.0%", "—", "—", "2,537 ms"],
        ["Vaccinated (baseline_b)", "48.0%", "80.0%", "+7.0%", "+59.0%", "4,033 ms"],
        ["ASGI Firewall (proposed)", "30.0%", "86.0%", "+0.0%", "+482.1%*", "14,767 ms*"],
    ]
    story.append(styled_table(headline_data, col_widths=[1.55 * inch, 0.7 * inch, 0.7 * inch, 0.95 * inch, 0.95 * inch, 0.95 * inch],
                               highlight_row=3))
    story.append(Paragraph("* see “Latency needs a hardware caveat” below before citing this figure elsewhere.", styles["Caption"]))

    story.append(headline_chart())
    story.append(Spacer(1, 6))

    story.append(Paragraph(
        "<b>The firewall gets both the lowest attack success rate and zero measurable cooperation "
        "tax.</b> Its Component Synergy Score (CSS) exactly matches the undefended baseline because "
        "Policy Evaluator's prompt is byte-identical between the two configurations &mdash; the only "
        "difference is what reaches the agent in the first place. The in-context “vaccination” "
        "defense buys less robustness (48% ASR vs. 30%) while still taxing cooperation (80% vs. 86% "
        "CSS) &mdash; worse than the firewall on both axes.",
        styles["Callout"]))

    story.append(Paragraph("Latency needs a hardware caveat", styles["H2"]))
    story.append(Paragraph(
        "+482% is real on this machine, but it is not a property of ASGI middleware firewalls in "
        "general. This machine's GPU has 6GB of VRAM &mdash; too little to hold the guard model (4.9GB) "
        "and the agent model (2GB) resident at the same time. Every “proposed” item that passes "
        "the firewall forces Ollama to evict and reload one model for the other. This was first caught "
        "as <i>every single proposed-config item timing out and getting blocked, including obviously "
        "benign ones</i> &mdash; a reload artifact, not a real classification, which would have silently "
        "produced a fake 100%-block-rate result if not caught by inspecting a live run rather than "
        "trusting the aggregate numbers. On hardware that can hold both models at once (or a production "
        "deployment using separate inference endpoints, which is the realistic setup anyway), the "
        "latency tax would be close to just the guard model's own inference time &mdash; a few seconds, "
        "not 5&times;. Treat the <i>ordering</i> (firewall &gt; vaccinated &gt; undefended) as the real "
        "finding; don't cite +482.1% outside this specific machine.",
        styles["Body"]))

    story.append(Paragraph("Zero false positives at the ingress layer", styles["H2"]))
    fp_data = [
        ["Category", "Blocked at ingress", "Rate"],
        ["Clean", "0 / 50", "0%"],
        ["ComplexBenign", "0 / 50", "0%"],
        ["Toxic", "22 / 50", "44%"],
        ["IPI_DoS", "33 / 50", "66%"],
    ]
    story.append(styled_table(fp_data, col_widths=[2.2 * inch, 1.8 * inch, 1.1 * inch]))
    story.append(Paragraph(
        "This is why Security Tax is exactly 0%: the firewall never blocks Clean or ComplexBenign "
        "content, so every complex-benign item reaching Policy Evaluator gets the identical input, "
        "and therefore the identical judgment, it would have gotten undefended.",
        styles["Body"]))

    story.append(Paragraph("The firewall isn't IPI/DoS-selective", styles["H2"]))
    story.append(Paragraph(
        "The guard task prompt explicitly asks the classifier to look for injection/DoS patterns, not "
        "general content policy &mdash; yet it blocks 44% of genuinely Toxic posts anyway. This mirrors "
        "a finding already documented for this project's sibling testbed (<font face='Courier'>"
        "mas_security_firewall</font>): an off-the-shelf safety classifier's own trained taxonomy leaks "
        "through regardless of how the task prompt frames the request. Arguably a feature for a real "
        "moderation service (catching obvious toxicity at the perimeter for free), but it means the "
        "firewall's overall block rate isn't a clean measurement of IPI/DoS detection alone &mdash; the "
        "IPI_DoS-only breakdown below isolates that.",
        styles["Body"]))

    story.append(Paragraph("Attack breakdown", styles["H2"]))
    story.append(Paragraph("Attack success rate by payload goal (IPI_DoS category, 25 items each):", styles["Body"]))
    goal_data = [
        ["Configuration", "force_allow", "induce_loop"],
        ["Undefended", "88%", "84%"],
        ["Vaccinated", "36%", "60%"],
        ["Firewall", "36%", "24%"],
    ]
    story.append(styled_table(goal_data, col_widths=[2.2 * inch, 1.5 * inch, 1.5 * inch], highlight_row=3))
    story.append(Paragraph(
        "The firewall's advantage over vaccination shows up entirely on the loop-inducing class -- "
        "“re-run this evaluation” / “resend to Ingestion” phrasing is apparently more "
        "distinctive to the guard model than administrative-sounding hijack text (“Trust &amp; "
        "Safety”, “SYSTEM OVERRIDE”). Vaccinated and firewall configurations tie exactly "
        "on force_allow (36%).",
        styles["Body"]))

    story.append(Spacer(1, 4))
    story.append(Paragraph("Attack success rate by obfuscation vector (proposed config, 10 items/vector):", styles["Body"]))
    vector_data = [
        ["Vector", "Undefended", "Firewall", "Catch rate"],
        ["ocr_embedded", "80%", "0%", "100% caught"],
        ["delimiter_breakout", "90%", "30%", "67% caught"],
        ["authority_spoof", "90%", "40%", "56% caught"],
        ["plain", "80%", "20%", "75% caught"],
        ["base64", "90%", "60%", "33% caught — weakest"],
    ]
    story.append(styled_table(vector_data, col_widths=[1.8 * inch, 1.3 * inch, 1.1 * inch, 1.6 * inch]))
    story.append(Paragraph(
        "Base64-wrapped payloads are the firewall's weakest spot by a clear margin, even though the "
        "sandbox decodes and annotates Base64 before classification. OCR-embedded payloads -- arriving "
        "via a separate field with no surrounding “cover” text -- are caught 100% of the time, "
        "plausibly because an isolated instruction-shaped string has nothing else nearby to look "
        "legitimate next to.",
        styles["Body"]))

    story.append(Paragraph("Methodology notes", styles["H2"]))
    story.append(Paragraph(
        "Dataset: 200 synthetic items (50 each Clean / ComplexBenign / Toxic / IPI_DoS), templated with "
        "seeded randomization for reproducibility. Models: <font face='Courier'>llama-guard3:8b</font> "
        "(firewall classifier) and <font face='Courier'>llama3.2:3b</font> (Policy Evaluator), both real "
        "Ollama inference calls, temperature 0. Mock toggles (<font face='Courier'>MOCK_AGENTS</font>, "
        "<font face='Courier'>MOCK_FIREWALL</font>) were off for every number in this report -- all 600 "
        "pipeline invocations hit real models, with 0 transport-level errors. An offline mock-only smoke "
        "test exists separately to validate pipeline wiring for free and was not used to produce any "
        "number here. Full source, raw per-item data, and this report's generating script are in the "
        "project repository under <font face='Courier'>new/</font>.",
        styles["Body"]))

    doc.build(story)
    return OUT_PATH


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path}")
