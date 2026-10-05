from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
)

OUTPUT = "output/pdf/Federico_Vargas_CV_Applied_AI_Architect_Anthropic.pdf"


def section(text):
    return Paragraph(text.upper(), STYLES["Section"])


def para(text, style="Body"):
    return Paragraph(text, STYLES[style])


def bullet(text):
    return Paragraph(text, STYLES["Bullet"])


def role(title, dates):
    return Paragraph(f"<b>{title}</b> <font color='#555555'>{dates}</font>", STYLES["Role"])


def org(text):
    return Paragraph(f"<b>{text}</b>", STYLES["Org"])


def page_num(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#777777"))
    canvas.drawRightString(7.35 * inch, 0.35 * inch, f"Page {doc.page}")
    canvas.restoreState()


styles = getSampleStyleSheet()
STYLES = {
    "Name": ParagraphStyle(
        "Name",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=20,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#111111"),
        spaceAfter=2,
    ),
    "Tagline": ParagraphStyle(
        "Tagline",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.6,
        leading=10.5,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#333333"),
        spaceAfter=2,
    ),
    "Contact": ParagraphStyle(
        "Contact",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.3,
        leading=8.7,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#333333"),
        spaceAfter=6,
    ),
    "Section": ParagraphStyle(
        "Section",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.6,
        leading=10.2,
        textColor=colors.HexColor("#1F4E79"),
        borderWidth=0,
        borderPadding=0,
        spaceBefore=5,
        spaceAfter=3,
    ),
    "Body": ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.0,
        leading=9.9,
        textColor=colors.HexColor("#222222"),
        alignment=TA_LEFT,
        spaceAfter=3,
    ),
    "Bullet": ParagraphStyle(
        "Bullet",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.75,
        leading=9.3,
        textColor=colors.HexColor("#222222"),
        leftIndent=11,
        firstLineIndent=-9,
        bulletIndent=0,
        spaceAfter=2.2,
    ),
    "Org": ParagraphStyle(
        "Org",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.4,
        leading=10,
        textColor=colors.HexColor("#111111"),
        spaceBefore=3,
        spaceAfter=1,
    ),
    "Role": ParagraphStyle(
        "Role",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.05,
        leading=9.6,
        textColor=colors.HexColor("#111111"),
        spaceBefore=2,
        spaceAfter=1,
    ),
}


story = []

story.append(para("FEDERICO JOSE VARGAS CABEZAS", "Name"))
story.append(
    para(
        "Applied AI Architect | GenAI Solutions Advisor | Enterprise AI Adoption & Evaluation",
        "Tagline",
    )
)
story.append(
    para(
        "+506 8327-1982 | vargasfederico04031993@gmail.com | San Jose, Costa Rica | "
        "linkedin.com/in/federico-v-728b54113 | github.com/fedevargas93",
        "Contact",
    )
)

story.append(section("Professional Summary"))
story.append(
    para(
        "Applied AI and analytics professional with 7+ years across enterprise data, GenAI advisory, "
        "technical program delivery, and stakeholder-facing solution work, supported by an MSc in Big Data "
        "Science from the University of Navarra. Recent GenAI Knowledge Advisor experience includes evaluating "
        "LLM/ML solution architectures, translating AI research into deployable business applications, and guiding "
        "AI adoption from opportunity discovery through implementation and impact measurement for a global "
        "telecommunications client. Strong fit for customer-facing AI architecture roles requiring technical "
        "discovery, executive communication, Python/SQL fluency, cloud awareness, evaluation thinking, and a "
        "practical commitment to safe, reliable, and interpretable AI systems."
    )
)

story.append(section("Applied AI Architect Strengths"))
for item in [
    "Enterprise AI advisory: translate ambiguous business requirements into scalable, measurable AI-enabled solutions.",
    "LLM and agentic AI architecture: design modular systems combining language models, symbolic reasoning, knowledge graphs, and auditable workflows.",
    "Evaluation mindset: define adoption roadmaps, success metrics, impact measurement, and technical trade-offs for GenAI initiatives.",
    "Customer-facing communication: bridge executives, business owners, engineering teams, analysts, and delivery stakeholders.",
    "Cloud and data foundation: AWS Certified Cloud Practitioner; hands-on Python, SQL, analytics, large-scale querying, and BI delivery.",
    "Teaching and enablement: present emerging AI concepts, architecture decisions, and business value in accessible language.",
]:
    story.append(bullet(f"- {item}"))

story.append(section("Selected AI & Architecture Work"))
story.append(
    role("Neurosymbolic Agentic AI System - Personal Research / Published", "2025-Present")
)
for item in [
    "Designing a modular agentic AI architecture that combines symbolic reasoning, knowledge graphs, structured inference, and LLM-driven language generation.",
    "Scoped LLM use to generation and cross-validation while preserving interpretable, auditable reasoning paths for safety-critical decision workflows.",
    "Presented the technical architecture and business case to an AI researcher and senior technology leader, generating interest in further evaluation.",
]:
    story.append(bullet(f"- {item}"))
