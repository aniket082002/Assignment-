from itertools import count
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException


app = FastAPI(
    title="Data Utility API",
    description="A CRUD API with request validation and error handling.",
    version="1.0.0",
)

# In-memory storage for demonstration.
items: dict[int, dict[str, Any]] = {}
id_counter = count(1)


class ItemCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    price: float = Field(gt=0, allow_inf_nan=False)
    quantity: int = Field(default=0, ge=0)


class ItemUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    quantity: int | None = Field(default=None, ge=0)


class Item(ItemCreate):
    id: int


def get_item_or_404(item_id: int) -> dict[str, Any]:
    item = items.get(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with ID {item_id} not found",
        )
    return item


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP_ERROR",
            "message": str(exc.detail),
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "VALIDATION_ERROR",
            "message": "Request data is invalid",
            "details": exc.errors(include_input=False),
        },
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request, exc: Exception):
    # Avoid exposing internal exception details to API clients.
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
        },
    )


@app.get("/")
def root():
    return {
        "message": "Data Utility API is running",
        "docs": "/docs",
    }


@app.post(
    "/items",
    response_model=Item,
    status_code=status.HTTP_201_CREATED,
    tags=["Items"],
)
def create_item(payload: ItemCreate):
    item_id = next(id_counter)
    item = {"id": item_id, **payload.model_dump()}
    items[item_id] = item
    return item


@app.get("/items", response_model=list[Item], tags=["Items"])
def list_items(
    skip: int = 0,
    limit: Annotated[int, Field(ge=1, le=100)] = 10,
):
    if skip < 0:
        raise HTTPException(
            status_code=400,
            detail="skip must be non-negative",
        )
    return list(items.values())[skip : skip + limit]


@app.get("/items/{item_id}", response_model=Item, tags=["Items"])
def read_item(
    item_id: Annotated[int, Path(ge=1)],
):
    return get_item_or_404(item_id)


@app.put("/items/{item_id}", response_model=Item, tags=["Items"])
def replace_item(
    item_id: Annotated[int, Path(ge=1)],
    payload: ItemCreate,
):
    get_item_or_404(item_id)
    item = {"id": item_id, **payload.model_dump()}
    items[item_id] = item
    return item


@app.patch("/items/{item_id}", response_model=Item, tags=["Items"])
def update_item(
    item_id: Annotated[int, Path(ge=1)],
    payload: ItemUpdate,
):
    item = get_item_or_404(item_id)
    changes = payload.model_dump(exclude_unset=True)

    # Prevent explicit nulls for fields that cannot be null.
    for field in ("name", "price", "quantity"):
        if field in changes and changes[field] is None:
            raise HTTPException(
                status_code=422,
                detail=f"{field} cannot be null",
            )

    item.update(changes)
    return item


@app.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Items"],
)
def delete_item(
    item_id: Annotated[int, Path(ge=1)],
):
    get_item_or_404(item_id)
    del items[item_id]
    return None