from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
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
    get_jobs,
    get_knowledge_items,
    get_resumes,
    get_resume_sources,
    get_targets,
    initialize_database,
    set_target_active,
    update_job,
    update_knowledge_item,
    update_target,
    create_resume,
    create_resume_source,
)
from app.schemas import (
    ActiveUpdate,
    JobInput,
    KnowledgeInput,
    ResumeInput,
    ResumeSourceInput,
    TargetInput,
)


TEMPLATE_DIRECTORY = Path(__file__).resolve().parent / "app" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIRECTORY))


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="求职 Agent", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


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


@app.post("/api/jobs", status_code=status.HTTP_201_CREATED)
def add_job(job: JobInput):
    created = create_job(**job.model_dump())
    if created is None:
        raise HTTPException(status_code=404, detail="关联的求职方向不存在")
    return created


@app.put("/api/jobs/{job_id}")
def edit_job(job_id: int, job: JobInput):
    updated = update_job(job_id=job_id, **job.model_dump())
    if updated is None:
        raise HTTPException(status_code=404, detail="岗位或关联的求职方向不存在")
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


@app.get("/api/resume-sources")
def list_resume_sources():
    return get_resume_sources()


@app.post("/api/resume-sources", status_code=status.HTTP_201_CREATED)
def add_resume_source(source: ResumeSourceInput):
    return create_resume_source(**source.model_dump())


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
