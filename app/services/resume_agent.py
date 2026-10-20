"""简历改进工作流：准备事实依据、调用模型、校验结构化结果。"""

import json

from app.services.llm_client import LLMClient, LLMError


SYSTEM_PROMPT = """你是一个严格遵守事实的简历改进助手。
只能使用用户提供的原始简历和个人知识库，不得编造经历、公司、技能、数字或成果。
改写工作或项目经历时，先把同一段经历作为整体梳理：结合上下文明确情境（S）和任务（T），整合多条原始描述中的行动（A）与结果（R）。不要机械地把每条 bullet 单独套成一套 STAR，也不要在简历正文中添加 S/T/A/R 标签。
最终简历要便于招聘者快速浏览：优先展示最有分量且有事实依据的成果，再说明采取了什么行动；项目或岗位名称、角色和技术栈可作为简短背景。写成自然、精炼的简历要点，避免重复背景。最终正文必须按 A4 一页简历控制篇幅，合并重复要点，优先保留与目标岗位最相关的经历；不要为了塞进一页而缩写到难以阅读，也不要删除关键事实。没有可靠数据时，不得补造数字；缺少关键信息时，在 missing_information 中说明需要用户补充或确认。
请把结果返回为 JSON 对象，不要使用 Markdown 代码围栏，字段必须包括：
resume_markdown（改进后的简历正文）、evidence（数组，每项包含 used_for，并引用 knowledge_item_id 或 resume_chunk_id）、
missing_information（数组，记录缺少或需要用户确认的信息）、greeting（可直接修改的打招呼语）。
如果原文或知识库没有证据，必须放入 missing_information，不能猜测补全。
evidence 只能引用本次提供的资料编号：知识库使用 knowledge_item_id，原始简历片段使用 resume_chunk_id；不得引用未提供的编号。
如果提供了岗位 JD，先识别岗位重点和关键词，再选择有事实依据的经历定制简历，并写一段简洁、礼貌的打招呼语；没有 JD 时，打招呼语可以留空。
"""


def build_user_prompt(
    source_content: str,
    knowledge_items: list[dict],
    instruction: str,
    jd_text: str = "",
    job_title: str = "",
    jd_analysis: dict | None = None,
    requirement_matches: list[dict] | None = None,
    resume_chunks: list[dict] | None = None,
) -> str:
    facts = [
        {
            "id": item["id"],
            "category": item["category"],
            "title": item["title"],
            "organization": item["organization"],
            "period": item["period"],
            "content": item["content"],
        }
        for item in knowledge_items
    ]
    retrieved_resume = resume_chunks if resume_chunks is not None else [
        {"chunk_id": 1, "content": source_content, "match_type": "full_source_fallback"}
    ]
    return json.dumps(
        {
            "task": instruction or "先按完整工作/项目经历梳理 STAR，再将内容整理成成果重点靠前、自然精炼、便于快速浏览的简历要点；不编造事实。",
            "job_title": job_title,
            "job_description": jd_text,
            "jd_analysis": jd_analysis or {},
            "personal_evidence_by_requirement": requirement_matches or [],
            "original_resume_retrieval": retrieved_resume,
            "knowledge_base": facts,
        },
        ensure_ascii=False,
        indent=2,
    )


def generate_resume_draft(
    source_content: str,
    knowledge_items: list[dict],
    instruction: str,
    jd_text: str = "",
    job_title: str = "",
    jd_analysis: dict | None = None,
    requirement_matches: list[dict] | None = None,
    resume_chunks: list[dict] | None = None,
    client: LLMClient | None = None,
) -> dict:
    client = client or LLMClient()
    result = client.complete_json(
        SYSTEM_PROMPT,
        build_user_prompt(
            source_content,
            knowledge_items,
            instruction,
            jd_text,
            job_title,
            jd_analysis,
            requirement_matches,
            resume_chunks,
        ),
    )
    content = result.get("resume_markdown")
    if not isinstance(content, str) or not content.strip():
        raise LLMError("模型没有返回可编辑的简历正文。")

    valid_ids = {item["id"] for item in knowledge_items}
    valid_chunk_ids = {item["chunk_id"] for item in (resume_chunks or [])}
    evidence = []
    for entry in result.get("evidence", []):
        if not isinstance(entry, dict):
            continue
        item_id = entry.get("knowledge_item_id")
        chunk_id = entry.get("resume_chunk_id")
        used_for = entry.get("used_for")
        if not isinstance(used_for, str) or not used_for.strip():
            continue
        if isinstance(item_id, int) and item_id in valid_ids:
            evidence.append({"knowledge_item_id": item_id, "used_for": used_for.strip()})
        elif isinstance(chunk_id, int) and chunk_id in valid_chunk_ids:
            evidence.append({"resume_chunk_id": chunk_id, "used_for": used_for.strip()})

    missing = [
        str(item).strip()
        for item in result.get("missing_information", [])
        if str(item).strip()
    ]
    if not evidence and knowledge_items:
        missing.append("模型没有返回有效的个人资料依据，请逐项人工检查。")
    greeting = result.get("greeting", "")
    if not isinstance(greeting, str):
        greeting = ""
    return {
        "result_content": content.strip(),
        "greeting": greeting.strip(),
        "evidence": evidence,
        "missing_info": list(dict.fromkeys(missing)),
        "knowledge_item_ids": [item["knowledge_item_id"] for item in evidence if "knowledge_item_id" in item],
    }
