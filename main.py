from contextlib import asynccontextmanager
import base64
import binascii
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import (
    create_target,
    delete_target,
    create_job,
    create_knowledge_item,
    delete_job,
    delete_knowledge_item,
    delete_resume,
    delete_resume_source,
    delete_resume_image_source,
    get_jobs,
    get_job,
    get_knowledge_items,
    get_resumes,
    get_resume,
    get_resume_sources,
    get_resume_image_source,
    get_resume_image_sources,
    get_targets,
    set_target_active,
    update_job,
    update_knowledge_item,
    update_target,
    create_resume,
    create_resume_source,
    create_resume_image_source,
    create_agent_run,
    get_agent_run,
    get_agent_runs,
    save_approved_agent_run,
    update_agent_run,
)
from app.schemas import (
    ActiveUpdate,
    BossGreetingSendInput,
    BossGreetingPrepareInput,
    BossJobTextInput,
    BossJobUrlInput,
    BossResumeSendInput,
    JobInput,
    KnowledgeInput,
    ResumeInput,
    ResumeSourceInput,
    ResumeFileInput,
    ResumeImageInput,
    ResumeImageOcrInput,
    ResumeRunApproval,
    ResumeRunInput,
    ResumeRunUpdate,
    TargetInput,
)
from app.services.ocr_service import OcrImageError, recognize_resume_image
from app.services.document_parser import DocumentParseError, extract_resume_text
from app.services.resume_agent import generate_resume_draft
from app.services.resume_graph import run_resume_graph
from app.services.knowledge_retriever import retrieve_knowledge, retrieve_resume_chunks
from app.services.jd_analyzer import analyze_jd, match_jd_requirements
from app.services.private_file_migration import migrate_legacy_private_files
from app.services.llm_client import LLMConfigurationError, LLMError
from app.storage import delete_private_file, save_private_file
from app.services.resume_export import ResumePdfExportError, render_resume_docx, render_resume_pdf
from app.services.resume_quality import analyze_resume_quality, estimate_resume_layout
from app.services.boss_job_parser import parse_boss_job_text
from app.services.chrome_automation import (
    ChromeAutomationError,
    check_boss_chat,
    chrome_status,
    connect_chrome,
    open_boss_in_chrome,
    open_boss_job_in_chrome,
    prepare_boss_greeting,
    send_boss_greeting,
    send_boss_resume,
    sync_boss_page,
)


TEMPLATE_DIRECTORY = Path(__file__).resolve().parent / "app" / "templates"
FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"
templates = Jinja2Templates(directory=str(TEMPLATE_DIRECTORY))


@asynccontextmanager
async def lifespan(_: FastAPI):
    command.upgrade(Config(str(Path(__file__).resolve().parent / "alembic.ini")), "head")
    migrate_legacy_private_files()
    yield


app = FastAPI(title="求职 Agent", lifespan=lifespan)
if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if (FRONTEND_DIST / "index.html").is_file():
        return FileResponse(FRONTEND_DIST / "index.html")
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


def _save_private_file_and_record(
    file_content: bytes | str,
    storage_filename: str,
    create_record: Callable[..., dict],
    **record_fields,
) -> dict:
    """Remove a newly saved file if its database record cannot be created."""
    storage_path = save_private_file(file_content, Path(storage_filename).suffix)
    try:
        return create_record(**record_fields, storage_path=storage_path)
    except Exception:
        delete_private_file(storage_path)
        raise


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/targets")
def list_job_targets():
    return get_targets()


@app.post("/api/targets", status_code=status.HTTP_201_CREATED)
def add_job_target(target: TargetInput):
    return create_target(
        title=target.title,
        keywords=target.keywords,
        cities=target.cities,
    )


@app.put("/api/targets/{target_id}")
def edit_job_target(target_id: int, target: TargetInput):
    updated = update_target(
        target_id=target_id,
        title=target.title,
        keywords=target.keywords,
        cities=target.cities,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="求职方向不存在")
    return updated


@app.patch("/api/targets/{target_id}/active")
def change_job_target_status(target_id: int, update: ActiveUpdate):
    updated = set_target_active(target_id=target_id, is_active=update.is_active)
    if updated is None:
        raise HTTPException(status_code=404, detail="求职方向不存在")
    return updated


