"""Build the verified Ragas/Ollama/OpenAI explainer PDF.

Run from the project root:
    python docs/build_explainer_pdf.py --output ../output/pdf/RAGAS_Evaluation_Solution.pdf
"""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    LongTable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_X = 17 * mm
TOP_MARGIN = 17 * mm
BOTTOM_MARGIN = 15 * mm
CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN_X)

NAVY = colors.HexColor("#102A43")
BLUE = colors.HexColor("#2F80ED")
TEAL = colors.HexColor("#168D83")
GREEN = colors.HexColor("#2A9D62")
ORANGE = colors.HexColor("#E88933")
RED = colors.HexColor("#C9414A")
INK = colors.HexColor("#243B53")
MUTED = colors.HexColor("#627D98")
LINE = colors.HexColor("#BCCCDC")
PALE_BLUE = colors.HexColor("#EAF3FF")
PALE_GREEN = colors.HexColor("#E9F7F2")
PALE_ORANGE = colors.HexColor("#FFF4E5")
PALE_RED = colors.HexColor("#FDECEE")
PAPER = colors.HexColor("#F7F9FC")
WHITE = colors.white


def build_styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "cover_kicker": ParagraphStyle(
            "cover_kicker",
            parent=sample["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=TEAL,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=32,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceAfter=14,
        ),
        "cover_subtitle": ParagraphStyle(
            "cover_subtitle",
            parent=sample["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=17,
            textColor=INK,
            alignment=TA_CENTER,
            spaceAfter=10,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=sample["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=23,
            textColor=NAVY,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12.2,
            leading=15,
            textColor=BLUE,
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "body",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8.8,
            leading=12.1,
            textColor=INK,
            spaceAfter=5,
        ),
        "small": ParagraphStyle(
            "small",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7.3,
            leading=9.5,
            textColor=MUTED,
            spaceAfter=3,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8.6,
            leading=11.5,
            leftIndent=12,
            firstLineIndent=-7,
            bulletIndent=4,
            textColor=INK,
            spaceAfter=3,
        ),
        "code": ParagraphStyle(
            "code",
            parent=sample["Code"],
            fontName="Courier",
            fontSize=7.1,
            leading=9.3,
            leftIndent=7,
            rightIndent=7,
            borderPadding=6,
            borderColor=LINE,
            borderWidth=0.5,
            borderRadius=3,
            backColor=PAPER,
            textColor=NAVY,
            spaceBefore=3,
            spaceAfter=7,
        ),
        "callout": ParagraphStyle(
            "callout",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9.1,
            leading=12.2,
            leftIndent=8,
            rightIndent=8,
            borderPadding=8,
            borderColor=TEAL,
            borderWidth=0.8,
            borderRadius=4,
            backColor=PALE_GREEN,
            textColor=NAVY,
            spaceBefore=5,
            spaceAfter=7,
        ),
        "ref": ParagraphStyle(
            "ref",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7.1,
            leading=9.4,
            leftIndent=15,
            firstLineIndent=-15,
            textColor=INK,
            spaceAfter=5,
        ),
    }


STYLES = build_styles()


def p(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, STYLES[style])


def bullet(text: str) -> Paragraph:
    return Paragraph(f"- {text}", STYLES["bullet"])


def code(text: str) -> Preformatted:
    return Preformatted(text.strip("\n"), STYLES["code"])


def table(
    rows: list[list[object]],
    widths: list[float],
    *,
    font_size: float = 7.4,
    header: bool = True,
) -> LongTable:
    converted: list[list[object]] = []
    for row_index, row in enumerate(rows):
        converted.append(
            [
                cell
                if isinstance(cell, Flowable)
                else Paragraph(
                    str(cell),
                    ParagraphStyle(
                        f"table_{row_index}",
                        parent=STYLES["small"],
                        fontName=(
                            "Helvetica-Bold"
                            if header and row_index == 0
                            else "Helvetica"
                        ),
                        fontSize=font_size,
                        leading=font_size + 2.2,
                        textColor=WHITE if header and row_index == 0 else INK,
                    ),
                )
                for cell in row
            ]
        )
    result = LongTable(
        converted,
        colWidths=widths,
        repeatRows=1 if header else 0,
        hAlign="LEFT",
    )
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
    ]
    if header:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, PAPER]),
            ]
        )
    else:
        commands.append(("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, PAPER]))
    result.setStyle(TableStyle(commands))
    return result


def flow_diagram(labels: list[str], fills: list[colors.Color] | None = None) -> Drawing:
    height = 68
    width = CONTENT_WIDTH
    drawing = Drawing(width, height)
    count = len(labels)
    gap = 18
    box_width = (width - gap * (count - 1)) / count
    box_height = 39
    y = 16
    palette = fills or [PALE_BLUE, PALE_GREEN, PALE_ORANGE, PALE_BLUE, PALE_GREEN]
    for index, label in enumerate(labels):
        x = index * (box_width + gap)
        drawing.add(
            Rect(
                x,
                y,
                box_width,
                box_height,
                rx=5,
                ry=5,
                fillColor=palette[index % len(palette)],
                strokeColor=BLUE if index % 2 == 0 else TEAL,
                strokeWidth=0.9,
            )
        )
        words = label.split("\n")
        for line_index, line in enumerate(words):
            drawing.add(
                String(
                    x + box_width / 2,
                    y + box_height / 2 + 4 - line_index * 10,
                    line,
                    fontName="Helvetica-Bold",
                    fontSize=7.4,
                    fillColor=NAVY,
                    textAnchor="middle",
                )
            )
        if index < count - 1:
            start_x = x + box_width
            end_x = start_x + gap - 3
            mid_y = y + box_height / 2
            drawing.add(Line(start_x + 2, mid_y, end_x, mid_y, strokeColor=MUTED))
            drawing.add(
                Polygon(
                    [end_x, mid_y, end_x - 5, mid_y + 3, end_x - 5, mid_y - 3],
                    fillColor=MUTED,
                    strokeColor=MUTED,
                )
            )
    return drawing


def two_lane_architecture() -> Drawing:
    drawing = Drawing(CONTENT_WIDTH, 150)
    drawing.add(String(0, 130, "APPLICATION LANE", fontName="Helvetica-Bold", fontSize=8, fillColor=BLUE))
    drawing.add(String(0, 58, "EVALUATION LANE", fontName="Helvetica-Bold", fontSize=8, fillColor=TEAL))

    def box(x: float, y: float, w: float, label: str, fill: colors.Color, stroke: colors.Color) -> None:
        drawing.add(Rect(x, y, w, 34, rx=4, ry=4, fillColor=fill, strokeColor=stroke, strokeWidth=0.8))
        for line_index, line in enumerate(label.split("\n")):
            drawing.add(String(x + w / 2, y + 19 - line_index * 9, line, textAnchor="middle", fontName="Helvetica-Bold", fontSize=6.9, fillColor=NAVY))

    def arrow(x1: float, y1: float, x2: float, y2: float) -> None:
        drawing.add(Line(x1, y1, x2, y2, strokeColor=MUTED, strokeWidth=0.8))
        drawing.add(Polygon([x2, y2, x2 - 5, y2 + 3, x2 - 5, y2 - 3], fillColor=MUTED, strokeColor=MUTED))

    widths = [82, 82, 82, 82, 82]
    xs = [0, 103, 206, 309, 412]
    top = ["Documents", "Chunks +\nembeddings", "Top-k\nretrieval", "Grounded\nanswer", "JSON\ntrace"]
    for i, label in enumerate(top):
        box(xs[i], 89, widths[i], label, PALE_BLUE if i % 2 == 0 else PALE_GREEN, BLUE)
        if i < 4:
            arrow(xs[i] + widths[i] + 3, 106, xs[i + 1] - 3, 106)
    bottom = ["Golden\ncase", "Exact ID +\ncitation", "Ragas\nmetrics", "Aggregate +\ngates", "JSON + CSV\nreport"]
    for i, label in enumerate(bottom):
        box(xs[i], 17, widths[i], label, PALE_GREEN if i % 2 == 0 else PALE_ORANGE, TEAL)
        if i < 4:
            arrow(xs[i] + widths[i] + 3, 34, xs[i + 1] - 3, 34)
    drawing.add(Line(xs[4] + 41, 89, xs[4] + 41, 54, strokeColor=ORANGE, strokeWidth=1.2))
    drawing.add(Polygon([xs[4] + 41, 51, xs[4] + 37, 57, xs[4] + 45, 57], fillColor=ORANGE, strokeColor=ORANGE))
    return drawing


def on_page(canvas, doc) -> None:  # type: ignore[no-untyped-def]
    canvas.saveState()
    if doc.page == 1:
        canvas.setFillColor(NAVY)
        canvas.rect(0, PAGE_HEIGHT - 12 * mm, PAGE_WIDTH, 12 * mm, fill=1, stroke=0)
        canvas.setFillColor(TEAL)
        canvas.rect(0, 0, PAGE_WIDTH, 5 * mm, fill=1, stroke=0)
    else:
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.45)
        canvas.line(MARGIN_X, PAGE_HEIGHT - 11 * mm, PAGE_WIDTH - MARGIN_X, PAGE_HEIGHT - 11 * mm)
        canvas.setFont("Helvetica-Bold", 6.8)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN_X, PAGE_HEIGHT - 8.5 * mm, "RAGAS EVALUATION SOLUTION")
        canvas.setFont("Helvetica", 6.8)
        canvas.drawRightString(PAGE_WIDTH - MARGIN_X, PAGE_HEIGHT - 8.5 * mm, "OLLAMA + OPENAI")
        canvas.line(MARGIN_X, 10 * mm, PAGE_WIDTH - MARGIN_X, 10 * mm)
        canvas.drawString(MARGIN_X, 6.5 * mm, "Verified implementation guide | 03 Aug 2026")
        canvas.drawRightString(PAGE_WIDTH - MARGIN_X, 6.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def section(title: str, subtitle: str | None = None) -> list[Flowable]:
    items: list[Flowable] = [p(title, "h1")]
    if subtitle:
        items.append(p(subtitle, "small"))
    return items


def references_block() -> list[Flowable]:
    refs = [
        ("R1", "Ragas 0.4.3 package", "https://pypi.org/project/ragas/"),
        ("R2", "Ragas v0.3 to v0.4 migration", "https://docs.ragas.io/en/stable/howtos/migrations/migrate_from_v03_to_v04/"),
        ("R3", "Ragas LLM adapters", "https://docs.ragas.io/en/stable/howtos/llm-adapters/"),
        ("R4", "Ragas Faithfulness", "https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/"),
        ("R5", "Ragas Answer Relevancy", "https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/"),
        ("R6", "Ragas Factual Correctness", "https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/factual_correctness/"),
        ("R7", "Ragas Context Precision", "https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/"),
        ("R8", "Ragas Context Recall", "https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/"),
        ("R9", "Ragas 0.4.3 import issue", "https://github.com/vibrantlabsai/ragas/issues/2745"),
        ("R10", "Ollama OpenAI compatibility", "https://docs.ollama.com/api/openai-compatibility"),
        ("R11", "Ollama structured outputs", "https://docs.ollama.com/capabilities/structured-outputs"),
        ("R12", "Ollama embeddings", "https://docs.ollama.com/capabilities/embeddings"),
        ("R13", "OpenAI text generation", "https://developers.openai.com/api/docs/guides/text"),
        ("R14", "OpenAI embeddings", "https://developers.openai.com/api/docs/guides/embeddings"),
        ("R15", "GPT-5.6 Luna model", "https://developers.openai.com/api/docs/models/gpt-5.6-luna"),
        ("R16", "Stanford Introduction to Information Retrieval", "https://nlp.stanford.edu/IR-book/"),
        ("R17", "NIST TREC common evaluation measures", "https://trec.nist.gov/pubs/trec10/appendices/measures.pdf"),
        ("R18", "scikit-learn nDCG definition", "https://scikit-learn.org/stable/modules/generated/sklearn.metrics.ndcg_score.html"),
    ]
    return [
        p(
            f'<b>[{key}]</b> <link href="{url}" color="#2F80ED">{title}</link><br/><font color="#627D98">{url}</font>',
            "ref",
        )
        for key, title, url in refs
    ]


def build_story() -> list[Flowable]:
    story: list[Flowable] = []

    # Cover
    story.extend(
        [
            Spacer(1, 28 * mm),
            p("VERIFIED ONE-STOP IMPLEMENTATION", "cover_kicker"),
            p("Ragas Evaluation Solution", "cover_title"),
            p("Testing a real RAG through Ollama and OpenAI", "cover_subtitle"),
            Spacer(1, 5 * mm),
            flow_diagram(["Documents", "RAG trace", "Exact metrics", "Ragas judge", "Reports"]),
            Spacer(1, 9 * mm),
            p(
                "Complete source integration, pinned installation, dual-provider judging, golden cases, retrieval mathematics, citation and policy checks, semantic Ragas metrics, experiment reports, and release-gate guidance.",
                "callout",
            ),
            Spacer(1, 13 * mm),
            table(
                [
                    ["Target", "Included"],
                    ["RAG providers", "Native Ollama or OpenAI"],
                    ["Ragas judges", "Ollama-compatible endpoint or OpenAI"],
                    ["Metric layers", "Exact IR + deterministic answer checks + semantic Ragas"],
                    ["Artifacts", "JSON traces, per-case JSON/CSV, aggregate summaries"],
                    ["Verified baseline", "Python 3.12.13; 16 tests; clean dependency check"],
                ],
                [42 * mm, 122 * mm],
                font_size=8,
            ),
            Spacer(1, 8 * mm),
            p("Prepared 03 August 2026 | Synthetic payroll-MFA teaching corpus", "cover_kicker"),
        ]
    )
    story.append(PageBreak())

    # Guide map
    story.extend(section("1. What this solution gives you", "Outcome first: what is built, and what it does not pretend to prove."))
    story.append(p("The original application remains the system under test. It retrieves policy sections, generates a cited answer, and saves a canonical trace. The evaluation layer consumes that trace afterward; it never replaces the real RAG with a framework-owned chain."))
    story.append(two_lane_architecture())
    story.append(p("Three evidence layers answer different questions:", "h2"))
    story.append(table(
        [
            ["Layer", "What it establishes", "Main limitation"],
            ["Exact retrieval", "Whether approved chunk IDs were found and ranked well", "Requires human-owned relevance labels"],
            ["Deterministic answer checks", "Citation validity, expected citations, concepts, forbidden claims", "Regex and ID checks do not prove entailment"],
            ["Ragas semantic metrics", "Grounding, relevance, correctness, context quality", "Judge-model output is not deterministic truth"],
        ],
        [35 * mm, 70 * mm, 59 * mm],
    ))
    story.append(p("Keep the layers separate. A fluent answer can hide weak retrieval; a faithful answer can still omit required policy detail; a high Hit Rate can coexist with poor ranking or low recall.", "callout"))
    story.append(p("Guide map", "h2"))
    story.append(table(
        [
            ["Pages", "Topic"],
            ["3-4", "RAG and evaluation architecture"],
            ["5-7", "Installation and provider setup"],
            ["8-10", "Golden data and exact retrieval mathematics"],
            ["11-13", "Answer checks and Ragas metrics"],
            ["14-17", "Reports, diagnosis, testing, and production use"],
            ["18-20", "Commands, source tour, and references"],
        ],
        [28 * mm, 136 * mm],
    ))
    story.append(PageBreak())

    # RAG architecture
    story.extend(section("2. The RAG being evaluated", "The evaluator scores application evidence, not a reconstructed approximation."))
    story.append(flow_diagram(["Markdown\npolicies", "Section\nchunks", "Embedding\nindex", "Cosine\ntop-k", "Cited\nanswer"]))
    story.append(p("Index build", "h2"))
    story.append(table(
        [
            ["Stage", "Actual behavior"],
            ["Chunking", "Every Markdown ## section becomes one stable chunk such as SEC-17::device-re-enrolment."],
            ["Embedding", "Ollama embeddinggemma or OpenAI text-embedding-3-small embeds title, section, and body."],
            ["Storage", "A provider/model-specific JSON index stores chunks and vectors."],
            ["Safety check", "Provider, embedding model, and chunker version must match when an index is loaded."],
        ],
        [34 * mm, 130 * mm],
    ))
    story.append(p("Query path", "h2"))
    story.append(table(
        [
            ["Stage", "Actual behavior"],
            ["Question vector", "The same embedding model maps the question into the document vector space."],
            ["Search", "Normalized NumPy vectors use cosine similarity; scores rank evidence and are not correctness probabilities."],
            ["Grounded prompt", "The top-k sections plus exact chunk IDs are inserted into a strict evidence-only prompt."],
            ["Generation", "Ollama /api/chat or OpenAI Responses API generates the answer."],
            ["Trace", "Question, answer, contexts, IDs, scores, models, top-k, and latency are persisted."],
        ],
        [34 * mm, 130 * mm],
    ))
    story.append(p("The two supplied synthetic documents produce 15 inspectable chunks. At this scale, exact matrix search is easier to audit than adding a vector database."))
    story.append(PageBreak())

    # Eval architecture and contract
    story.extend(section("3. Evaluation architecture and contract", "One canonical trace feeds both exact checks and semantic judges."))
    story.append(flow_diagram(["Golden\ncase", "Real RAG\ntrace", "Exact +\nRagas", "Per-case\nresult", "Aggregate\nreport"]))
    story.append(p("Trace-to-evaluator mapping", "h2"))
    story.append(table(
        [
            ["Trace / golden field", "Used as", "Why it exists"],
            ["question", "Ragas user_input", "Preserves the exact application input"],
            ["answer", "Ragas response", "Scores the answer users actually received"],
            ["retrieved_contexts", "Ragas retrieved_contexts", "Measures support and evidence coverage"],
            ["retrieved_chunk_ids", "Exact ranked list", "Enables reproducible P@k, recall, AP, nDCG, and citations"],
            ["reference", "Approved answer", "Independent truth specification for correctness and recall"],
            ["context_relevance", "ID to grade 0-3", "Binary and graded ranking labels"],
            ["required_context_ids", "Mandatory evidence set", "Separates merely relevant from completeness-critical evidence"],
        ],
        [45 * mm, 43 * mm, 76 * mm],
    ))
    story.append(p("The RAG provider and the judge provider are independent. This supports all four Ollama/OpenAI combinations and lets a stronger external judge evaluate a local generator without changing the application trace.", "callout"))
    story.append(p("Question matching is exact by default for saved traces. This guard prevents scoring one answer against another case's reference. Deliberate paraphrase experiments must opt in."))
    story.append(PageBreak())

    # Install
    story.extend(section("4. Installation that has actually been tested", "Use a fresh environment; do not copy a floating Ragas install from an old tutorial."))
    story.append(p("Supported baseline", "h2"))
    story.append(table(
        [
            ["Item", "Pinned / tested value"],
            ["Python", "3.11 or 3.12; verified on 3.12.13"],
            ["Ragas", "0.4.3"],
            ["OpenAI SDK", "2.52.0"],
            ["NumPy", "2.5.1"],
            ["langchain-community", "0.3.31 compatibility pin"],
            ["httpx SOCKS extra", "0.28.1; protects proxy-enabled environments"],
        ],
        [55 * mm, 109 * mm],
    ))
    story.append(code("""
# Windows PowerShell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-eval.txt
Copy-Item .env.example .env

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-eval.txt
cp .env.example .env
"""))
    story.append(p("Compatibility finding", "h2"))
    story.append(p("An unconstrained Ragas 0.4.3 install can resolve langchain-community 0.4.x and then fail during import because Ragas imports a VertexAI module removed from that branch. The package pins 0.3.31, which was verified in a clean environment. This is tracked upstream [R9]."))
    story.append(code("""
python -m pip check
python eval_app.py preflight --judge-provider ollama
pytest -q
"""))
    story.append(p("Expected verified state: no broken requirements, 16 passing tests, and an initialized adapter. Non-live preflight does not contact a model."))
    story.append(PageBreak())

    # Ollama
    story.extend(section("5. Ollama: local RAG and local Ragas judge", "The application uses Ollama native APIs; Ragas uses Ollama's OpenAI-compatible API."))
    story.append(code("""
ollama pull gemma3:4b
ollama pull embeddinggemma

python eval_app.py preflight --judge-provider ollama --live

python eval_app.py run \\
  --rag-provider ollama \\
  --judge-provider ollama \\
  --top-k 3 \\
  --metric-profile core
"""))
    story.append(p("Endpoint split", "h2"))
    story.append(table(
        [
            ["Responsibility", "Endpoint / client", "Default model"],
            ["RAG embeddings", "POST /api/embed", "embeddinggemma"],
            ["RAG generation", "POST /api/chat", "gemma3:4b"],
            ["Ragas embeddings", "POST /v1/embeddings through OpenAI SDK", "embeddinggemma"],
            ["Ragas structured judge", "POST /v1/chat/completions through Instructor", "gemma3:4b"],
        ],
        [45 * mm, 77 * mm, 42 * mm],
    ))
    story.append(p("Environment settings", "h2"))
    story.append(code("""
RAG_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=gemma3:4b
OLLAMA_EMBEDDING_MODEL=embeddinggemma

RAGAS_JUDGE_PROVIDER=ollama
RAGAS_OLLAMA_BASE_URL=http://localhost:11434
RAGAS_OLLAMA_CHAT_MODEL=gemma3:4b
RAGAS_OLLAMA_EMBEDDING_MODEL=embeddinggemma
"""))
    story.append(p("A small local judge is useful for learning, but it can be less stable at claim decomposition and structured output. Calibrate it against human labels before using it as a release authority. Ollama documents OpenAI compatibility, structured outputs, and embeddings in [R10-R12].", "callout"))
    story.append(PageBreak())

    # OpenAI
    story.extend(section("6. OpenAI and independent judging", "Generation and judging can use the same provider, but they do not have to."))
    story.append(code("""
# .env (never commit the real key)
OPENAI_API_KEY=replace-with-your-key
OPENAI_CHAT_MODEL=gpt-5.6-luna
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
RAGAS_OPENAI_CHAT_MODEL=gpt-5.6-luna
RAGAS_OPENAI_EMBEDDING_MODEL=text-embedding-3-small

python eval_app.py preflight --judge-provider openai --live

python eval_app.py run \\
  --rag-provider openai \\
  --judge-provider openai \\
  --top-k 3
"""))
    story.append(p("Cross-provider experiment", "h2"))
    story.append(code("""
# Local application, independent hosted evaluator
python eval_app.py run \\
  --rag-provider ollama \\
  --judge-provider openai \\
  --case-id MFA-001 \\
  --case-id MFA-006 \\
  --top-k 3
"""))
    story.append(table(
        [
            ["Choice", "Strength", "Risk / cost"],
            ["Ollama judge", "Local, private, repeatable infrastructure", "Judge capability and JSON reliability depend on model/hardware"],
            ["OpenAI judge", "Stronger independent semantic assessment", "API cost, latency, and data-handling requirements"],
            ["Same model family", "Simple comparisons", "Self-evaluation can create correlated blind spots"],
            ["Independent model", "Better diversity of failure signals", "More variables must be recorded and controlled"],
        ],
        [39 * mm, 60 * mm, 65 * mm],
    ))
    story.append(p("The application uses OpenAI's Responses API for answer generation. The Ragas adapter uses structured Chat Completions through Instructor. Official OpenAI generation, embedding, and model references are [R13-R15]."))
    story.append(PageBreak())

    # Golden data
    story.extend(section("7. Golden cases: the evaluation specification", "Metrics are only as trustworthy as the reference answer and relevance labels."))
    story.append(table(
        [
            ["Case", "Scenario", "Primary failure surface"],
            ["MFA-001", "Changed phone", "Recovery completeness"],
            ["MFA-002", "Manager asks for bypass", "Unsafe shortcut rejection"],
            ["MFA-003", "Payroll closes in three hours", "Conditional fallback and P2 triage"],
            ["MFA-004", "Required ticket fields", "Operational detail and minimization"],
            ["MFA-005", "Stolen phone plus unexpected prompt", "Security escalation"],
            ["MFA-006", "Thirty-minute guarantee", "Target versus guarantee"],
            ["MFA-007", "Help Desk phone number", "Insufficient-evidence behavior"],
            ["MFA-008", "Failed test sign-in", "Workflow closure state"],
        ],
        [24 * mm, 64 * mm, 76 * mm],
    ))
    story.append(p("Anatomy of one case", "h2"))
    story.append(code("""
{
  "case_id": "MFA-001",
  "question": "I changed phones ...",
  "reference": "Approved policy-grounded answer ...",
  "required_context_ids": ["SEC-17::standard-recovery-workflow",
                           "SEC-17::device-re-enrolment"],
  "context_relevance": {"chunk-id": 3},
  "expected_citation_ids": ["chunk-id"],
  "required_concepts": [["regex-a", "regex-b"]],
  "forbidden_claim_patterns": ["unsafe-regex"],
  "tags": ["recovery", "completeness"]
}
"""))
    story.append(p("Reference answers and required IDs are human-owned. Never derive them from the same response being scored; doing so lets the system define its own truth.", "callout"))
    story.append(p("Dataset validation confirms unique case IDs, nonempty specifications, allowed grades, and that every referenced chunk ID exists in the current 15-chunk corpus."))
    story.append(PageBreak())

    # Exact math
    story.extend(section("8. Exact retrieval mathematics", "Deterministic, fast, and reproducible over stable chunk IDs."))
    story.append(p("Let y_i = 1 if rank i is relevant, otherwise 0; g_i is its grade; R is the number of judged-relevant chunks; k is the observed retrieval depth."))
    story.append(table(
        [
            ["Metric", "Definition", "Interpretation"],
            ["P@k", "sum(y_i)/k", "How much retrieved material is relevant"],
            ["R@k", "sum(y_i)/R", "How much relevant material was found"],
            ["F1@k", "2PR/(P+R)", "Balance between precision and recall"],
            ["Hit@k", "1 when sum(y_i)>0 else 0", "At least one useful result"],
            ["RR@k", "1 / first relevant rank", "How early the first useful result appears"],
            ["AP@k", "(1/R) sum(P@i * y_i)", "Quality across every relevant rank; missed items remain penalties"],
            ["DCG@k", "sum((2^g_i-1)/log2(i+1))", "Graded utility discounted by rank"],
            ["nDCG@k", "DCG@k / ideal DCG@k", "Observed graded ranking versus ideal"],
        ],
        [26 * mm, 60 * mm, 78 * mm],
    ))
    story.append(p("Mandatory-evidence metrics", "h2"))
    story.append(code("""
RequiredRecall@k = |Retrieved@k intersect Required| / |Required|
AllRequired@k    = 1 only if Required is a subset of Retrieved@k
"""))
    story.append(p("The implementation rejects an empty relevant set, an empty required set, duplicate retrieved IDs, and an empty top-k trace. This removes ambiguous denominator conventions."))
    story.append(p("Across cases: Hit Rate = mean Hit; MRR = mean RR; MAP = mean AP; mean nDCG = mean nDCG. Micro precision pools hits and retrieved counts; micro recall pools hits and relevant counts. IR definitions are grounded in [R16-R18]."))
    story.append(PageBreak())

    # Worked example
    story.extend(section("9. Worked ranking example", "No judge call is needed; every value follows from the approved IDs and rank order."))
    story.append(p("For MFA-001, assume the observed top three are:"))
    story.append(table(
        [
            ["Rank", "Chunk", "Relevant?", "Grade"],
            ["1", "SEC-17::standard-recovery-workflow", "yes", "3"],
            ["2", "SEC-17::purpose-and-scope", "no", "0"],
            ["3", "SEC-17::payroll-deadline-fallback", "no", "0"],
        ],
        [18 * mm, 93 * mm, 28 * mm, 25 * mm],
    ))
    story.append(p("The approved relevant and required set contains two chunks: standard recovery workflow and device re-enrolment. The latter is missing."))
    story.append(code("""
P@3  = 1/3 = 0.333          R@3  = 1/2 = 0.500
F1@3 = 2(1/3)(1/2)/(1/3+1/2) = 0.400
Hit@3 = 1                   RR@3 = 1/1 = 1.000
AP@3 = (P@1 * 1)/R = 1/2 = 0.500

DCG@3  = 7/log2(2) = 7
IDCG@3 = 7/log2(2) + 7/log2(3) = 11.4165
nDCG@3 = 7/11.4165 = approximately 0.613

RequiredRecall@3 = 1/2 = 0.500
AllRequired@3 = 0
"""))
    story.append(p("Why the combination matters", "h2"))
    story.append(bullet("Hit and reciprocal rank look perfect because one useful chunk appears first."))
    story.append(bullet("Precision exposes two non-gold results; recall exposes the missing device-enrolment evidence."))
    story.append(bullet("nDCG penalizes the absent second grade-3 passage even though rank 1 is ideal."))
    story.append(bullet("A generated answer could still sound excellent by paraphrasing the first passage. That is why retrieval and answer scoring remain separate."))
    story.append(PageBreak())

    # citations
    story.extend(section("10. Deterministic answer checks", "Fast controls for source identity, required concepts, and explicitly unsafe statements."))
    story.append(p("Citation set mathematics", "h2"))
    story.append(code("""
C = unique cited IDs        V = retrieved IDs        E = expected citation IDs

CitationValidity  = |C intersect V| / |C|
CitationPrecision = |C intersect E| / |C|
CitationRecall    = |C intersect E| / |E|
CitationF1        = 2PR/(P+R)
"""))
    story.append(table(
        [
            ["Check", "Pass means", "It does not prove"],
            ["Citation validity", "Every cited ID was available to the generator", "The passage entails the claim"],
            ["Citation precision", "Citations belong to the expected source set", "Every expected source was cited"],
            ["Citation recall", "Expected sources appear in the answer", "Claims are faithfully paraphrased"],
            ["Concept coverage", "At least one approved regex alternative matched per concept", "Semantic completeness outside listed concepts"],
            ["Forbidden-claim pass", "No explicitly prohibited pattern matched", "Absence of every possible unsafe implication"],
        ],
        [37 * mm, 64 * mm, 63 * mm],
    ))
    story.append(p("Empty-set behavior is explicit: no citation receives zero validity/precision when the case expects citations; a case that genuinely expects no citations uses a different neutral convention."))
    story.append(p("These controls make excellent CI smoke tests because they are deterministic. Use Ragas or human review for semantic entailment and nuanced completeness.", "callout"))
    story.append(PageBreak())

    # Ragas core
    story.extend(section("11. Core Ragas metrics", "Current v0.4 collections API: each metric is called directly and returns MetricResult."))
    story.append(table(
        [
            ["Metric", "Inputs", "Core interpretation"],
            ["Faithfulness", "question + response + contexts", "Supported response claims / all response claims"],
            ["Answer relevancy", "question + response + judge embeddings", "Mean cosine similarity between original and reverse-generated questions"],
            ["Factual F1", "response + reference", "Claim precision/recall balance against approved answer"],
            ["Context precision", "question + reference + ranked contexts", "Useful contexts should occur early"],
            ["Context recall", "question + reference + contexts", "Reference claims should be supportable from retrieved evidence"],
        ],
        [33 * mm, 60 * mm, 71 * mm],
    ))
    story.append(code("""
from ragas.metrics.collections import Faithfulness

metric = Faithfulness(llm=judge_llm)
result = metric.score(
    user_input=trace.question,
    response=trace.answer,
    retrieved_contexts=list(trace.retrieved_contexts),
)
score = result.value
reason = result.reason
"""))
    story.append(p("This is intentionally not the older evaluate()/SingleTurnSample tutorial pattern. Ragas v0.4 moved metrics to ragas.metrics.collections and direct score()/ascore() calls return MetricResult [R1-R3]."))
    story.append(p("Faithfulness is grounding, not truth. A response can faithfully repeat incomplete evidence. Factual correctness uses the independent reference. Context recall asks whether retrieval supplied enough evidence for that reference [R4-R8].", "callout"))
    story.append(PageBreak())

    # Ragas full and separation
    story.extend(section("12. Full profile and metric independence", "Use the core profile for routine loops; use the full profile for diagnosis."))
    story.append(table(
        [
            ["Added metric", "Purpose", "Why it can disagree with another score"],
            ["Factual precision", "Penalize extra or unsupported response claims versus reference", "A concise answer may score high while missing reference claims"],
            ["Factual recall", "Measure reference-claim coverage", "A verbose answer may cover more while adding mistakes"],
            ["Answer correctness", "Combined semantic and factual agreement", "Uses a different composition than claim-only F1"],
            ["Context relevance", "Question-to-context usefulness without reference", "A context can be relevant yet insufficient for the gold answer"],
            ["Context utilization", "Whether contexts help support the generated response", "The response may use only a subset of necessary policy evidence"],
        ],
        [37 * mm, 60 * mm, 67 * mm],
    ))
    story.append(p("Common non-contradictions", "h2"))
    story.append(bullet("High faithfulness + low factual recall: the answer is grounded but incomplete."))
    story.append(bullet("High Hit Rate + low recall: at least one correct passage appears, but other necessary evidence is absent."))
    story.append(bullet("High Ragas context precision + low exact ID precision: the judge finds early passages useful, while the approved ID set is stricter."))
    story.append(bullet("High answer relevancy + low faithfulness: the response addresses the question but invents support."))
    story.append(p("Every semantic call is isolated. A failed metric records its exception and latency while preserving successful results. The default CLI exit code is 3 when any Ragas call fails; exploratory runs can explicitly allow metric errors."))
    story.append(code("""
python eval_app.py run --rag-provider ollama --judge-provider openai \\
  --metric-profile full --top-k 3
"""))
    story.append(PageBreak())

    # Reporting
    story.extend(section("13. Reports, aggregation, and gates", "Preserve per-case evidence before looking at one aggregate number."))
    story.append(p("Each experiment writes a uniquely named JSON and CSV plus latest.json/latest.csv. The JSON preserves full trace evidence, detailed exact metrics, every semantic result/reason/error/latency, configuration, dependency versions, and gate outcome."))
    story.append(table(
        [
            ["Summary", "Calculation", "Use"],
            ["Macro metric", "Arithmetic mean of per-case scores", "Every case has equal weight"],
            ["Micro P/R", "Pool hits and denominators first", "Every retrieved/relevant item has equal weight"],
            ["Hit Rate", "Mean Hit@k", "Fraction of questions with any relevant retrieval"],
            ["MRR", "Mean reciprocal rank", "First-relevant-result speed"],
            ["MAP", "Mean AP", "Ranking quality across relevant results"],
            ["Ragas error rate", "Failed semantic calls / attempted calls", "Evaluator reliability, not RAG quality"],
        ],
        [36 * mm, 61 * mm, 67 * mm],
    ))
    story.append(p("Gates", "h2"))
    story.append(code("""
{
  "enabled": true,
  "minimum_summary": {
    "summary.aliases.hit_rate_at_k": 0.90
  },
  "minimum_case": {
    "deterministic_metrics.forbidden_claim_pass": 1.0
  },
  "maximum_ragas_error_rate": 0.0
}
"""))
    story.append(p("The shipped example is disabled. Thresholds must be calibrated from human-reviewed baselines; there is no universal 0.8 quality boundary. Safety-critical per-case rules should not be hidden inside an average.", "callout"))
    story.append(PageBreak())

    # Diagnostics
    story.extend(section("14. Reading failures without fooling yourself", "Start from the failing case and trace backward through retrieval, evidence, and claims."))
    story.append(table(
        [
            ["Observed pattern", "Likely failure surface", "First investigation"],
            ["Low P@k, high R@k", "Retrieval adds noise", "Lower k, rerank, add lexical/metadata filters"],
            ["High P@k, low R@k", "Retrieval is too narrow", "Increase k, improve query/chunking, inspect missing required IDs"],
            ["High retrieval, low faithfulness", "Generator ignores or distorts evidence", "Inspect prompt, claims, and cited support"],
            ["High faithfulness, low factual recall", "Evidence or answer is incomplete", "Compare missing reference claims and required chunks"],
            ["Invalid citations", "Generator invented or copied unavailable IDs", "Validate citations after generation; constrain output"],
            ["Forbidden claim fails", "Unsafe policy behavior", "Block release; inspect exact response and regression cause"],
            ["Ragas errors", "Evaluator failure", "Check structured output, model capacity, timeout, and endpoint"],
        ],
        [43 * mm, 57 * mm, 64 * mm],
    ))
    story.append(p("Controlled comparison protocol", "h2"))
    story.append(bullet("Hold corpus, golden cases, judge model, judge prompt/version, and seed-like settings constant."))
    story.append(bullet("Change one variable: top-k, embedding model, chunker, generator, prompt, or reranker."))
    story.append(bullet("Compare per-case deltas and confidence from repeated or human-reviewed runs, not one rounded average."))
    story.append(bullet("Record model names, package versions, timestamps, latency, and semantic-call errors with every result."))
    story.append(p("Do not interpret a cosine retrieval score such as 0.68 as 68 percent confidence or correctness. It is a ranking signal in a model-specific vector space."))
    story.append(PageBreak())

    # Verification
    story.extend(section("15. Verification performed", "What was checked here, and what still requires your configured model endpoints."))
    story.append(table(
        [
            ["Verification", "Result", "Evidence"],
            ["Fresh dependency install", "PASS", "Pinned requirements installed in a new Python 3.12 environment"],
            ["Dependency consistency", "PASS", "pip check reported no broken requirements"],
            ["Original RAG tests", "PASS", "Chunking, cosine retrieval, trace, index, OpenAI and Ollama adapters"],
            ["Evaluation tests", "PASS", "Dataset IDs, formulas, citations, trace contract, factories, reports, gates"],
            ["Combined suite", "16 passed", "No network or paid model calls needed"],
            ["CLI smoke test", "PASS", "list-cases, adapter preflight, and saved-trace deterministic report"],
            ["Live judge call", "USER ENV", "Run --live after Ollama is running or OPENAI_API_KEY is configured"],
            ["Live eight-case scores", "NOT INVENTED", "Must be produced from your actual models and saved traces"],
        ],
        [45 * mm, 31 * mm, 88 * mm],
    ))
    story.append(p("Test suite coverage", "h2"))
    story.append(bullet("15 unique policy chunks and stable metadata."))
    story.append(bullet("Known cosine ranking and index persistence."))
    story.append(bullet("Canonical trace creation and provider request shapes."))
    story.append(bullet("Eight golden cases reference only real corpus IDs."))
    story.append(bullet("P@k, R@k, F1, Hit, RR, AP, nDCG, required-context behavior."))
    story.append(bullet("Citation/policy checks, Ragas factory construction, report summaries, and disabled gates."))
    story.append(p("No live score is printed in this guide because no Ollama server or OpenAI key was assumed. That is a deliberate evidence boundary, not an omission.", "callout"))
    story.append(PageBreak())

    # Production
    story.extend(section("16. From teaching solution to release evaluation", "The code is complete for this project; production governance remains an organizational responsibility."))
    story.append(table(
        [
            ["Area", "Minimum production extension"],
            ["Gold ownership", "Reviewer identity, approval date, policy version, adjudication history"],
            ["Corpus integrity", "Document hashes, stale-index detection, current/retired status filters"],
            ["Security", "Access filtering before retrieval; redaction/encryption and trace retention policy"],
            ["Judge calibration", "Human-labeled benchmark; local versus independent judge agreement"],
            ["Statistics", "Repeated runs or confidence intervals for unstable semantic metrics"],
            ["Cost control", "Case sampling, cache/deduplication, separate fast and diagnostic profiles"],
            ["Release policy", "Per-case safety gates plus calibrated aggregate thresholds"],
            ["Observability", "Model/prompt/corpus versions, latency, token/cost, error categories"],
        ],
        [43 * mm, 121 * mm],
    ))
    story.append(p("Recommended cadence", "h2"))
    story.append(bullet("Every commit: unit tests and deterministic exact metrics."))
    story.append(bullet("Pull request or nightly: core Ragas profile on a stable golden subset."))
    story.append(bullet("Before release: full profile, all safety cases, human review of regressions."))
    story.append(bullet("After policy/model changes: rebuild the index and establish a new reviewed baseline."))
    story.append(p("Ragas scores are measurements made by another model. Treat evaluator reliability, versioning, and calibration as first-class system properties."))
    story.append(PageBreak())

    # Commands
    story.extend(section("17. Command reference", "Copy-paste entry points for the normal workflow."))
    story.append(p("Inspect and run the application", "h2"))
    story.append(code("""
python app.py inspect
python app.py build --provider ollama
python app.py ask "I changed phones and cannot complete MFA. How do I regain payroll access?" \\
  --provider ollama --top-k 3 --show-context
"""))
    story.append(p("Evaluate", "h2"))
    story.append(code("""
python eval_app.py list-cases
python eval_app.py preflight --judge-provider ollama --live

python eval_app.py run --rag-provider ollama --judge-provider ollama \\
  --top-k 3 --metric-profile core

python eval_app.py run --rag-provider ollama --judge-provider openai \\
  --case-id MFA-001 --top-k 3

python eval_app.py trace --trace results/latest.json --case-id MFA-001 \\
  --judge-provider ollama

python eval_app.py run --rag-provider ollama --top-k 3 --skip-ragas
"""))
    story.append(p("Outputs and exit codes", "h2"))
    story.append(table(
        [
            ["Item", "Meaning"],
            ["evaluation/results/*.json", "Complete experiment evidence and aggregate summary"],
            ["evaluation/results/*.csv", "Flat per-case comparison table"],
            ["Exit 0", "Execution succeeded and enabled gates passed"],
            ["Exit 1", "An enabled release gate failed"],
            ["Exit 2", "Configuration, data, provider, or file error"],
            ["Exit 3", "One or more semantic metric calls failed"],
        ],
        [52 * mm, 112 * mm],
    ))
    story.append(PageBreak())

    # Source tour
    story.extend(section("18. Source tour", "Where to change behavior without mixing responsibilities."))
    story.append(table(
        [
            ["File", "Responsibility"],
            ["app.py", "RAG build, inspect, ask, and demo CLI"],
            ["rag/pipeline.py", "Retrieval, prompt, generation, and trace orchestration"],
            ["rag/providers.py", "Native Ollama and OpenAI application adapters"],
            ["eval_app.py", "Evaluation CLI and exit behavior"],
            ["evaluation/data/golden_cases.json", "Human-owned references, relevance, concepts, and safety patterns"],
            ["evaluation/retrieval_metrics.py", "Exact IR mathematics"],
            ["evaluation/deterministic_metrics.py", "Citation and policy checks"],
            ["evaluation/judges.py", "OpenAI/Ollama judge configuration and Ragas factories"],
            ["evaluation/ragas_runner.py", "Core/full collections-based metric calls"],
            ["evaluation/reporting.py", "Macro/micro aggregation, CSV/JSON, optional gates"],
            ["tests/test_evaluation.py", "Offline evaluator regression suite"],
        ],
        [57 * mm, 107 * mm],
    ))
    story.append(p("Design boundaries", "h2"))
    story.append(bullet("Application code does not import Ragas."))
    story.append(bullet("Exact metrics do not call a model."))
    story.append(bullet("Judge settings are independent from application settings."))
    story.append(bullet("Every Ragas metric call can fail without erasing the rest of the experiment."))
    story.append(bullet("Gate thresholds are policy files, not hard-coded universal constants."))
    story.append(Spacer(1, 4 * mm))
    story.append(p("Start with README.md, then inspect golden_cases.json and retrieval_metrics.py. Those three files explain the intended evaluation contract before any model call occurs.", "callout"))
    story.append(PageBreak())

    # References
    story.extend(section("19. Authoritative references", "Official framework/provider documentation plus standard IR sources."))
    story.extend(references_block())
    story.append(Spacer(1, 3 * mm))
    story.append(p("Source boundary", "h2"))
    story.append(p("Project-specific claims in this guide were checked against the supplied source files and tests. Ragas API/version claims use official Ragas documentation and PyPI; provider behavior uses official Ollama and OpenAI documentation; retrieval definitions use Stanford IR, NIST TREC, and scikit-learn. No live quality score was inferred from documentation."))
    story.append(p("End of guide", "cover_kicker"))
    return story


def build_pdf(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    document = BaseDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title="Ragas Evaluation Solution: Ollama and OpenAI",
        author="OpenAI Codex",
        subject="Verified implementation and mathematical explainer for Ragas evaluation",
        creator="ReportLab",
    )
    frame = Frame(
        MARGIN_X,
        BOTTOM_MARGIN,
        CONTENT_WIDTH,
        PAGE_HEIGHT - TOP_MARGIN - BOTTOM_MARGIN,
        id="content",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    document.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])
    document.build(build_story())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    build_pdf(arguments.output.resolve())
    print(arguments.output.resolve())


if __name__ == "__main__":
    main()
