import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

API_URL = os.getenv("INVENTORY_API_URL", "http://127.0.0.1:8000")
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
LOG_FILE = Path(__file__).resolve().parent / "conversation_log.csv"
LOG_COLUMNS = ["actor", "message", "tool_call", "timestamp"]
HTTP_TIMEOUT = 10
MAX_STEPS = 8  # Tope de llamadas al LLM por mensaje para evitar bucles infinitos de tools.

SYSTEM_PROMPT = (
    "Eres el asistente de inventario de una tienda de suministros para cafeterías con dos locales. "
    "Responde siempre en español, de forma breve y directa. "
    "Usa las herramientas para consultar o modificar el inventario; nunca inventes datos de stock. "
    "Para actualizar el stock necesitas el id del producto: si no lo conoces, consulta primero el inventario. "
    "Entradas de mercancía son delta positivo y ventas son delta negativo. "
    "Si el usuario no indica la cantidad o el producto con claridad, pregúntale antes de actuar."
)


# ---------------------------------------------------------------- Cliente HTTP
def _request(method: str, path: str, **kwargs) -> dict | list:
    try:
        response = requests.request(method, f"{API_URL}{path}", timeout=HTTP_TIMEOUT, **kwargs)
    except requests.RequestException as e:
        return {"error": f"No se pudo contactar con la API de inventario: {e.__class__.__name__}"}
    try:
        body = response.json()
    except ValueError:
        body = None
    if response.ok:
        return body
    detail = body.get("detail") if isinstance(body, dict) else None
    return {"error": detail or f"La API respondió con HTTP {response.status_code}", "status": response.status_code}


def list_inventory() -> dict | list:
    return _request("GET", "/inventory")


def add_product(name: str, quantity: float, unit: str) -> dict | list:
    return _request("POST", "/inventory", json={"name": name, "quantity": quantity, "unit": unit})


def update_stock(product_id: int, delta: float) -> dict | list:
    return _request("PATCH", f"/inventory/{int(product_id)}", json={"delta": delta})


def get_low_stock_alerts(threshold: float | None = None) -> dict | list:
    params = {"threshold": threshold} if threshold is not None else None
    return _request("GET", "/inventory/alerts", params=params)


TOOL_FUNCTIONS = {
    "list_inventory": list_inventory,
    "add_product": add_product,
    "update_stock": update_stock,
    "get_low_stock_alerts": get_low_stock_alerts,
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_inventory",
            "description": (
                "Devuelve la lista completa de productos con id, nombre, unidad y cantidad en stock. "
                "Úsala para responder cuánto hay de un producto o para obtener el id de un producto."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_product",
            "description": (
                "Registra un producto NUEVO que todavía no existe en el inventario. "
                "No la uses para entradas o ventas de productos existentes (para eso usa update_stock)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nombre del producto, por ejemplo 'Leche de avena'."},
                    "quantity": {"type": "number", "minimum": 0, "description": "Stock inicial (no negativo)."},
                    "unit": {"type": "string", "description": "Unidad de medida: kg, litro, unidad, etc."},
                },
                "required": ["name", "quantity", "unit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_stock",
            "description": (
                "Ajusta el stock de un producto existente sumando un delta. "
                "Delta positivo para entradas de mercancía (entregas) y negativo para salidas (ventas). "
                "Requiere el id del producto; si no lo conoces, llama antes a list_inventory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "Id del producto a actualizar."},
                    "delta": {
                        "type": "number",
                        "description": "Cantidad a sumar (positiva) o restar (negativa). No puede ser 0.",
                    },
                },
                "required": ["product_id", "delta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_low_stock_alerts",
            "description": (
                "Devuelve los productos cuyo stock está por debajo de un umbral. "
                "Úsala para preguntas como '¿qué productos están por agotarse?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "threshold": {
                        "type": "number",
                        "minimum": 0,
                        "description": "Umbral de stock bajo. Si se omite, la API usa 10.",
                    },
                },
            },
        },
    },
]


