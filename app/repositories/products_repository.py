import csv
import os
import tempfile
import threading
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PRODUCTS_CSV = DATA_DIR / "products.csv"

COLUMNS = ["id", "nombre de producto", "Unidad", "Stock"]

SAMPLE_PRODUCTS = [
    {"id": 1, "nombre de producto": "Café arábica", "Unidad": "kg", "Stock": 40},
    {"id": 2, "nombre de producto": "Leche de avena", "Unidad": "litro", "Stock": 30},
    {"id": 3, "nombre de producto": "Vasos de cartón 12oz", "Unidad": "unidad", "Stock": 500},
    {"id": 4, "nombre de producto": "Azúcar", "Unidad": "kg", "Stock": 25},
]


# Serializa lectura-modificación-escritura dentro de un único proceso.
lock = threading.RLock()


def ensure_products_csv() -> None:
    """Crea data/products.csv con productos de ejemplo si no existe."""
    if PRODUCTS_CSV.exists():
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _write_rows(SAMPLE_PRODUCTS)


def read_products() -> list[dict]:
    ensure_products_csv()
    with PRODUCTS_CSV.open(newline="", encoding="utf-8") as f:
        return [
            {
                "id": int(row["id"]),
                "name": row["nombre de producto"],
                "unit": row["Unidad"],
                "quantity": float(row["Stock"]),
            }
            for row in csv.DictReader(f)
        ]


def write_products(products: list[dict]) -> None:
    _write_rows(
        [
            {
                "id": p["id"],
                "nombre de producto": p["name"],
                "Unidad": p["unit"],
                "Stock": _format_quantity(p["quantity"]),
            }
            for p in products
        ]
    )


def _format_quantity(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def _write_rows(rows: list[dict]) -> None:
    # Escritura atómica: evita dejar el CSV a medias si el proceso se interrumpe.
    fd, tmp_path = tempfile.mkstemp(dir=DATA_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp_path, PRODUCTS_CSV)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    ensure_products_csv()
    print(f"Listo: {PRODUCTS_CSV}")
