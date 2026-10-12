from urllib.parse import urlsplit
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TargetInput(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    keywords: str = Field(default="", max_length=500)
    cities: list[str] = Field(min_length=1, max_length=10)

    @field_validator("title", "keywords")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("请填写岗位名称")
        return value

    @field_validator("cities")
    @classmethod
    def clean_cities(cls, cities: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(city.strip() for city in cities if city.strip()))
        if not cleaned:
            raise ValueError("至少选择或填写一个城市")
        return cleaned


class ActiveUpdate(BaseModel):
    is_active: bool


class JobInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    company: str = Field(default="", max_length=120)
    city: str = Field(default="", max_length=80)
    source: str = Field(default="手动录入", max_length=80)
    original_url: str = Field(default="", max_length=1000)
    description: str = Field(default="", max_length=10000)
    target_id: int | None = Field(default=None, gt=0)

    @field_validator("title", "company", "city", "source", "original_url", "description")
    @classmethod
    def trim_job_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("请填写岗位名称")
        return value

    @field_validator("source")
    @classmethod
    def source_must_have_default(cls, value: str) -> str:
        return value or "手动录入"

    @field_validator("original_url")
    @classmethod
    def original_url_must_be_http(cls, value: str) -> str:
        if value:
            parts = urlsplit(value)
            if parts.scheme not in {"http", "https"} or not parts.netloc:
                raise ValueError("原始链接需要以 http:// 或 https:// 开头")
        return value


class KnowledgeInput(BaseModel):
    category: Literal["个人信息", "教育经历", "工作经历", "项目经验", "技能", "成果"]
    title: str = Field(min_length=1, max_length=120)
    organization: str = Field(default="", max_length=120)
    period: str = Field(default="", max_length=80)
    content: str = Field(min_length=1, max_length=10000)
    source_note: str = Field(default="", max_length=300)

    @field_validator("title", "organization", "period", "content", "source_note")
    @classmethod
    def trim_knowledge_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("请填写条目名称")
        return value

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("请填写经历或技能内容")
        return value


class ResumeInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=30000)
    source_item_ids: list[int] = Field(default_factory=list, max_length=200)
    source_resume_id: int | None = Field(default=None, gt=0)

    @field_validator("title", "content")
    @classmethod
    def trim_resume_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("title")
    @classmethod
    def resume_title_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("请填写简历名称")
        return value

    @field_validator("content")
    @classmethod
    def resume_content_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("简历内容不能为空")
        return value

    @field_validator("source_item_ids")
    @classmethod
    def unique_source_ids(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(item_id for item_id in value if item_id > 0))


class ResumeSourceInput(BaseModel):
    filename: str = Field(default="手动粘贴", max_length=255)
    content: str = Field(min_length=1, max_length=30000)

    @field_validator("filename", "content")
    @classmethod
    def trim_source_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("filename")
    @classmethod
    def filename_must_not_be_blank(cls, value: str) -> str:
        return value or "手动粘贴"

    @field_validator("content")
    @classmethod
    def source_content_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("简历原文不能为空")
        return value
