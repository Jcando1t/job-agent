"""把岗位 JD 拆成可检查的要求，并用本地资料给出逐条证据匹配。"""

import re

from app.services.knowledge_retriever import _terms


_RESPONSIBILITY_HINTS = ("负责", "职责", "工作内容", "承担", "推进", "建设", "维护", "开发")
_HARD_HINTS = ("任职要求", "岗位要求", "必须", "必备", "要求", "熟练", "掌握", "至少", "年以上", "本科", "学历")
_PREFERRED_HINTS = ("优先", "加分", "优先考虑", "有经验者", "更佳")
_HEADINGS = ("岗位职责", "工作职责", "工作内容", "任职要求", "岗位要求", "任职资格", "优先条件", "加分项", "职位描述")


def _clean_line(line: str) -> str:
    return re.sub(r"^[\s•●▪*\-—·\d.、)）(（]+", "", line).strip(" ：:；;\t")


def _sentences(jd_text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in re.split(r"[\r\n]+", jd_text):
        line = _clean_line(raw_line)
        if not line:
            continue
        # 标题保留在分类状态中，不作为一条岗位要求。
        if line.rstrip("：:") in _HEADINGS:
            continue
        parts = re.split(r"(?<=[。；;])\s*", line)
        lines.extend(part.strip(" 。；;\t") for part in parts if part.strip(" 。；;\t"))
    return list(dict.fromkeys(lines))


def analyze_jd(jd_text: str) -> dict:
    """按显式标题和常见词语做透明的本地分类，不声称是语义理解。"""
    result = {"responsibilities": [], "hard_requirements": [], "preferred_qualifications": [], "keywords": []}
    section = ""
    for raw_line in re.split(r"[\r\n]+", jd_text):
        line = _clean_line(raw_line)
        heading = line.rstrip("：:")
        if heading in _HEADINGS:
            if heading in ("岗位职责", "工作职责", "工作内容"):
                section = "responsibilities"
            elif heading in ("优先条件", "加分项"):
                section = "preferred_qualifications"
            else:
                section = "hard_requirements"
            continue
        if not line:
            continue
        sentences = [part.strip(" 。；;\t") for part in re.split(r"(?<=[。；;])\s*", line) if part.strip(" 。；;\t")]
        for sentence in sentences:
            if any(hint in sentence for hint in _PREFERRED_HINTS):
                category = "preferred_qualifications"
            elif section:
                category = section
            elif any(hint in sentence for hint in _RESPONSIBILITY_HINTS):
                category = "responsibilities"
            elif any(hint in sentence for hint in _HARD_HINTS):
                category = "hard_requirements"
            else:
                category = "hard_requirements"
            if sentence not in result[category]:
                result[category].append(sentence)

    all_text = " ".join(_sentences(jd_text))
    # 展示可读的技术词、英文缩写及常见中文领域词，避免把长段中文切片全列出来。
    english = re.findall(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9+#.]{1,30}(?![A-Za-z0-9])", all_text)
    known_chinese = ("人工智能", "机器学习", "深度学习", "自然语言处理", "大模型", "智能体", "知识库", "数据分析", "产品设计", "项目管理", "沟通协作")
    terms = list(dict.fromkeys([*english, *(term for term in known_chinese if term in all_text)]))
    result["keywords"] = terms[:30]
    return result


def match_jd_requirements(
    analysis: dict,
    knowledge_items: list[dict],
    source_content: str = "",
) -> list[dict]:
    """将要求匹配到原始简历和个人资料，作为可核对的关键词提示。"""
    matches: list[dict] = []
    categories = (
        ("responsibilities", "岗位职责"),
        ("hard_requirements", "硬性要求"),
        ("preferred_qualifications", "优先条件"),
    )
    resume_terms = _terms(source_content)
    for key, label in categories:
        for requirement in analysis.get(key, []):
            req_terms = _terms(requirement)
            ranked = []
            resume_overlap = req_terms & resume_terms
            if resume_overlap:
                ranked.append(
                    (
                        len(resume_overlap),
                        {
                            "knowledge_item_id": None,
                            "title": "原始简历",
                            "matched_terms": sorted(resume_overlap),
                        },
                    )
                )
            for item in knowledge_items:
                text = " ".join(str(item.get(field, "")) for field in ("category", "title", "organization", "content", "source_note"))
                overlap = req_terms & _terms(text)
                if overlap:
                    ranked.append((len(overlap), {
                        "knowledge_item_id": item["id"],
                        "title": item.get("title", "个人资料"),
                        "matched_terms": sorted(overlap),
                    }))
            ranked.sort(key=lambda entry: (-entry[0], str(entry[1].get("title", ""))))
            evidence = [item for _, item in ranked[:3]]
            status = "有相关资料，需核对" if evidence else "未找到依据"
            matches.append({"category": label, "requirement": requirement, "status": status, "evidence": evidence})
    return matches
