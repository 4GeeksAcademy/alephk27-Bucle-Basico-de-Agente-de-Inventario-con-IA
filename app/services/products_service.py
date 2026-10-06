from app.repositories import products_repository as repo

DEFAULT_LOW_STOCK_THRESHOLD = 10


class ProductNotFoundError(Exception):
    pass


class DuplicateProductError(Exception):
    pass


class InsufficientStockError(Exception):
    pass


def list_products() -> list[dict]:
    return repo.read_products()


def create_product(name: str, quantity: float, unit: str) -> dict:
    with repo.lock:
        products = repo.read_products()
        if any(p["name"].casefold() == name.casefold() for p in products):
            raise DuplicateProductError(f"Ya existe un producto llamado '{name}'.")
        product = {
            "id": max((p["id"] for p in products), default=0) + 1,
            "name": name,
            "unit": unit,
            "quantity": quantity,
        }
        products.append(product)
        repo.write_products(products)
        return product


def adjust_stock(product_id: int, delta: float) -> dict:
    with repo.lock:
        products = repo.read_products()
        product = next((p for p in products if p["id"] == product_id), None)
        if product is None:
            raise ProductNotFoundError(f"No existe el producto con id {product_id}.")
        new_quantity = product["quantity"] + delta
        if new_quantity < 0:
            raise InsufficientStockError(
                f"Stock insuficiente para '{product['name']}': disponible "
                f"{product['quantity']:g} {product['unit']}, se intentó restar {abs(delta):g}."
            )
        product["quantity"] = new_quantity
        repo.write_products(products)
        return product


def low_stock_products(threshold: float = DEFAULT_LOW_STOCK_THRESHOLD) -> list[dict]:
    return [p for p in repo.read_products() if p["quantity"] < threshold]
