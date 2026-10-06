from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from app.repositories.products_repository import ensure_products_csv
from app.services import products_service as service


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_products_csv()
    yield


app = FastAPI(title="API de Inventario", lifespan=lifespan)


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    quantity: float = Field(ge=0, allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=20)

    @field_validator("name", "unit")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("no puede estar vacío")
        return v


class StockUpdate(BaseModel):
    delta: float = Field(allow_inf_nan=False, description="Positivo: entrada. Negativo: salida.")

    @field_validator("delta")
    @classmethod
    def not_zero(cls, v: float) -> float:
        if v == 0:
            raise ValueError("delta no puede ser 0")
        return v


class Product(BaseModel):
    id: int
    name: str
    unit: str
    quantity: float


@app.get("/inventory", response_model=list[Product])
def get_inventory():
    return service.list_products()


@app.get("/inventory/alerts", response_model=list[Product])
def get_alerts(
    threshold: float = Query(
        service.DEFAULT_LOW_STOCK_THRESHOLD,
        ge=0,
        allow_inf_nan=False,
        description="Se devuelven los productos con cantidad menor a este valor.",
    ),
):
    return service.low_stock_products(threshold)


@app.post("/inventory", response_model=Product, status_code=status.HTTP_201_CREATED)
def add_product(payload: ProductCreate):
    try:
        return service.create_product(payload.name, payload.quantity, payload.unit)
    except service.DuplicateProductError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))


@app.patch("/inventory/{product_id}", response_model=Product)
def update_stock(product_id: int, payload: StockUpdate):
    try:
        return service.adjust_stock(product_id, payload.delta)
    except service.ProductNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    except service.InsufficientStockError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
