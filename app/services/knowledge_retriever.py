"""本地知识检索：按关键词重叠选择结构化资料和简历片段。"""

import re
from collections import Counter


_STOP_WORDS = {
    "负责", "参与", "具有", "能够", "熟悉", "掌握", "以及", "进行", "相关", "以上", "以下",
    "经验", "工作", "岗位", "要求", "能力", "优先", "提供", "团队", "我们", "你们", "以及",
}


def _terms(text: str) -> set[str]:
    normalized = text.lower()
    terms = set(re.findall(r"[a-z][a-z0-9+#.]{1,30}", normalized))
    for run in re.findall(r"[\u3400-\u9fff]+", normalized):
        for size in (2, 3, 4):
            terms.update(run[index : index + size] for index in range(max(0, len(run) - size + 1)))
    return terms - _STOP_WORDS


def retrieve_knowledge(
    knowledge_items: list[dict],
    query: str,
    limit: int = 8,
) -> list[dict]:
    """按 JD/岗位/用户要求选出相关条目；无匹配时不假装检索成功。"""
    query_terms = _terms(query)
    if not query_terms:
        return knowledge_items[:limit]

    ranked: list[tuple[int, int, dict]] = []
    for position, item in enumerate(knowledge_items):
        title_terms = _terms(item.get("title", ""))
        detail_terms = _terms(
            " ".join(
                str(item.get(field, ""))
                for field in ("category", "organization", "period", "content", "source_note")
            )
        )
        title_score = len(query_terms & title_terms) * 3
        detail_score = len(query_terms & detail_terms)
        score = title_score + detail_score
        if score:
            ranked.append((score, -position, item))

    ranked.sort(reverse=True, key=lambda entry: (entry[0], entry[1]))
    return [item for _, _, item in ranked[:limit]]


def retrieve_resume_chunks(
    resume_text: str,
    query: str,
    limit: int = 8,
    chunk_size: int = 1200,
) -> list[dict]:
    """把简历切成可读片段并检索；结果保留编号和命中词，便于解释来源。"""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", resume_text) if part.strip()]
    chunks: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            chunks.append(paragraph)
            continue
        lines = re.split(r"(?<=[。！？!?；;])\s*|\n+", paragraph)
        current = ""
        for line in lines:
            line = line.strip()
            while len(line) > chunk_size:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.append(line[:chunk_size])
                line = line[chunk_size:]
            if line and len(current) + len(line) + 1 > chunk_size:
                chunks.append(current)
                current = line
            elif line:
                current = f"{current}\n{line}".strip()
        if current:
            chunks.append(current)

    query_terms = _terms(query)
    ranked = []
    for index, content in enumerate(chunks):
        matched_terms = sorted(query_terms & _terms(content))
        if not query_terms or matched_terms:
            ranked.append({
                "chunk_id": index + 1,
                "content": content,
                "matched_terms": matched_terms,
                "score": len(matched_terms),
                "match_type": "keyword" if matched_terms else "general_context",
            })

    if query_terms and not ranked:
        # Keep a small source fallback so a new JD can still receive a cautious draft.
        ranked = [
            {"chunk_id": index + 1, "content": content, "matched_terms": [], "score": 0, "match_type": "fallback"}
            for index, content in enumerate(chunks[: min(3, limit)])
        ]
    ranked.sort(key=lambda item: (-item["score"], item["chunk_id"]))
    return ranked[:limit]
