from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.database import (
    create_target,
    delete_target,
    get_targets,
    initialize_database,
    set_target_active,
    update_target,
)
from app.schemas import ActiveUpdate, TargetInput


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
