"""用 LangGraph 编排简历改进 Agent 的最小垂直流程。

图只负责流程状态和节点之间的路由；具体的 JD 分析、资料检索、模型调用
和质量检查仍由项目自己的服务完成，便于初学者阅读和替换。
"""

from __future__ import annotations

from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from app.services.jd_analyzer import analyze_jd, match_jd_requirements
from app.services.knowledge_retriever import retrieve_knowledge
from app.services.resume_agent import generate_resume_draft
from app.services.resume_quality import analyze_resume_quality


DraftGenerator = Callable[..., dict[str, Any]]
QualityChecker = Callable[[str, str, list[dict]], dict[str, Any]]


class ResumeGraphState(TypedDict, total=False):
    """一次简历改进任务在图中的共享状态。"""

    source_content: str
    all_knowledge_items: list[dict]
    knowledge_items: list[dict]
    resume_chunks: list[dict]
    instruction: str
    jd_text: str
    job_title: str
    company: str
    jd_analysis: dict[str, Any]
    requirement_matches: list[dict]
    result_content: str
    greeting: str
    evidence: list[dict]
    missing_info: list[str]
    knowledge_item_ids: list[int]
    quality_check: dict[str, Any]
    status: str
    status_message: str


def _analyze_jd_node(state: ResumeGraphState) -> dict[str, Any]:
    analysis = state.get("jd_analysis") or analyze_jd(state.get("jd_text", ""))
    matches = state.get("requirement_matches")
    if matches is None:
        matches = match_jd_requirements(
            analysis,
            state.get("all_knowledge_items", []),
            source_content=state.get("source_content", ""),
        )
    return {
        "jd_analysis": analysis,
        "requirement_matches": matches,
        "status": "jd_analyzed",
        "status_message": "JD 已分析，准备检索相关经历。",
    }


def _retrieve_knowledge_node(state: ResumeGraphState) -> dict[str, Any]:
    # API 层已经提前检索过时直接复用，避免一次请求重复排序；单独调用图时则由节点完成检索。
    if "knowledge_items" in state:
        selected = state["knowledge_items"]
    else:
        search_text = " ".join(
            part
            for part in (
                state.get("job_title", ""),
                state.get("company", ""),
                state.get("jd_text", ""),
                state.get("instruction", ""),
            )
            if part
        )
        selected = retrieve_knowledge(
            state.get("all_knowledge_items", []), search_text
        )
    return {
        "knowledge_items": selected,
        "status": "knowledge_retrieved",
        "status_message": (
            f"已找到 {len(selected)} 条相关个人资料和 "
            f"{len(state.get('resume_chunks', []))} 个原始简历片段。"
        ),
    }


def _generate_draft_node(
    draft_generator: DraftGenerator,
) -> Callable[[ResumeGraphState], dict[str, Any]]:
    def generate(state: ResumeGraphState) -> dict[str, Any]:
        draft = draft_generator(
            source_content=state.get("source_content", ""),
            knowledge_items=state.get("knowledge_items", []),
            resume_chunks=state.get("resume_chunks", []),
            instruction=state.get("instruction", ""),
            jd_text=state.get("jd_text", ""),
            job_title=state.get("job_title", ""),
            jd_analysis=state.get("jd_analysis", {}),
            requirement_matches=state.get("requirement_matches", []),
        )
        return {
            "result_content": draft["result_content"],
            "greeting": draft.get("greeting", ""),
            "evidence": draft.get("evidence", []),
            "missing_info": draft.get("missing_info", []),
            "knowledge_item_ids": draft.get("knowledge_item_ids", []),
            "status": "draft_generated",
            "status_message": "草稿已生成，进入质量检查。",
        }

    return generate


def _quality_check_node(
    quality_checker: QualityChecker,
) -> Callable[[ResumeGraphState], dict[str, Any]]:
    def check(state: ResumeGraphState) -> dict[str, Any]:
        quality = quality_checker(
            state.get("source_content", ""),
            state.get("result_content", ""),
            state.get("knowledge_items", []),
        )
        return {
            "quality_check": quality,
            "status": "quality_checked",
            "status_message": "草稿已完成事实、STAR 和一页检查。",
        }

    return check


def _quality_route(state: ResumeGraphState) -> str:
    layout = state.get("quality_check", {}).get("layout", {})
    return "needs_revision" if layout.get("estimated_pages", 1) > 1 else "await_review"


def _needs_revision_node(state: ResumeGraphState) -> dict[str, str]:
    return {
        "status": "needs_revision",
        "status_message": "草稿预计超过一页，请修改后再提交人工审核。",
    }


def _await_review_node(state: ResumeGraphState) -> dict[str, str]:
    return {
        "status": "awaiting_review",
        "status_message": "草稿已准备好，等待用户审核确认。",
    }


def build_resume_graph(
    draft_generator: DraftGenerator = generate_resume_draft,
    quality_checker: QualityChecker = analyze_resume_quality,
):
    """创建一次简历改进图。

    通过参数注入模型和检查器，测试可以使用假实现，API 层也能保留原有依赖。
    """

    graph = StateGraph(ResumeGraphState)
    graph.add_node("analyze_jd", _analyze_jd_node)
    graph.add_node("retrieve_knowledge", _retrieve_knowledge_node)
    graph.add_node("generate_draft", _generate_draft_node(draft_generator))
    graph.add_node("quality_check", _quality_check_node(quality_checker))
    graph.add_node("needs_revision", _needs_revision_node)
    graph.add_node("await_review", _await_review_node)
    graph.add_edge(START, "analyze_jd")
    graph.add_edge("analyze_jd", "retrieve_knowledge")
    graph.add_edge("retrieve_knowledge", "generate_draft")
    graph.add_edge("generate_draft", "quality_check")
    graph.add_conditional_edges(
        "quality_check",
        _quality_route,
        {"needs_revision": "needs_revision", "await_review": "await_review"},
    )
    graph.add_edge("needs_revision", END)
    graph.add_edge("await_review", END)
    return graph.compile()


def run_resume_graph(
    *,
    source_content: str,
    all_knowledge_items: list[dict],
    instruction: str = "",
    jd_text: str = "",
    job_title: str = "",
    company: str = "",
    knowledge_items: list[dict] | None = None,
    resume_chunks: list[dict] | None = None,
    jd_analysis: dict[str, Any] | None = None,
    requirement_matches: list[dict] | None = None,
    draft_generator: DraftGenerator = generate_resume_draft,
    quality_checker: QualityChecker = analyze_resume_quality,
) -> ResumeGraphState:
    """运行图并返回可保存、可展示的最终状态。"""

    initial: ResumeGraphState = {
        "source_content": source_content,
        "all_knowledge_items": all_knowledge_items,
        "instruction": instruction,
        "jd_text": jd_text,
        "job_title": job_title,
        "company": company,
    }
    if knowledge_items is not None:
        initial["knowledge_items"] = knowledge_items
    if resume_chunks is not None:
        initial["resume_chunks"] = resume_chunks
    if jd_analysis is not None:
        initial["jd_analysis"] = jd_analysis
    if requirement_matches is not None:
        initial["requirement_matches"] = requirement_matches
    return build_resume_graph(draft_generator, quality_checker).invoke(initial)
