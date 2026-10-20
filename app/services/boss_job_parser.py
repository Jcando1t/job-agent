"""用少量透明规则整理用户从 BOSS 页面复制的岗位文字。"""

import re


_LABELS = {
    "title": ("岗位名称", "职位名称", "职位"),
    "company": ("公司", "企业", "招聘公司"),
    "city": ("城市", "工作地点", "职位地点"),
}
_NOISE = re.compile(r"^(?:BOSS直聘|职位搜索|职位已收藏|已收藏|立即沟通|立即投递|分享|举报|收藏)$")
_SALARY = re.compile(r"^\d+(?:\.\d+)?(?:\s*[-~～]\s*\d+(?:\.\d+)?)?\s*(?:K|千|元).*$", re.IGNORECASE)
_LOCATION_ONLY = re.compile(r"^[\u4e00-\u9fff]{2,}(?:[·•][\u4e00-\u9fff0-9]{1,12}){1,3}$")
_CARD_TAGS = re.compile(r"^(?:\d+[-~～]\d+年|经验不限|不限经验).*(?:本科|大专|硕士|博士)")
_BRACKET_ONLY = re.compile(r"^[\[\]（）()]+$")
_CONTACT_NAME = re.compile(r"^[\u4e00-\u9fff]{1,4}(?:先生|女士)$")
_JD_HEADINGS = {"岗位职责", "工作职责", "工作内容", "任职要求", "岗位要求", "任职资格", "职位描述", "职位要求"}


def _lines(raw_text: str) -> list[str]:
    return [line.strip(" \t•●▪*-—") for line in re.split(r"[\r\n]+", raw_text) if line.strip()]


def _label_value(line: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        match = re.match(rf"^{re.escape(label)}\s*[:：]\s*(.+)$", line)
        if match:
            return match.group(1).strip()
    return ""


def parse_boss_job_text(raw_text: str) -> dict:
    """提取岗位元信息并尽量剔除非 JD 页面文字，结果仍需用户核对。"""
    lines = _lines(raw_text)
    if not lines:
        return {"title": "", "company": "", "city": "", "description": "", "warnings": ["没有识别到岗位文字"]}

    title = next((_label_value(line, _LABELS["title"]) for line in lines if _label_value(line, _LABELS["title"])), "")
    if not title:
        salary_index = next((index for index, line in enumerate(lines) if _SALARY.match(line)), -1)
        if salary_index > 0:
            title = next(
                (
                    line
                    for line in reversed(lines[:salary_index])
                    if not _NOISE.match(line)
                    and not _LOCATION_ONLY.fullmatch(line)
                    and not _CARD_TAGS.match(line)
                    and not _BRACKET_ONLY.fullmatch(line)
                    and not _CONTACT_NAME.fullmatch(line)
                ),
                "",
            )
    if not title:
        title = next(
            (
                line
                for line in lines
                if not _NOISE.match(line)
                and not _SALARY.match(line)
                and not _LOCATION_ONLY.fullmatch(line)
                and not _BRACKET_ONLY.fullmatch(line)
                and not _CONTACT_NAME.fullmatch(line)
                and not _CARD_TAGS.match(line)
                and not any(_label_value(line, labels) for labels in (_LABELS["company"], _LABELS["city"]))
                and line.rstrip("：:") not in {"岗位职责", "任职要求", "岗位要求", "职位描述", "公司信息"}
            ),
            "",
        )
    company = next((_label_value(line, _LABELS["company"]) for line in lines if _label_value(line, _LABELS["company"])), "")
    city = next((_label_value(line, _LABELS["city"]) for line in lines if _label_value(line, _LABELS["city"])), "")
    if not city:
        location_line = next((line for line in lines if _LOCATION_ONLY.fullmatch(line)), "")
        if location_line:
            city = re.split(r"[·•]", location_line, maxsplit=1)[0]
    if not company:
        title_index = lines.index(title) if title in lines else -1
        if title_index > 0:
            company = next(
                (
                    line for line in reversed(lines[:title_index])
                    if line not in {title, city}
                    and not _NOISE.match(line)
                    and not _SALARY.match(line)
                    and not _CARD_TAGS.match(line)
                    and not _LOCATION_ONLY.fullmatch(line)
                    and not _CONTACT_NAME.fullmatch(line)
                    and not _BRACKET_ONLY.fullmatch(line)
                ),
                "",
            )
        if not company and title_index >= 0:
            location_index = next(
                (index for index, line in enumerate(lines) if _LOCATION_ONLY.fullmatch(line)),
                len(lines),
            )
            if location_index < len(lines):
                company = next(
                    (
                        line for line in reversed(lines[title_index + 1:location_index])
                        if not _NOISE.match(line)
                        and not _SALARY.match(line)
                        and not _CARD_TAGS.match(line)
                        and not _LOCATION_ONLY.fullmatch(line)
                        and not _CONTACT_NAME.fullmatch(line)
                        and not _BRACKET_ONLY.fullmatch(line)
                    ),
                    "",
                )

    metadata = {title, company, city}
    description_lines = [
        line
        for line in lines
        if line not in metadata
        and not _NOISE.match(line)
        and not _SALARY.match(line)
        and not _LOCATION_ONLY.fullmatch(line)
        and not _CARD_TAGS.match(line)
        and not _BRACKET_ONLY.fullmatch(line)
        and not _CONTACT_NAME.fullmatch(line)
        and not any(_label_value(line, labels) for labels in (_LABELS["title"], _LABELS["company"], _LABELS["city"]))
    ]
    has_jd_heading = any(
        line.rstrip("：:") in _JD_HEADINGS
        or re.search(r"(?:岗位职责|工作职责|工作内容|任职要求|岗位要求|任职资格|职位描述|职位要求)\s*[:：]", line)
        for line in description_lines
    )
    warnings = ["公司和城市可能根据卡片文字位置推测，请核对。", "请核对岗位信息和 JD 后再导入。"]
    if not has_jd_heading:
        warnings.append("没有识别到明确的岗位职责或任职要求标题，JD 可能不完整，请补充核对。")
    if not title:
        warnings.append("没有识别到岗位名称，请在导入预览中补充。")
    return {
        "title": title,
        "company": company,
        "city": city,
        "description": "\n".join(description_lines),
        "warnings": warnings,
    }
