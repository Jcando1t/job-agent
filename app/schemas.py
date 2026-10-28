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
    status: Literal["未处理", "收藏", "不合适", "已投递", "面试中", "已结束"] = "未处理"
    notes: str = Field(default="", max_length=5000)
    next_action: str = Field(default="", max_length=500)
    target_id: int | None = Field(default=None, gt=0)

    @field_validator("title", "company", "city", "source", "original_url", "description", "status", "notes", "next_action")
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


class BossJobTextInput(BaseModel):
    text: str = Field(min_length=1, max_length=20000)

    @field_validator("text")
    @classmethod
    def pasted_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("请粘贴 BOSS 岗位文字")
        return value


class BossJobUrlInput(BaseModel):
    url: str = Field(min_length=1, max_length=2000)

    @field_validator("url")
    @classmethod
    def trim_url(cls, value: str) -> str:
        return value.strip()


class BossGreetingSendInput(BaseModel):
    job_id: int = Field(gt=0)
    resume_id: int = Field(gt=0)
    greeting: str = Field(min_length=1, max_length=5000)
    confirmed: bool = False

    @field_validator("greeting")
    @classmethod
    def trim_greeting(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("打招呼语不能为空")
        return value


class BossGreetingPrepareInput(BaseModel):
    job_id: int = Field(gt=0)
    resume_id: int = Field(gt=0)
    greeting: str = Field(min_length=1, max_length=5000)

    @field_validator("greeting")
    @classmethod
    def trim_greeting(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("打招呼语不能为空")
        return value


class BossResumeSendInput(BaseModel):
    job_id: int = Field(gt=0)
    resume_id: int = Field(gt=0)
    confirmed: bool = False


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
    target_id: int | None = Field(default=None, gt=0)
    photo_image_id: int | None = Field(default=None, gt=0)

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
    source_image_ids: list[int] = Field(default_factory=list, max_length=10)

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

    @field_validator("source_image_ids")
    @classmethod
    def unique_source_image_ids(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(image_id for image_id in value if image_id > 0))


class ResumeFileInput(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1, max_length=14_000_000)

    @field_validator("filename", "content_base64")
    @classmethod
    def trim_file_text(cls, value: str) -> str:
        return value.strip()


class ResumeImageInput(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: Literal["image/png", "image/jpeg", "image/webp", "image/gif"]
    content_base64: str = Field(min_length=1, max_length=14_000_000)

    @field_validator("filename", "content_base64")
    @classmethod
    def trim_image_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("filename")
    @classmethod
    def image_filename_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("图片文件名不能为空")
        return value

    @field_validator("content_base64")
    @classmethod
    def image_data_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("图片内容不能为空")
        return value


class ResumeImageOcrInput(BaseModel):
    image_ids: list[int] = Field(min_length=1, max_length=10)

    @field_validator("image_ids")
    @classmethod
    def unique_positive_image_ids(cls, value: list[int]) -> list[int]:
        if any(image_id <= 0 for image_id in value):
            raise ValueError("图片编号无效")
        return list(dict.fromkeys(value))


class ResumeRunInput(BaseModel):
    source_resume_id: int = Field(gt=0)
    job_id: int | None = Field(default=None, gt=0)
    target_id: int | None = Field(default=None, gt=0)
    instruction: str = Field(default="", max_length=2000)
    job_title: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=200)
    jd_text: str = Field(default="", max_length=30000)
    allow_external_model: bool = False
    photo_image_id: int | None = Field(default=None, gt=0)

    @field_validator("instruction")
    @classmethod
    def trim_instruction(cls, value: str) -> str:
        return value.strip()

    @field_validator("job_title", "company", "jd_text")
    @classmethod
    def trim_job_fields(cls, value: str) -> str:
        return value.strip()


class ResumeRunUpdate(BaseModel):
    result_content: str = Field(min_length=1, max_length=30000)
    greeting: str = Field(default="", max_length=5000)

    @field_validator("result_content")
    @classmethod
    def trim_result_content(cls, value: str) -> str:
        return value.strip()

    @field_validator("result_content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("修改后的简历内容不能为空")
        return value

    @field_validator("greeting")
    @classmethod
    def trim_greeting(cls, value: str) -> str:
        return value.strip()


class ResumeRunApproval(BaseModel):
    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("请填写简历版本名称")
        return value
