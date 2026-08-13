from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar('T')


class GenericResponse(BaseModel, Generic[T]):
    """Envelope every endpoint responds with.

    A consistent shape means a client parses success and failure the same way:
    the exception middleware returns the same `success` and `message` keys, with
    `data` replaced by `error`.
    """

    success: bool = Field(default=True, examples=[True])
    message: str = Field(default="Success", examples=["Success"])
    data: Optional[T] = None
