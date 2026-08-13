from pydantic import BaseModel, Field
from typing import Generic, TypeVar, Optional

T = TypeVar('T')


class GenericResponse(BaseModel, Generic[T]):
    success: bool = Field(default=True, example=True)
    message: str = Field(default="Success", example="success")
    data: Optional[T] = None

    model_config = {
        "exclude_none": True
    }

class GenericResponseFalse(BaseModel, Generic[T]):
    success: bool = Field(default=False, example=False)
    message: str = Field(default="Failed", example="failed")

    model_config = {
        "exclude_none": True
    }

class GenericJSONResponse(BaseModel, Generic[T]):
    total_data: int = Field(default="0", example="0")
    dataset: Optional[T] = None

    model_config = {
        "exclude_none": True
    }
