"""对简历草稿做可解释的质量检查，不调用模型。"""

import re
import math
import unicodedata
from difflib import SequenceMatcher

from app.services.factuality_check import check_resume_facts


_ACTION_WORDS = (
    "负责", "主导", "参与", "协助", "使用", "通过", "设计", "开发", "搭建",
    "实现", "优化", "推动", "完成", "编写", "建立", "维护", "支持", "分析",
    "落地", "改造", "构建", "部署", "排查", "迭代", "制定", "管理", "测试",
)
_RESULT_WORDS = ("提升", "降低", "增长", "达到", "上线", "完成", "结果", "提高", "减少", "节省")


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _has_result(text: str) -> bool:
    return _has_any(text, _RESULT_WORDS) or bool(re.search(r"\d+(?:\.\d+)?\s*[%％万千个天月年次]", text))


def _display_width(text: str) -> float:
    """用字符宽度估算 Word 换行；这是保存前提醒，不替代实际排版渲染。"""
    width = 0.0
    for character in text:
        width += 1.0 if unicodedata.east_asian_width(character) in {"W", "F"} else 0.55
    return width


def estimate_resume_layout(content: str) -> dict:
    """估算 A4 DOCX 是否可能超过一页，避免用户保存后才发现超页。"""
    max_lines = 56
    chars_per_line = 48
    estimated_lines = 0
    for raw_line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        heading = re.match(r"^(#{1,6})\s+", line)
        line_count = max(1, math.ceil(_display_width(line) / chars_per_line))
        estimated_lines += line_count + (1 if heading else 0)
    estimated_pages = max(1, math.ceil(estimated_lines / max_lines))
    over_limit = estimated_lines > max_lines
    return {
        "status": "预计超过一页" if over_limit else "预计一页内",
        "estimated_lines": estimated_lines,
        "max_lines": max_lines,
        "estimated_pages": estimated_pages,
        "message": (
            "内容较多，请删减后再保存。"
            if over_limit
            else "按当前 A4 模板估算可控制在一页内，导出后仍请目视确认。"
        ),
    }


def _experience_groups(content: str) -> list[dict]:
    """按一段工作/项目经历聚合要点，而不是逐条 bullet 套 STAR。

    有工作/项目章节时，章节下的子标题（通常是公司、岗位或项目名）
    会开启一个经历组；没有子标题时，整段章节视为一个经历组。没有
    明确经历章节的旧式纯 bullet 简历则保留逐条检查的兼容行为。
    """
    raw_lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    groups: list[dict] = []
    current: dict | None = None
    experience_depth: int | None = None
    in_experience = False
    saw_experience_section = False
    fallback_bullets: list[str] = []

    def flush() -> None:
        nonlocal current
        if current and current["bullets"]:
            groups.append(current)
        current = None

    def is_experience_heading(text: str) -> bool:
        return bool(re.search(r"(?:工作|项目|实习|职业)\s*经历|实践经验", text))

    for raw in raw_lines:
        original = raw.strip()
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", original)
        if heading:
            depth = len(heading.group(1))
            heading_text = heading.group(2)
            if is_experience_heading(heading_text):
                flush()
                saw_experience_section = True
                in_experience = True
                experience_depth = depth
                continue
            if in_experience and experience_depth is not None:
                if depth <= experience_depth:
                    flush()
                    in_experience = False
                elif depth == experience_depth + 1:
                    flush()
                    current = {"title": heading_text, "bullets": []}
                    continue
                else:
                    continue
            continue

        plain_section = re.match(r"^(工作经历|项目经历|实习经历|职业经历|实践经验)\s*[:：]?$", original)
        if plain_section:
            flush()
            saw_experience_section = True
            in_experience = True
            experience_depth = None
            current = {"title": plain_section.group(1), "bullets": []}
            continue

        is_list_item = bool(re.match(r"^\s*(?:[-*•]\s+|\d+[.、)]\s+)", original))
        line = re.sub(r"^\s*(?:[-*•]\s+|\d+[.、)]\s+)", "", original)
        if not is_list_item or len(line) < 8:
            continue
        if re.search(r"(?:@|https?://|邮箱|电话|手机|微信|地址|现居|出生|性别)", line, re.IGNORECASE):
            continue
        if re.match(r"^(?:技能|技术栈|证书|语言|求职意向)\s*[:：]", line):
            continue

        if saw_experience_section and in_experience:
            if current is None:
                current = {"title": "", "bullets": []}
            current["bullets"].append(line)
        else:
            # 先暂存无标题简历的 bullet。若后面发现正式经历章节，
            # 这些章节外内容（例如技能列表）就不会被误判为经历。
            fallback_bullets.append(line)

    flush()
    if not saw_experience_section:
        # 兼容没有经历章节标题的简历：每条仍可单独提示。
        groups.extend({"title": "", "bullets": [line]} for line in fallback_bullets)
    return groups[:30]


def analyze_resume_quality(
    original: str, revised: str, knowledge_items: list[dict] | None = None
) -> dict:
    """返回 STAR、事实核对提示和修改摘要，结果适合直接展示给用户。"""
    items = []
    groups = _experience_groups(revised)
    for group in groups:
        text = "；".join(group["bullets"])
        checks = {
            "action": _has_any(text, _ACTION_WORDS),
            "result": _has_result(text),
        }
        missing = [label for label, present in checks.items() if not present]
        if missing:
            items.append({
                "title": group["title"],
                "text": text,
                "bullet_count": len(group["bullets"]),
                "missing": missing,
            })
    matcher = SequenceMatcher(a=original.splitlines(), b=revised.splitlines())
    added = sum(j2 - j1 for tag, _, _, j1, j2 in matcher.get_opcodes() if tag in {"insert", "replace"})
    removed = sum(i2 - i1 for tag, i1, i2, _, _ in matcher.get_opcodes() if tag in {"delete", "replace"})
    added_lines = [line for line in revised.splitlines() if line.strip() and line not in original]
    removed_lines = [line for line in original.splitlines() if line.strip() and line not in revised]
    total = len(groups)
    return {
        "star": {
            "total_experiences": total,
            "needs_follow_up": len(items),
            "status": "建议补充" if items else "要点较清晰",
            "experiences": items[:12],
        },
        "diff": {
            "added_lines": added,
            "removed_lines": removed,
            "added_preview": added_lines[:8],
            "removed_preview": removed_lines[:8],
        },
        "factuality": check_resume_facts(original, revised, knowledge_items or []),
        "layout": estimate_resume_layout(revised),
    }
