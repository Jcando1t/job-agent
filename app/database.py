import json
from pathlib import Path

from app.config import get_settings
from app.models import (
    AgentRun,
    Job,
    JobTarget,
    KnowledgeItem,
    Resume,
    ResumeImageSource,
    ResumeSource,
)
from app.sqlalchemy_db import create_database_engine
from app.storage import delete_private_file, get_private_file
from sqlalchemy import delete as sqlalchemy_delete
from sqlalchemy import select as sqlalchemy_select
from sqlalchemy import update as sqlalchemy_update
from sqlalchemy.orm import Session

DATABASE_PATH = get_settings().database_path


def get_targets(database_path: Path = DATABASE_PATH) -> list[dict]:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            targets = session.scalars(
                sqlalchemy_select(JobTarget)
                .where(JobTarget.owner_id == "local")
                .order_by(JobTarget.id.desc())
            ).all()
            return [
                {
                    "id": target.id,
                    "title": target.title,
                    "keywords": target.keywords,
                    "cities": json.loads(target.cities),
                    "is_active": bool(target.is_active),
                    "created_at": target.created_at,
                    "updated_at": target.updated_at,
                }
                for target in targets
            ]
    finally:
        engine.dispose()


def create_target(
    title: str,
    keywords: str,
    cities: list[str],
    database_path: Path = DATABASE_PATH,
) -> dict:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            target = JobTarget(
                owner_id="local",
                title=title,
                keywords=keywords,
                cities=json.dumps(cities, ensure_ascii=False),
            )
            session.add(target)
            session.commit()
            session.refresh(target)
            return _target_model_to_dict(target)
    finally:
        engine.dispose()


def _target_model_to_dict(target: JobTarget) -> dict:
    return {
        "id": target.id,
        "title": target.title,
        "keywords": target.keywords,
        "cities": json.loads(target.cities),
        "is_active": bool(target.is_active),
        "created_at": target.created_at,
        "updated_at": target.updated_at,
    }


def update_target(
    target_id: int,
    title: str,
    keywords: str,
    cities: list[str],
    database_path: Path = DATABASE_PATH,
) -> dict | None:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            target = session.scalar(
                sqlalchemy_select(JobTarget).where(
                    JobTarget.id == target_id, JobTarget.owner_id == "local"
                )
            )
            if target is None:
                return None
            target.title = title
            target.keywords = keywords
            target.cities = json.dumps(cities, ensure_ascii=False)
            session.commit()
            session.refresh(target)
            return _target_model_to_dict(target)
    finally:
        engine.dispose()


def set_target_active(
    target_id: int,
    is_active: bool,
    database_path: Path = DATABASE_PATH,
) -> dict | None:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            target = session.scalar(
                sqlalchemy_select(JobTarget).where(
                    JobTarget.id == target_id, JobTarget.owner_id == "local"
                )
            )
            if target is None:
                return None
            target.is_active = int(is_active)
            session.commit()
            session.refresh(target)
            return _target_model_to_dict(target)
    finally:
        engine.dispose()


def delete_target(target_id: int, database_path: Path = DATABASE_PATH) -> bool:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            target = session.scalar(
                sqlalchemy_select(JobTarget).where(
                    JobTarget.id == target_id, JobTarget.owner_id == "local"
                )
            )
            if target is None:
                return False
            session.delete(target)
            session.commit()
            return True
    finally:
        engine.dispose()


