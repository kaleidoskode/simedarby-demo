"""Food and beverage catalogue endpoint."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.core.construct_services import catalog
from app.helpers.generic_response import GenericResponse
from app.schemas.common_schema import FnbCategory
from app.schemas.fnb_schema import FnbItem
from app.services import catalog_services

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=GenericResponse[List[FnbItem]],
            summary="List food and beverage items")
async def list_fnb(
    *,
    service: catalog_services.CatalogServices = Depends(catalog),
    category: Optional[FnbCategory] = Query(
        default=None,
        description="One of the tabs: combo, food_snacks or beverages"),
):
    """The Beverages & Food screen.

    A discounted item carries both prices: `price` is payable and
    `original_price` is the struck-through amount, with `discount_pct` for the
    badge.
    """
    data = await service.list_fnb(category=category)
    return GenericResponse(message=f"{len(data)} items", data=data)