story.append(role("Quantum Natural Language Processing - Independent Research", "2025-Present"))
story.append(
    bullet(
        "- Investigating quantum approaches to language representation and inference, connecting emerging computational paradigms to applied NLP problems."
    )
)

story.append(section("Professional Experience"))
story.append(org("Accenture - Costa Rica"))
story.append(
    role(
        "Digital Execution Lead / Project Manager - Marketing Operations & Campaign Strategy",
        "Jan 2026-Present",
    )
)
for item in [
    "Serve as analytical and technical bridge between senior client stakeholders and cross-functional delivery teams for a global US telecommunications leader.",
    "Own end-to-end solution delivery from design through production deployment, coordinating development teams and client digital-platform stakeholders.",
    "Use operational data and structured analysis to guide efficiency decisions, prioritization, and KPI-aligned execution for enterprise programs.",
]:
    story.append(bullet(f"- {item}"))

story.append(role("GenAI Knowledge Advisor / Researcher / Project Manager", "Oct 2025-Dec 2025"))
for item in [
    "Served as lead technical advisor to a major telecommunications company, evaluating GenAI/ML solution architectures and practical deployment paths.",
    "Translated academic AI research and emerging LLM capabilities into business use cases, implementation considerations, and stakeholder-ready guidance.",
    "Managed AI adoption across business units from opportunity identification and roadmap definition through implementation and impact measurement.",
    "Partnered with business and technical stakeholders to surface constraints, compare solution trade-offs, and align GenAI initiatives to measurable value.",
]:
    story.append(bullet(f"- {item}"))

story.append(role("Project Manager", "Jun 2025-Oct 2025"))
for item in [
    "Led two concurrent data-driven initiatives for a global enterprise client relationship, keeping delivery aligned with timelines, KPIs, and stakeholder expectations.",
    "Converted analysis and visualization outputs into delivery decisions for client-facing teams.",
]:
    story.append(bullet(f"- {item}"))

story.append(role("Analytics & Modelling Specialist", "Aug 2024-Jun 2025"))
for item in [
    "Served as vendor data visualization specialist for Google via Accenture, delivering dashboards that turned operational data into decision-ready insight.",
    "Queried and modeled large-scale databases with SQL to support ad-hoc analysis, reporting, and business decision-making.",
]:
    story.append(bullet(f"- {item}"))

story.append(PageBreak())

story.append(org("Citi - Heredia, Costa Rica"))
story.append(role("Finance Reporting Analyst 2", "Aug 2021-May 2023"))
story.append(
    bullet(
        "- Produced and analyzed LATAM Treasury Reporting outputs under strict regulatory SLAs, data-quality expectations, and archival controls."
    )
)
story.append(role("AML Compliance KYC Analyst", "Jun 2017-Aug 2021"))
story.append(
    bullet(
        "- Completed high-volume KYC records under Global AML/KYC policy, managing concurrent reviews, escalations, and strict production SLAs."
    )
)

story.append(org("Copal Amba, a Moody's Analytics Company - Heredia, Costa Rica"))
story.append(role("Associate Analyst", "Jun 2016-Nov 2016"))
story.append(
    bullet(
        "- Performed data modeling within Financial Planning & Analysis, supporting client reporting using Oracle Essbase."
    )
)

story.append(section("Education"))
for item in [
    "<b>MSc, Big Data Science</b> - University of Navarra, Madrid, Spain (2023-2024). Coursework in statistical modeling, machine learning, and large-scale data analysis.",
    "<b>Licentiate Degree, Business Administration and Management</b> - Universidad Latina de Costa Rica (2015-2016).",
    "<b>Bachelor of Business Administration</b> - Universidad Latina de Costa Rica (2012-2014).",
]:
    story.append(bullet(f"- {item}"))

story.append(section("Certifications & Languages"))
for item in [
    "AWS Certified Cloud Practitioner (CLF-C02); Certified Scrum Master Professional; Certified Product Owner Professional.",
    "Reinvention with Agentic AI (Accenture); Intermediate SQL and Intermediate Python (DataCamp).",
    "Languages: Spanish native; English C1, Duolingo Certified; German B1.",
]:
    story.append(bullet(f"- {item}"))


doc = BaseDocTemplate(
    OUTPUT,
    pagesize=letter,
    leftMargin=0.55 * inch,
    rightMargin=0.55 * inch,
    topMargin=0.45 * inch,
    bottomMargin=0.48 * inch,
)
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
doc.addPageTemplates([PageTemplate(id="CV", frames=[frame], onPage=page_num)])
doc.build(story)