def _to_job_dict(row: Job, target_title: str | None = None) -> dict:
    return {
        "id": row.id,
        "target_id": row.target_id,
        "target_title": target_title,
        "title": row.title,
        "company": row.company,
        "city": row.city,
        "source": row.source,
        "original_url": row.original_url,
        "description": row.description,
        "status": row.status,
        "notes": row.notes,
        "next_action": row.next_action,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def get_jobs(database_path: Path = DATABASE_PATH) -> list[dict]:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            rows = session.execute(
                sqlalchemy_select(Job, JobTarget.title)
                .outerjoin(JobTarget, JobTarget.id == Job.target_id)
                .where(Job.owner_id == "local")
                .order_by(Job.id.desc())
            ).all()
            return [_to_job_dict(job, target_title) for job, target_title in rows]
    finally:
        engine.dispose()


def get_job(job_id: int, database_path: Path = DATABASE_PATH) -> dict | None:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            row = session.execute(
                sqlalchemy_select(Job, JobTarget.title)
                .outerjoin(JobTarget, JobTarget.id == Job.target_id)
                .where(Job.id == job_id, Job.owner_id == "local")
            ).first()
            return _to_job_dict(*row) if row else None
    finally:
        engine.dispose()


def create_job(
    title: str,
    company: str = "",
    city: str = "",
    source: str = "手动录入",
    original_url: str = "",
    description: str = "",
    status: str = "未处理",
    notes: str = "",
    next_action: str = "",
    target_id: int | None = None,
    database_path: Path = DATABASE_PATH,
) -> dict | None:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            if target_id is not None and session.scalar(
                sqlalchemy_select(JobTarget.id).where(
                    JobTarget.id == target_id, JobTarget.owner_id == "local"
                )
            ) is None:
                return None
            duplicate_query = sqlalchemy_select(Job).where(
                Job.owner_id == "local",
                (Job.original_url == original_url)
                if original_url
                else (
                    (Job.title == title)
                    & (Job.company == company)
                    & (Job.city == city)
                ),
            )
            duplicate = session.scalar(duplicate_query)
            if duplicate is not None:
                target_title = session.scalar(
                    sqlalchemy_select(JobTarget.title).where(JobTarget.id == duplicate.target_id)
                ) if duplicate.target_id else None
                result = _to_job_dict(duplicate, target_title)
                result["duplicate"] = True
                return result
            job = Job(
                owner_id="local",
                target_id=target_id,
                title=title,
                company=company,
                city=city,
                source=source,
                original_url=original_url,
                description=description,
                status=status,
                notes=notes,
                next_action=next_action,
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            target_title = session.scalar(
                sqlalchemy_select(JobTarget.title).where(JobTarget.id == job.target_id)
            ) if job.target_id else None
            return _to_job_dict(job, target_title)
    finally:
        engine.dispose()


def update_job(
    job_id: int,
    title: str,
    company: str = "",
    city: str = "",
    source: str = "手动录入",
    original_url: str = "",
    description: str = "",
    status: str = "未处理",
    notes: str = "",
    next_action: str = "",
    target_id: int | None = None,
    database_path: Path = DATABASE_PATH,
) -> dict | None:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            if target_id is not None and session.scalar(
                sqlalchemy_select(JobTarget.id).where(
                    JobTarget.id == target_id, JobTarget.owner_id == "local"
                )
            ) is None:
                return None
            job = session.scalar(
                sqlalchemy_select(Job).where(Job.id == job_id, Job.owner_id == "local")
            )
            if job is None:
                return None
            duplicate_condition = (
                Job.original_url == original_url
                if original_url
                else (Job.title == title) & (Job.company == company) & (Job.city == city)
            )
            duplicate = session.scalar(
                sqlalchemy_select(Job).where(
                    Job.owner_id == "local",
                    Job.id != job_id,
                    duplicate_condition,
                )
            )
            if duplicate is not None:
                target_title = session.scalar(
                    sqlalchemy_select(JobTarget.title).where(JobTarget.id == duplicate.target_id)
                ) if duplicate.target_id else None
                result = _to_job_dict(duplicate, target_title)
                result["duplicate"] = True
                return result
            job.target_id = target_id
            job.title = title
            job.company = company
            job.city = city
            job.source = source
            job.original_url = original_url
            job.description = description
            job.status = status
            job.notes = notes
            job.next_action = next_action
            session.commit()
            session.refresh(job)
            target_title = session.scalar(
                sqlalchemy_select(JobTarget.title).where(JobTarget.id == job.target_id)
            ) if job.target_id else None
            return _to_job_dict(job, target_title)
    finally:
        engine.dispose()


def delete_job(job_id: int, database_path: Path = DATABASE_PATH) -> bool:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            job = session.scalar(
                sqlalchemy_select(Job).where(Job.id == job_id, Job.owner_id == "local")
            )
            if job is None:
                return False
            session.delete(job)
            session.commit()
            return True
    finally:
        engine.dispose()


def _knowledge_model_to_dict(item: KnowledgeItem) -> dict:
    return {
        "id": item.id,
        "category": item.category,
        "title": item.title,
        "organization": item.organization,
        "period": item.period,
        "content": item.content,
        "source_note": item.source_note,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def get_knowledge_items(database_path: Path = DATABASE_PATH) -> list[dict]:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            items = session.scalars(
                sqlalchemy_select(KnowledgeItem)
                .where(KnowledgeItem.owner_id == "local")
                .order_by(KnowledgeItem.id.desc())
            ).all()
            return [_knowledge_model_to_dict(item) for item in items]
    finally:
        engine.dispose()


def create_knowledge_item(
    category: str,
    title: str,
    organization: str = "",
    period: str = "",
    content: str = "",
    source_note: str = "",
    database_path: Path = DATABASE_PATH,
) -> dict:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            item = KnowledgeItem(
                owner_id="local",
                category=category,
                title=title,
                organization=organization,
                period=period,
                content=content,
                source_note=source_note,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return _knowledge_model_to_dict(item)
    finally:
        engine.dispose()


def update_knowledge_item(
    item_id: int,
    category: str,
    title: str,
    organization: str = "",
    period: str = "",
    content: str = "",
    source_note: str = "",
    database_path: Path = DATABASE_PATH,
) -> dict | None:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            item = session.scalar(
                sqlalchemy_select(KnowledgeItem).where(
                    KnowledgeItem.id == item_id,
                    KnowledgeItem.owner_id == "local",
                )
            )
            if item is None:
                return None
            item.category = category
            item.title = title
            item.organization = organization
            item.period = period
            item.content = content
            item.source_note = source_note
            session.commit()
            session.refresh(item)
            return _knowledge_model_to_dict(item)
    finally:
        engine.dispose()


def delete_knowledge_item(item_id: int, database_path: Path = DATABASE_PATH) -> bool:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            result = session.execute(
                sqlalchemy_delete(KnowledgeItem).where(
                    KnowledgeItem.id == item_id,
                    KnowledgeItem.owner_id == "local",
                )
            )
            session.commit()
            return result.rowcount > 0
    finally:
        engine.dispose()


def get_resumes(database_path: Path = DATABASE_PATH) -> list[dict]:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            rows = session.scalars(
                sqlalchemy_select(Resume)
                .where(Resume.owner_id == "local")
                .order_by(Resume.version.desc(), Resume.id.desc())
            ).all()
            return [_resume_model_to_dict(row) for row in rows]
    finally:
        engine.dispose()


def get_resume(resume_id: int, database_path: Path = DATABASE_PATH) -> dict | None:
    """只读取指定的本地简历版本，避免导出时加载其他个人版本。"""
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            resume = session.scalar(
                sqlalchemy_select(Resume).where(
                    Resume.id == resume_id,
                    Resume.owner_id == "local",
                )
            )
            return _resume_model_to_dict(resume) if resume else None
    finally:
        engine.dispose()


def _resume_model_to_dict(resume: Resume) -> dict:
    return {
        "id": resume.id,
        "target_id": resume.target_id,
        "is_current": bool(resume.is_current),
        "version": resume.version,
        "title": resume.title,
        "content": resume.content,
        "source_item_ids": json.loads(resume.source_item_ids),
        "source_resume_id": resume.source_resume_id,
        "photo_image_id": resume.photo_image_id,
        "greeting": resume.greeting,
        "job_snapshot": json.loads(resume.job_snapshot),
        "created_at": resume.created_at,
        "updated_at": resume.updated_at,
    }


def get_resume_sources(database_path: Path = DATABASE_PATH) -> list[dict]:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            rows = session.scalars(
                sqlalchemy_select(ResumeSource)
                .where(ResumeSource.owner_id == "local")
                .order_by(ResumeSource.id.desc())
            ).all()
            return [_resume_source_model_to_dict(row) for row in rows]
    finally:
        engine.dispose()


def _resume_source_model_to_dict(source: ResumeSource) -> dict:
    return {
        "id": source.id,
        "filename": source.filename,
        "content": source.content,
        "source_image_ids": json.loads(source.source_image_ids),
        "storage_path": source.storage_path,
        "created_at": source.created_at,
    }


def create_resume_source(
    filename: str,
    content: str,
    source_image_ids: list[int] | None = None,
    storage_path: str | None = None,
    database_path: Path = DATABASE_PATH,
) -> dict:
    source_image_ids = list(
        dict.fromkeys(image_id for image_id in (source_image_ids or []) if image_id > 0)
    )
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            source = ResumeSource(
                owner_id="local",
                filename=filename,
                content=content,
                source_image_ids=json.dumps(source_image_ids or []),
                storage_path=storage_path,
            )
            session.add(source)
            session.commit()
            session.refresh(source)
            return _resume_source_model_to_dict(source)
    finally:
        engine.dispose()


def get_resume_image_sources(database_path: Path = DATABASE_PATH) -> list[dict]:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            rows = session.scalars(
                sqlalchemy_select(ResumeImageSource)
                .where(ResumeImageSource.owner_id == "local")
                .order_by(ResumeImageSource.id.desc())
            ).all()
            return [_resume_image_model_to_dict(row) for row in rows]
    finally:
        engine.dispose()


def get_resume_image_source(
    image_id: int, database_path: Path = DATABASE_PATH
) -> dict | None:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            row = session.scalar(
                sqlalchemy_select(ResumeImageSource).where(
                    ResumeImageSource.id == image_id,
                    ResumeImageSource.owner_id == "local",
                )
            )
            return _resume_image_model_to_dict(row, include_content=True) if row else None
    finally:
        engine.dispose()


def _resume_image_model_to_dict(
    source: ResumeImageSource, include_content: bool = False
) -> dict:
    image = {
        "id": source.id,
        "filename": source.filename,
        "content_type": source.content_type,
        "storage_path": source.storage_path,
        "created_at": source.created_at,
    }
    if include_content:
        image["content"] = (
            get_private_file(source.storage_path).read_bytes()
            if source.storage_path
            else source.content
        )
    return image


def create_resume_image_source(
    filename: str,
    content_type: str,
    content: bytes,
    storage_path: str | None = None,
    database_path: Path = DATABASE_PATH,
) -> dict:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            image = ResumeImageSource(
                owner_id="local",
                filename=filename,
                content_type=content_type,
                content=content,
                storage_path=storage_path,
            )
            session.add(image)
            session.commit()
            session.refresh(image)
            return _resume_image_model_to_dict(image)
    finally:
        engine.dispose()


def delete_resume_image_source(
    image_id: int, database_path: Path = DATABASE_PATH
) -> bool:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            image = session.scalar(
                sqlalchemy_select(ResumeImageSource).where(
                    ResumeImageSource.id == image_id,
                    ResumeImageSource.owner_id == "local",
                )
            )
            if image is None:
                return False
            storage_path = image.storage_path
            session.execute(
                sqlalchemy_update(Resume)
                .where(Resume.photo_image_id == image_id, Resume.owner_id == "local")
                .values(photo_image_id=None)
            )
            session.delete(image)
            session.commit()
            delete_private_file(storage_path)
            return True
    finally:
        engine.dispose()


def delete_resume_source(source_id: int, database_path: Path = DATABASE_PATH) -> bool:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            source = session.scalar(
                sqlalchemy_select(ResumeSource).where(
                    ResumeSource.id == source_id,
                    ResumeSource.owner_id == "local",
                )
            )
            if source is None:
                return False
            storage_path = source.storage_path
            session.delete(source)
            session.commit()
            delete_private_file(storage_path)
            return True
    finally:
        engine.dispose()


def create_resume(
    title: str,
    content: str,
    source_item_ids: list[int],
    source_resume_id: int | None = None,
    greeting: str = "",
    job_snapshot: dict | None = None,
    target_id: int | None = None,
    photo_image_id: int | None = None,
    database_path: Path = DATABASE_PATH,
) -> dict:
    source_item_ids = list(dict.fromkeys(item_id for item_id in source_item_ids if item_id > 0))
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            latest_version = session.scalar(
                sqlalchemy_select(Resume.version)
                .where(Resume.owner_id == "local")
                .order_by(Resume.version.desc())
                .limit(1)
            ) or 0
            resume = Resume(
                owner_id="local",
                target_id=target_id,
                is_current=False,
                version=latest_version + 1,
                title=title,
                content=content,
                source_item_ids=json.dumps(source_item_ids),
                source_resume_id=source_resume_id,
                photo_image_id=photo_image_id,
                greeting=greeting,
                job_snapshot=json.dumps(job_snapshot or {}, ensure_ascii=False),
            )
            session.add(resume)
            session.commit()
            session.refresh(resume)
            return _resume_model_to_dict(resume)
    finally:
        engine.dispose()


def delete_resume(resume_id: int, database_path: Path = DATABASE_PATH) -> bool:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            resume = session.scalar(
                sqlalchemy_select(Resume).where(
                    Resume.id == resume_id, Resume.owner_id == "local"
                )
            )
            if resume is None:
                return False
            session.delete(resume)
            session.commit()
            return True
    finally:
        engine.dispose()


def _agent_run_model_to_dict(run: AgentRun) -> dict:
    return {
        "id": run.id,
        "source_resume_id": run.source_resume_id,
        "greeting": run.greeting,
        "status": run.status,
        "input_snapshot": json.loads(run.input_snapshot),
        "result_content": run.result_content,
        "evidence": json.loads(run.evidence_json),
        "missing_info": json.loads(run.missing_info_json),
        "error_message": run.error_message,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


def create_agent_run(
    source_resume_id: int,
    input_snapshot: dict,
    status: str = "running",
    database_path: Path = DATABASE_PATH,
) -> dict:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            run = AgentRun(
                owner_id="local",
                source_resume_id=source_resume_id,
                status=status,
                input_snapshot=json.dumps(input_snapshot, ensure_ascii=False),
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            return _agent_run_model_to_dict(run)
    finally:
        engine.dispose()


def get_agent_run(run_id: int, database_path: Path = DATABASE_PATH) -> dict | None:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            run = session.scalar(
                sqlalchemy_select(AgentRun).where(
                    AgentRun.id == run_id, AgentRun.owner_id == "local"
                )
            )
            return _agent_run_model_to_dict(run) if run else None
    finally:
        engine.dispose()


def get_agent_runs(database_path: Path = DATABASE_PATH) -> list[dict]:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            runs = session.scalars(
                sqlalchemy_select(AgentRun)
                .where(AgentRun.owner_id == "local")
                .order_by(AgentRun.id.desc())
            ).all()
            return [_agent_run_model_to_dict(run) for run in runs]
    finally:
        engine.dispose()


def update_agent_run(
    run_id: int,
    status: str,
    result_content: str = "",
    greeting: str = "",
    evidence: list[dict] | None = None,
    missing_info: list[str] | None = None,
    error_message: str = "",
    input_snapshot: dict | None = None,
    database_path: Path = DATABASE_PATH,
) -> dict | None:
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            run = session.scalar(
                sqlalchemy_select(AgentRun).where(
                    AgentRun.id == run_id, AgentRun.owner_id == "local"
                )
            )
            if run is None:
                return None
            run.status = status
            run.result_content = result_content
            run.greeting = greeting
            run.evidence_json = json.dumps(evidence or [], ensure_ascii=False)
            run.missing_info_json = json.dumps(missing_info or [], ensure_ascii=False)
            run.error_message = error_message
            if input_snapshot is not None:
                run.input_snapshot = json.dumps(input_snapshot, ensure_ascii=False)
            session.commit()
            session.refresh(run)
            return _agent_run_model_to_dict(run)
    finally:
        engine.dispose()


def save_approved_agent_run(
    run_id: int,
    title: str,
    database_path: Path = DATABASE_PATH,
) -> dict | None:
    """在同一个事务中确认草稿并保存新简历版本。"""
    engine = create_database_engine(database_path)
    try:
        with Session(engine) as session:
            run = session.scalar(
                sqlalchemy_select(AgentRun).where(
                    AgentRun.id == run_id,
                    AgentRun.owner_id == "local",
                    AgentRun.status == "draft",
                )
            )
            if run is None:
                return None
            snapshot = json.loads(run.input_snapshot)
            target_id = snapshot.get("target_id")
            is_current = bool(target_id and not snapshot.get("job_id"))
            if target_id and session.scalar(
                sqlalchemy_select(JobTarget.id).where(
                    JobTarget.id == target_id, JobTarget.owner_id == "local"
                )
            ) is None:
                target_id = None
                is_current = False
            latest_version = session.scalar(
                sqlalchemy_select(Resume.version)
                .where(Resume.owner_id == "local")
                .order_by(Resume.version.desc())
                .limit(1)
            ) or 0
            if is_current:
                session.execute(
                    sqlalchemy_update(Resume)
                    .where(
                        Resume.owner_id == "local",
                        Resume.target_id == target_id,
                        Resume.is_current.is_(True),
                    )
                    .values(is_current=False)
                )
            resume = Resume(
                owner_id="local",
                target_id=target_id,
                is_current=is_current,
                version=latest_version + 1,
                title=title,
                content=run.result_content,
                greeting=run.greeting,
                job_snapshot=json.dumps(
                    {
                        "job_id": snapshot.get("job_id"),
                        "job_title": snapshot.get("job_title", ""),
                        "company": snapshot.get("company", ""),
                        "jd_text": snapshot.get("jd_text", ""),
                    },
                    ensure_ascii=False,
                ),
                source_item_ids=json.dumps(snapshot.get("knowledge_item_ids", [])),
                source_resume_id=run.source_resume_id,
                photo_image_id=snapshot.get("photo_image_id"),
            )
            run.status = "approved"
            session.add(resume)
            session.commit()
            session.refresh(resume)
            return {
                "id": resume.id,
                "target_id": resume.target_id,
                "is_current": bool(resume.is_current),
                "version": resume.version,
                "title": resume.title,
                "content": resume.content,
                "source_item_ids": json.loads(resume.source_item_ids),
                "source_resume_id": resume.source_resume_id,
                "photo_image_id": resume.photo_image_id,
                "greeting": resume.greeting,
                "job_snapshot": json.loads(resume.job_snapshot),
                "created_at": resume.created_at,
                "updated_at": resume.updated_at,
            }
    finally:
        engine.dispose()
