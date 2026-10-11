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