@app.delete("/api/targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_job_target(target_id: int):
    deleted = delete_target(target_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="求职方向不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/jobs")
def list_jobs():
    return get_jobs()


@app.post("/api/jobs/boss/preview")
def preview_boss_job(payload: BossJobTextInput):
    return parse_boss_job_text(payload.text)


@app.get("/api/jobs/boss/browser")
def boss_browser_status():
    return chrome_status()


@app.post("/api/jobs/boss/browser/connect")
def connect_boss_browser():
    try:
        return connect_chrome()
    except ChromeAutomationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/jobs/boss/browser/open")
def open_boss_browser():
    try:
        return open_boss_in_chrome()
    except ChromeAutomationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/jobs/boss/browser/open-job")
def open_boss_job_browser(payload: BossJobUrlInput):
    try:
        return open_boss_job_in_chrome(payload.url)
    except ChromeAutomationError as error:
        error_status = 422 if "没有有效的 BOSS 直聘详情链接" in str(error) else 503
        raise HTTPException(status_code=error_status, detail=str(error)) from error


def _delivery_materials(job_id: int, resume_id: int) -> tuple[dict, dict]:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="岗位记录不存在")
    resume = get_resume(resume_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="简历版本不存在")
    if not job.get("original_url"):
        raise HTTPException(status_code=409, detail="该岗位没有 BOSS 原始链接，无法自动发送")
    snapshot = resume.get("job_snapshot") or {}
    is_job_resume = snapshot.get("job_id") == job_id
    is_current_target_resume = (
        bool(job.get("target_id"))
        and resume.get("target_id") == job.get("target_id")
        and resume.get("is_current") is True
    )
    if not is_job_resume and not is_current_target_resume:
        raise HTTPException(
            status_code=409,
            detail="只能发送当前岗位的已审核专属简历，或该岗位求职方向当前生效的简历",
        )
    return job, resume


@app.get("/api/jobs/{job_id}/boss/chat-status")
def boss_job_chat_status(job_id: int):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="岗位记录不存在")
    if not job.get("original_url"):
        return {"ready": False, "message": "该岗位没有 BOSS 原始链接，无法检查聊天窗口。"}
    title = job.get("title", "")
    city = job.get("city", "")
    return check_boss_chat(job["original_url"], title, city) if title else check_boss_chat(job["original_url"])


@app.post("/api/jobs/boss/browser/prepare-greeting")
def prepare_boss_greeting_api(payload: BossGreetingPrepareInput):
    job, resume = _delivery_materials(payload.job_id, payload.resume_id)
    try:
        title = job.get("title", "")
        city = job.get("city", "")
        result = prepare_boss_greeting(job["original_url"], payload.greeting, title, city) if title else prepare_boss_greeting(job["original_url"], payload.greeting)
    except ChromeAutomationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        **result,
        "job_id": job["id"],
        "resume_id": resume["id"],
        "message": "已打开对应岗位沟通页并填入打招呼语，尚未发送。",
    }


@app.post("/api/jobs/boss/browser/send-greeting")
def send_boss_greeting_api(payload: BossGreetingSendInput):
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="请先确认岗位、简历和打招呼语后再发送")
    job, resume = _delivery_materials(payload.job_id, payload.resume_id)
    try:
        title = job.get("title", "")
        city = job.get("city", "")
        result = send_boss_greeting(job["original_url"], payload.greeting, title, city) if title else send_boss_greeting(job["original_url"], payload.greeting)
    except ChromeAutomationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        **result,
        "job_id": job["id"],
        "resume_id": resume["id"],
        "message": "打招呼语已发送。",
    }


@app.post("/api/jobs/boss/browser/send-resume")
def send_boss_resume_api(payload: BossResumeSendInput):
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="请先确认岗位和简历版本后再发送")
    job, resume = _delivery_materials(payload.job_id, payload.resume_id)
    try:
        title = job.get("title", "")
        city = job.get("city", "")
        arguments = (
            job["original_url"],
            f"{resume['title'] or 'resume'}.docx",
            render_resume_docx(resume["title"], resume["content"]),
        )
        result = send_boss_resume(*arguments, title, city) if title else send_boss_resume(*arguments)
    except ChromeAutomationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        **result,
        "job_id": job["id"],
        "resume_id": resume["id"],
        "message": "定制简历附件已发送。",
    }


