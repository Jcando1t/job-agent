"""SQLAlchemy 映射：字段与当前本地 SQLite 表结构保持一致。"""

from sqlalchemy import Boolean, ForeignKey, Integer, LargeBinary, String, Text, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class JobTarget(Base):
    __tablename__ = "job_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False, server_default="local")
    title: Mapped[str] = mapped_column(String, nullable=False)
    keywords: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    cities: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.current_timestamp()
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False, server_default="local")
    target_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_targets.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    company: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    city: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    source: Mapped[str] = mapped_column(String, nullable=False, server_default="手动录入")
    original_url: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="未处理")
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    next_action: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.current_timestamp()
    )


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False, server_default="local")
    category: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    organization: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    period: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_note: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=func.current_timestamp(),
    )


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False, server_default="local")
    target_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_targets.id", ondelete="SET NULL"), nullable=True
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_item_ids: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.current_timestamp()
    )
    source_resume_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    greeting: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    job_snapshot: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")


class ResumeSource(Base):
    __tablename__ = "resume_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False, server_default="local")
    filename: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    source_image_ids: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    storage_path: Mapped[str | None] = mapped_column(String, nullable=True)


class ResumeImageSource(Base):
    __tablename__ = "resume_image_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False, server_default="local")
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class AgentRun(Base):
    """一次简历改进任务及其审核状态。"""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False, server_default="local")
    source_resume_id: Mapped[int] = mapped_column(
        ForeignKey("resume_sources.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="draft")
    input_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    result_content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    greeting: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    missing_info_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.current_timestamp()
    )
