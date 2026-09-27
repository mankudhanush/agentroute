"""Request bodies for the API. Routing fields are not declared here."""

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=100_000)
    conversation_id: str | None = None
    # Plugin capabilities for this request. Omitted keeps the existing tool path.
    blender: bool = True
    playwright: bool = True

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Message is empty.")
        return text

    @field_validator("conversation_id")
    @classmethod
    def blank_id_is_absent(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None
