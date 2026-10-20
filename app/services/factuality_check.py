"""标出草稿中新出现的数字和常见技术名词，供用户人工核对。"""

import re


_TECH_TERMS = (
    "FastAPI", "Django", "Flask", "SQLAlchemy", "SQLite", "PostgreSQL", "MySQL",
    "MongoDB", "Redis", "Pydantic", "Alembic", "Vue", "Vue 3", "TypeScript",
    "JavaScript", "React", "Node.js", "Python", "Java", "C++", "C#", ".NET",
    "RAG", "Agent", "API", "REST", "GraphQL", "HTTP", "HTTPS", "JSON", "XML",
    "HTML", "CSS", "Git", "GitHub", "pytest", "OpenAI", "DeepSeek", "OCR",
    "LLM", "Docker", "Kubernetes", "AWS", "Azure", "GCP", "NumPy", "Pandas",
)
_CLAIM_BOUNDARY = re.compile(r"(?<=[。！？!?；;])\s*|\n+")


def _number_claims(text: str) -> set[str]:
    return {number.replace(",", "") for number in re.findall(r"\d+(?:[,.]\d+)*", text)}


def _tech_claims(text: str) -> set[str]:
    return {
        term.casefold()
        for term in _TECH_TERMS
        if re.search(rf"(?<![\w]){re.escape(term)}(?![\w])", text, re.IGNORECASE)
    }


def check_resume_facts(original: str, revised: str, knowledge_items: list[dict]) -> dict:
    """报告未在原简历或相关知识条目中出现的数字、技术名词所在句子。

    This is a narrow deterministic check, not proof that every other claim is true.
    """
    evidence_text = "\n".join(
        [original, *(str(item.get("content", "")) for item in knowledge_items)]
    )
    known_numbers = _number_claims(evidence_text)
    known_terms = _tech_claims(evidence_text)
    flagged = []

    for line in revised.splitlines():
        for sentence in _CLAIM_BOUNDARY.split(line):
            sentence = re.sub(r"^\s*(?:[-*•]\s+|\d+[.、)]\s+|#{1,6}\s*)", "", sentence).strip()
            if not sentence:
                continue
            unsupported = sorted(_number_claims(sentence) - known_numbers)
            unsupported += sorted(_tech_claims(sentence) - known_terms)
            if unsupported:
                flagged.append({"text": sentence, "claims": unsupported})

    return {
        "status": "需人工核对" if flagged else "未发现可识别的新增数字或技术名词",
        "items": flagged[:30],
        "scope": "仅检查数字和常见技术名词；其他事实仍需结合原始资料人工核对。",
    }
