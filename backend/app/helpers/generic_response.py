from pydantic import BaseModel, Field
from typing import Generic, TypeVar, Optional

T = TypeVar('T')


class GenericResponse(BaseModel, Generic[T]):
    success: bool = Field(default=True, example=True)
    message: str = Field(default="Success", example="success")
    data: Optional[T] | None = None
