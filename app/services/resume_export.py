"""将已保存的 Markdown 简历版本导出为常见文件格式。"""

from io import BytesIO
import html
import re

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt
from pypdf import PdfReader
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from reportlab.platypus.doctemplate import LayoutError


class ResumePdfExportError(ValueError):
    """简历无法安全地导出为一页 PDF。"""


_PDF_FONT = "STSong-Light"


def render_resume_pdf(title: str, markdown: str) -> bytes:
    """将审核后的 Markdown 简历导出为仅一页的 PDF。"""
    if _PDF_FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(_PDF_FONT))
        pdfmetrics.registerFontFamily(
            _PDF_FONT,
            normal=_PDF_FONT,
            bold=_PDF_FONT,
            italic=_PDF_FONT,
            boldItalic=_PDF_FONT,
        )

    styles = {
        "title": ParagraphStyle(
            "ResumeTitle", fontName=_PDF_FONT, fontSize=16, leading=19,
            alignment=TA_CENTER, spaceAfter=4,
        ),
        "section": ParagraphStyle(
            "ResumeSection", fontName=_PDF_FONT, fontSize=11, leading=13,
            spaceBefore=4, spaceAfter=1, keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "ResumeBody", fontName=_PDF_FONT, fontSize=8.5, leading=10.3,
            spaceAfter=1,
        ),
    }
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=11 * mm,
        bottomMargin=11 * mm,
        title=title,
    )
    story = []
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    has_heading = any(re.match(r"^\s*#\s+", line) for line in lines)
    if not has_heading:
        story.append(Paragraph(_pdf_inline(title), styles["title"]))

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            style = styles["title"] if len(heading.group(1)) == 1 else styles["section"]
            story.append(Paragraph(_pdf_inline(heading.group(2)), style))
        elif line.startswith(("- ", "* ", "• ")):
            story.append(Paragraph("• " + _pdf_inline(line[2:].strip()), styles["body"]))
        elif re.match(r"^\d+[.、)]\s+", line):
            story.append(Paragraph("• " + _pdf_inline(re.sub(r"^\d+[.、)]\s+", "", line)), styles["body"]))
        else:
            story.append(Paragraph(_pdf_inline(line), styles["body"]))
    if not story:
        story.append(Paragraph(_pdf_inline(title), styles["title"]))

    try:
        document.build(story)
    except LayoutError as error:
        raise ResumePdfExportError("简历内容无法排入一页，请精简内容后再导出。") from error

    pdf = output.getvalue()
    if len(PdfReader(BytesIO(pdf)).pages) != 1:
        raise ResumePdfExportError("简历超过一页，请精简内容后再导出。")
    return pdf


def _pdf_inline(text: str) -> str:
    """Escape plain text and preserve basic Markdown emphasis."""
    parts = re.split(r"(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`)", text)
    rendered = []
    for part in parts:
        if not part:
            continue
        if (part.startswith("**") and part.endswith("**")) or (part.startswith("__") and part.endswith("__")):
            rendered.append(f"<b>{html.escape(part[2:-2])}</b>")
        elif part.startswith("`") and part.endswith("`"):
            rendered.append(html.escape(part[1:-1]))
        else:
            rendered.append(html.escape(part))
    return "".join(rendered)


def render_resume_docx(title: str, markdown: str) -> bytes:
    """将简历 Markdown 的标题和列表转换为可编辑的 Word 文档。"""
    document = Document()
    section = document.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Inches(0.55)
    section.bottom_margin = Inches(0.55)
    section.left_margin = Inches(0.7)
    section.right_margin = Inches(0.7)

    # Word uses separate font settings for Latin and East Asian characters.
    # Setting only font.name can leave Chinese glyphs to an unsupported theme font.
    for style_name in ("Normal", "Heading 1", "Heading 2", "Heading 3", "List Bullet", "List Number"):
        style = document.styles[style_name]
        style.font.name = "Aptos"
        style._element.get_or_add_rPr().get_or_add_rFonts().set(
            qn("w:eastAsia"), "Microsoft YaHei"
        )
        style.paragraph_format.line_spacing = 1.0

    normal = document.styles["Normal"]
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(1)
    for style_name, size, before, after in (
        ("Title", 16, 0, 3),
        ("Heading 1", 13, 5, 2),
        ("Heading 2", 11, 4, 1),
        ("Heading 3", 10.5, 3, 1),
    ):
        style = document.styles[style_name]
        style.font.name = "Aptos"
        style._element.get_or_add_rPr().get_or_add_rFonts().set(
            qn("w:eastAsia"), "Microsoft YaHei"
        )
        style.font.size = Pt(size)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True
    document.core_properties.title = title

    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    first_heading_seen = False
    if not any(re.match(r"^\s*#\s+", line) for line in lines):
        document.add_heading(title, level=0)

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            document.add_heading(heading.group(2).strip(), level=min(len(heading.group(1)), 3))
            first_heading_seen = True
        elif line.startswith(("- ", "* ", "• ")):
            paragraph = document.add_paragraph(style="List Bullet")
            _add_inline_text(paragraph, line[2:].strip())
        elif re.match(r"^\d+[.、)]\s+", line):
            paragraph = document.add_paragraph(style="List Number")
            _add_inline_text(paragraph, re.sub(r"^\d+[.、)]\s+", "", line))
        else:
            paragraph = document.add_paragraph()
            _add_inline_text(paragraph, line)

    if not first_heading_seen and not markdown.strip():
        document.add_heading(title, level=0)

    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _add_inline_text(paragraph, text: str) -> None:
    """保留 Markdown 粗体和行内代码的可读文字及基础样式。"""
    token_pattern = re.compile(r"(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`)")
    for part in token_pattern.split(text):
        if not part:
            continue
        if (part.startswith("**") and part.endswith("**")) or (part.startswith("__") and part.endswith("__")):
            paragraph.add_run(part[2:-2]).bold = True
        elif part.startswith("`") and part.endswith("`"):
            paragraph.add_run(part[1:-1]).font.name = "Consolas"
        else:
            paragraph.add_run(part)
