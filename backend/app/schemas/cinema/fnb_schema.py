"""Food and beverage catalogue models."""

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.cinema.common_schema import FnbCategory, Money


class FnbItem(BaseModel):
    """An item on the Beverages & Food screen.

    `price` is what the customer pays. When the item is discounted,
    `original_price` carries the struck-through amount and `discount_pct` the
    badge value, matching the "10% off" treatment in the design.
    """

    id: str = Field(..., examples=["fnb_fresh_xl_combo"])
    category: FnbCategory
    name: str = Field(..., examples=["Fresh XL Combo"])
    description: str = Field(..., examples=["Double large popcorn and 4 pepsi"])
    image_url: Optional[str] = None
    price: Money
    original_price: Optional[Money] = None
    discount_pct: Optional[int] = Field(default=None, ge=1, le=100,
                                        examples=[10])
    is_available: bool = True