# ------------------------------------------------------------------- Registro
def log_event(actor: str, message: str, tool_call: str = "") -> None:
    """Añade una fila a conversation_log.csv (solo adición; nunca sobrescribe)."""
    is_new = not LOG_FILE.exists() or LOG_FILE.stat().st_size == 0
    with LOG_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(LOG_COLUMNS)
        writer.writerow([actor, message, tool_call, datetime.now().astimezone().isoformat()])


# ------------------------------------------------------------------------ LLM
def ask_llm(client: Groq, messages: list[dict]) -> tuple[str, list[dict]]:
    """Envía el contexto al LLM, muestra el texto en streaming y devuelve (texto, tool_calls)."""
    completion = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.6,
        max_completion_tokens=1024,
        top_p=0.95,
        reasoning_effort="low",
        stream=True,
        stop=None,
    )
    content = ""
    calls: dict[int, dict] = {}
    for chunk in completion:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            if not content:
                print("Agente: ", end="", flush=True)
            content += delta.content
            print(delta.content, end="", flush=True)
        for tc in delta.tool_calls or []:
            slot = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
            if tc.id:
                slot["id"] = tc.id
            if tc.function:
                slot["name"] += tc.function.name or ""
                slot["arguments"] += tc.function.arguments or ""
    return content, [calls[i] for i in sorted(calls)]


def run_tool(name: str, raw_arguments: str) -> dict | list:
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return {"error": f"Herramienta desconocida: {name}"}
    try:
        arguments = json.loads(raw_arguments or "{}")
        if not isinstance(arguments, dict):
            raise ValueError
    except ValueError:
        return {"error": "Los argumentos de la herramienta no son un JSON de objeto válido."}
    try:
        return func(**arguments)
    except (TypeError, ValueError) as e:
        return {"error": f"Argumentos inválidos para {name}: {e}"}


def handle_user_message(client: Groq, messages: list[dict], user_input: str) -> None:
    messages.append({"role": "user", "content": user_input})
    log_event("user", user_input)

    for _ in range(MAX_STEPS):
        # Pensar: el LLM decide si responder o llamar a una tool.
        content, tool_calls = ask_llm(client, messages)
        if content:
            print()

        if not tool_calls:
            messages.append({"role": "assistant", "content": content})
            log_event("agent", content)
            return  # Respuesta final.

        messages.append(
            {
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
                    for c in tool_calls
                ],
            }
        )
        if content:
            log_event("agent", content)

        # Actuar y Actualizar: ejecutar cada tool e inyectar su resultado en el contexto.
        for call in tool_calls:
            log_event("agent", call["arguments"] or "{}", call["name"])
            result = run_tool(call["name"], call["arguments"])
            result_json = json.dumps(result, ensure_ascii=False)
            log_event("tool", result_json, call["name"])
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result_json})
    else:
        fallback = "No pude completar la solicitud tras varios intentos. Reformúlala, por favor."
        print(f"Agente: {fallback}")
        messages.append({"role": "assistant", "content": fallback})
        log_event("agent", fallback)


def main() -> None:
    if not os.getenv("GROQ_API_KEY"):
        sys.exit("Falta GROQ_API_KEY. Copia .env.example a .env y añade tu clave.")

    check = list_inventory()
    if isinstance(check, dict) and "error" in check:
        sys.exit(f"La API no responde en {API_URL}. Arráncala antes: python -m uvicorn app.api:app --reload")

    client = Groq()
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    print("Agente de inventario. Escribe 'salir' para terminar.")

    while True:
        # Observar
        try:
            user_input = input("\nTú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_input.lower() in {"salir", "exit", "quit"}:
            break
        if not user_input:
            continue
        try:
            handle_user_message(client, messages, user_input)
        except Exception as e:  # noqa: BLE001 - el bucle no debe morir por un fallo del proveedor.
            print(f"\n[error] {e.__class__.__name__}: {e}")
            log_event("agent", f"Error: {e.__class__.__name__}: {e}")


if __name__ == "__main__":
    main()
