"""
Base models and mixins for NEXUS data structures.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict, Field


class BaseModel(PydanticBaseModel):
    """Base model with common configuration for all NEXUS models."""

    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
        arbitrary_types_allowed=True,
        json_encoders={
            Decimal: str,
            datetime: lambda v: v.isoformat(),
            UUID: str,
        },
    )

    def model_dump_json_safe(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary representation."""
        return self.model_dump(mode="json")


class TimestampMixin(BaseModel):
    """Mixin for models that track creation and update timestamps."""

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None


class IdentifiableMixin(BaseModel):
    """Mixin for models with UUID identifiers."""

    id: UUID = Field(default_factory=uuid4)


class AuditMixin(TimestampMixin):
    """Mixin for models that track audit information."""

    created_by: Optional[str] = None
    updated_by: Optional[str] = None


def generate_id() -> str:
    """Generate a unique identifier string."""
    return str(uuid4())
