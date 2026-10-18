"""将已保存的 Markdown 简历版本导出为常见文件格式。"""

from io import BytesIO
import re

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt


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

    normal = document.styles["Normal"]
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(3)
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