@app.post("/api/jobs/boss/browser/sync")
def sync_boss_browser():
    try:
        return sync_boss_page()
    except ChromeAutomationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/jobs", status_code=status.HTTP_201_CREATED)
def add_job(job: JobInput):
    created = create_job(**job.model_dump())
    if created is None:
        raise HTTPException(status_code=404, detail="关联的求职方向不存在")
    if created.get("duplicate"):
        raise HTTPException(status_code=409, detail="相同原始链接或相同岗位信息已经记录过了")
    return created


@app.put("/api/jobs/{job_id}")
def edit_job(job_id: int, job: JobInput):
    updated = update_job(job_id=job_id, **job.model_dump())
    if updated is None:
        raise HTTPException(status_code=404, detail="岗位或关联的求职方向不存在")
    if updated.get("duplicate"):
        raise HTTPException(status_code=409, detail="相同原始链接或相同岗位信息已经记录过了")
    return updated


@app.delete("/api/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_job(job_id: int):
    deleted = delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/knowledge")
def list_knowledge_items():
    return get_knowledge_items()


@app.post("/api/knowledge", status_code=status.HTTP_201_CREATED)
def add_knowledge_item(item: KnowledgeInput):
    return create_knowledge_item(**item.model_dump())


@app.put("/api/knowledge/{item_id}")
def edit_knowledge_item(item_id: int, item: KnowledgeInput):
    updated = update_knowledge_item(item_id=item_id, **item.model_dump())
    if updated is None:
        raise HTTPException(status_code=404, detail="个人知识条目不存在")
    return updated


@app.delete("/api/knowledge/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_knowledge_item(item_id: int):
    deleted = delete_knowledge_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="个人知识条目不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/resumes")
def list_resumes():
    return get_resumes()


@app.get("/api/resumes/{resume_id}/download")
def download_resume(resume_id: int, format: str = "docx"):
    resume = get_resume(resume_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="简历版本不存在")
    if format not in {"docx", "pdf", "md"}:
        raise HTTPException(status_code=422, detail="仅支持 DOCX、PDF 或 Markdown 导出")
    title = _safe_download_stem(resume["title"], resume_id)
    extension = format
    headers = {
        "Content-Disposition": (
            f'attachment; filename="resume-{resume_id}.{extension}"; '
            f"filename*=UTF-8''{quote(title, safe='')}.{extension}"
        ),
        "X-Content-Type-Options": "nosniff",
    }
    if format == "md":
        return Response(
            content=resume["content"],
            media_type="text/markdown; charset=utf-8",
            headers=headers,
        )
    if format == "pdf":
        try:
            content = render_resume_pdf(title, resume["content"])
        except ResumePdfExportError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return Response(
            content=content,
            media_type="application/pdf",
            headers=headers,
        )
    return Response(
        content=render_resume_docx(title, resume["content"]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


def _safe_download_stem(title: str, resume_id: int) -> str:
    """移除 Windows/浏览器文件名中的保留字符和路径分隔符。"""
    stem = "".join(
        character
        for character in title.strip()
        if character not in '<>:"/\\|?*' and ord(character) >= 32
    ).strip(" .")[:100]
    return stem or f"resume-{resume_id}"


@app.get("/api/resume-sources")
def list_resume_sources():
    return get_resume_sources()


@app.get("/api/resume-images")
def list_resume_image_sources():
    return get_resume_image_sources()


@app.get("/api/resume-images/{image_id}/content")
def read_resume_image(image_id: int):
    image = get_resume_image_source(image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="简历图片不存在")
    return Response(
        content=image["content"],
        media_type=image["content_type"],
        headers={"X-Content-Type-Options": "nosniff"},
    )


@app.post("/api/resume-images/recognize")
def recognize_resume_images(payload: ResumeImageOcrInput):
    results = []
    for image_id in payload.image_ids:
        image = get_resume_image_source(image_id)
        if image is None:
            raise HTTPException(status_code=404, detail=f"简历图片 #{image_id} 不存在")
        try:
            text = recognize_resume_image(image["content"])
        except ImportError as error:
            raise HTTPException(
                status_code=503,
                detail="本地 OCR 组件尚未安装，请按项目说明安装依赖后重启应用。",
            ) from error
        except OcrImageError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        results.append(
            {"id": image_id, "filename": image["filename"], "text": text}
        )
    return {"results": results}


@app.post("/api/resume-images", status_code=status.HTTP_201_CREATED)
def add_resume_image(image: ResumeImageInput):
    try:
        content = base64.b64decode(image.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="图片数据格式无效")
    if not content or len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="图片大小需在 10 MB 以内")
    signatures = {
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
        "image/gif": content.startswith((b"GIF87a", b"GIF89a")),
    }
    if not signatures[image.content_type]:
        raise HTTPException(status_code=415, detail="图片格式与文件内容不匹配")
    filename = Path(image.filename.replace("\\", "/")).name or "resume-image"
    return _save_private_file_and_record(
        content,
        filename,
        create_resume_image_source,
        filename=filename,
        content_type=image.content_type,
        # 图片正文只保存到本地文件；数据库保留兼容旧表的空 BLOB。
        content=b"",
    )


@app.delete("/api/resume-images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_resume_image(image_id: int):
    deleted = delete_resume_image_source(image_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="简历图片不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/resume-sources", status_code=status.HTTP_201_CREATED)
def add_resume_source(source: ResumeSourceInput):
    return _save_private_file_and_record(
        source.content,
        source.filename,
        create_resume_source,
        **source.model_dump(),
    )


@app.post("/api/resume-sources/upload", status_code=status.HTTP_201_CREATED)
def upload_resume_source(source: ResumeFileInput):
    try:
        content = base64.b64decode(source.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="文件数据格式无效")
    if not content or len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件大小需在 10 MB 以内")
    filename = Path(source.filename.replace("\\", "/")).name or "resume.txt"
    try:
        extracted = extract_resume_text(filename, content)
    except DocumentParseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _save_private_file_and_record(
        content,
        filename,
        create_resume_source,
        filename=filename,
        content=extracted,
    )


@app.delete("/api/resume-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_resume_source(source_id: int):
    deleted = delete_resume_source(source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="原始简历不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/resumes", status_code=status.HTTP_201_CREATED)
def save_resume(resume: ResumeInput):
    return create_resume(**resume.model_dump())


@app.delete("/api/resumes/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_resume(resume_id: int):
    deleted = delete_resume(resume_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="简历版本不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/resume-runs")
def list_resume_runs():
    return get_agent_runs()


@app.get("/api/resume-runs/{run_id}")
def read_resume_run(run_id: int):
    run = get_agent_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="简历改进任务不存在")
    return run


@app.post("/api/resume-runs", status_code=status.HTTP_201_CREATED)
def create_resume_run(payload: ResumeRunInput):
    if not payload.allow_external_model:
        raise HTTPException(
            status_code=400,
            detail="此操作会将简历和个人资料发送给 DeepSeek。请明确确认后再开始模型调用。",
        )
    source = next(
        (item for item in get_resume_sources() if item["id"] == payload.source_resume_id),
        None,
    )
    if source is None:
        raise HTTPException(status_code=404, detail="原始简历材料不存在")
    selected_job = get_job(payload.job_id) if payload.job_id is not None else None
    if payload.job_id is not None and selected_job is None:
        raise HTTPException(status_code=404, detail="关联的岗位记录不存在")
    job_target_id = selected_job.get("target_id") if selected_job else None
    if payload.target_id and job_target_id and payload.target_id != job_target_id:
        raise HTTPException(status_code=409, detail="所选求职方向与岗位关联方向不一致，请先统一岗位方向")
    target_id = payload.target_id or job_target_id
    if target_id and not any(target["id"] == target_id for target in get_targets()):
        raise HTTPException(status_code=404, detail="关联的求职方向不存在")
    job_title = payload.job_title or (selected_job["title"] if selected_job else "")
    company = payload.company or (selected_job["company"] if selected_job else "")
    jd_text = payload.jd_text or (selected_job["description"] if selected_job else "")
    all_knowledge_items = get_knowledge_items()
    jd_analysis = analyze_jd(jd_text)
    requirement_matches = match_jd_requirements(
        jd_analysis, all_knowledge_items, source_content=source["content"]
    )
    search_text = " ".join(
        part for part in (job_title, company, jd_text, payload.instruction) if part
    )
    knowledge_items = retrieve_knowledge(all_knowledge_items, search_text)
    resume_chunks = retrieve_resume_chunks(source["content"], search_text)
    snapshot = {
        "source_filename": source["filename"],
        "instruction": payload.instruction,
        "job_id": selected_job["id"] if selected_job else None,
        "target_id": target_id,
        "job_title": job_title,
        "company": company,
        "jd_text": jd_text,
        "jd_analysis": jd_analysis,
        "requirement_matches": requirement_matches,
        "knowledge_item_ids": [item["id"] for item in knowledge_items],
        "resume_chunks": resume_chunks,
    }
    run = create_agent_run(payload.source_resume_id, snapshot)
    try:
        graph_state = run_resume_graph(
            source_content=source["content"],
            all_knowledge_items=all_knowledge_items,
            knowledge_items=knowledge_items,
            resume_chunks=resume_chunks,
            instruction=payload.instruction,
            jd_text=jd_text,
            job_title=job_title,
            company=company,
            jd_analysis=jd_analysis,
            requirement_matches=requirement_matches,
            # 通过 API 层注入，保留现有测试和模型客户端替换方式。
            draft_generator=generate_resume_draft,
        )
        draft = {
            "result_content": graph_state["result_content"],
            "greeting": graph_state.get("greeting", ""),
            "evidence": graph_state.get("evidence", []),
            "missing_info": graph_state.get("missing_info", []),
            "knowledge_item_ids": graph_state.get("knowledge_item_ids", []),
        }
    except LLMConfigurationError as error:
        update_agent_run(run["id"], "failed", error_message=str(error))
        raise HTTPException(status_code=503, detail=str(error)) from error
    except LLMError as error:
        update_agent_run(run["id"], "failed", error_message=str(error))
        raise HTTPException(status_code=502, detail=str(error)) from error
    completed = update_agent_run(
        run["id"],
        "draft",
        result_content=draft["result_content"],
        greeting=draft["greeting"],
        evidence=draft["evidence"],
        missing_info=draft["missing_info"],
        input_snapshot={
            **snapshot,
            "knowledge_item_ids": draft["knowledge_item_ids"],
            "quality_check": graph_state["quality_check"],
            "agent_graph": {
                "name": "resume_improvement",
                "status": graph_state.get("status", "awaiting_review"),
                "status_message": graph_state.get("status_message", ""),
            },
        },
    )
    return completed


@app.put("/api/resume-runs/{run_id}/draft")
def edit_resume_run(run_id: int, payload: ResumeRunUpdate):
    run = get_agent_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="简历改进任务不存在")
    if run["status"] != "draft":
        raise HTTPException(status_code=409, detail="只有待审核草稿可以编辑")
    source = next((item for item in get_resume_sources() if item["id"] == run["source_resume_id"]), None)
    if source is not None:
        knowledge_ids = set(run["input_snapshot"].get("knowledge_item_ids", []))
        knowledge_items = [
            item for item in get_knowledge_items() if item["id"] in knowledge_ids
        ]
        quality_check = analyze_resume_quality(
            source["content"], payload.result_content, knowledge_items
        )
    else:
        quality_check = run["input_snapshot"].get("quality_check", {})
    return update_agent_run(
        run_id,
        "draft",
        result_content=payload.result_content,
        greeting=payload.greeting,
        evidence=run["evidence"],
        missing_info=run["missing_info"],
        input_snapshot={**run["input_snapshot"], "quality_check": quality_check},
    )


@app.post("/api/resume-runs/{run_id}/approve", status_code=status.HTTP_201_CREATED)
def approve_resume_run(run_id: int, payload: ResumeRunApproval):
    run = get_agent_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="简历改进任务不存在")
    layout = run.get("input_snapshot", {}).get("quality_check", {}).get("layout")
    if not isinstance(layout, dict):
        layout = estimate_resume_layout(run.get("result_content", ""))
    if layout.get("estimated_pages", 1) > 1:
        raise HTTPException(
            status_code=409,
            detail=f"当前草稿预计超过一页（约 {layout.get('estimated_pages')} 页），请删减内容后再保存。",
        )
    saved = save_approved_agent_run(run_id, payload.title)
    if saved is None:
        raise HTTPException(status_code=409, detail="任务不存在或已经确认，不能重复保存")
    return saved
