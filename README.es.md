# Sistema de Inventario con API REST y Agente de IA

Sistema para una tienda de suministros para cafeterías con dos locales. Permite consultar y actualizar el inventario hablando en lenguaje natural, por ejemplo *"llegaron 30 litros de leche de avena"* o *"¿qué productos están por agotarse?"*.

Tiene dos partes que se ejecutan por separado:

1. **API REST (FastAPI):** gestiona el inventario y lo guarda en `data/products.csv`.
2. **Agente de IA (`agent.py`):** conversa con un LLM de Groq, que decide qué endpoint de la API llamar mediante *tools*. Cada evento se registra en `conversation_log.csv`.

## Arquitectura

Monolito organizado por capas. El agente es un cliente independiente que solo se comunica con la API; nunca accede al CSV directamente.

```text
Usuario → agent.py → LLM (Groq)
              │
              ▼ HTTP
        app/api.py            rutas y validación (FastAPI)
              │
        app/services/         reglas de negocio (stock, duplicados, alertas)
              │
        app/repositories/     acceso a data/products.csv
```

### Estructura del proyecto

```text
.
├── agent.py                          # Agente: bucle, tools y cliente HTTP
├── app/
│   ├── api.py                        # Endpoints FastAPI
│   ├── services/
│   │   └── products_service.py       # Lógica de inventario
│   └── repositories/
│       └── products_repository.py    # Lectura/escritura del CSV
├── data/products.csv                 # Inventario (se crea solo si no existe)
├── conversation_log.csv              # Registro de conversaciones (solo adición)
├── requirements.txt
└── .env.example
```

## Requisitos

- Python 3.10 o superior.
- Una clave de API de [Groq](https://console.groq.com).

## Instalación

```bash
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` y añade tu clave:

```env
GROQ_API_KEY=tu_clave_aqui
```

Variables opcionales:

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Modelo de chat de Groq. Debe soportar tool calling y estar disponible para tu clave. |
| `INVENTORY_API_URL` | `http://127.0.0.1:8000` | URL de la API que usa el agente. |

> No subas nunca `.env` al repositorio. Ya está incluido en `.gitignore`.

## Uso

Necesitas dos terminales abiertas en la raíz del proyecto. **La API debe estar en ejecución antes de iniciar el agente**; si no responde, el agente termina con un aviso.

**Terminal 1: API**

```bash
python -m uvicorn app.api:app --reload
```

La documentación interactiva está en `http://127.0.0.1:8000/docs`. Al arrancar, si `data/products.csv` no existe, se crea con 4 productos de ejemplo.

**Terminal 2: agente**

```bash
python agent.py
```

Escribe tus mensajes en el prompt `Tú:` y `salir` para terminar. Para detener el sistema, cierra primero el agente y después la API (`Ctrl + C`).

Ejemplos de conversación:

```text
Tú: ¿qué productos están por agotarse?
Tú: llegaron 30 litros de leche de avena
Tú: vendimos 12 kg de café arábica
Tú: registra un producto nuevo: Matcha, 3 kg
```

## API

| Método | Ruta | Descripción | Respuestas |
|---|---|---|---|
| `GET` | `/inventory` | Lista todos los productos. | 200 |
| `POST` | `/inventory` | Añade un producto. | 201, 409 (nombre duplicado), 422 |
| `PATCH` | `/inventory/{product_id}` | Suma o resta stock con un `delta`. | 200, 404, 409 (stock insuficiente), 422 |
| `GET` | `/inventory/alerts?threshold=10` | Productos con cantidad **menor** al umbral (por defecto 10). | 200, 422 |

Los errores devuelven un mensaje descriptivo en el campo `detail`.

Ejemplos:

```bash
curl http://127.0.0.1:8000/inventory

curl -X POST http://127.0.0.1:8000/inventory \
  -H "Content-Type: application/json" \
  -d '{"name": "Matcha", "quantity": 3, "unit": "kg"}'

# delta positivo: entrada de mercancía. Negativo: venta o salida.
curl -X PATCH http://127.0.0.1:8000/inventory/1 \
  -H "Content-Type: application/json" \
  -d '{"delta": -5}'

curl "http://127.0.0.1:8000/inventory/alerts?threshold=20"
```

Los productos se devuelven con este formato:

```json
{"id": 1, "name": "Café arábica", "unit": "kg", "quantity": 40.0}
```

### Formato de `data/products.csv`

```csv
id,nombre de producto,Unidad,Stock
1,Café arábica,kg,40
```

## Agente y tools

`agent.py` implementa el ciclo **Observar → Pensar → Actuar → Actualizar → Repetir**:

1. **Observar:** lee el mensaje del usuario.
2. **Pensar:** envía el historial y las definiciones de tools al LLM.
3. **Actuar:** si el LLM elige una tool, el agente llama al endpoint correspondiente.
4. **Actualizar:** el resultado se añade al historial de la conversación.
5. **Repetir:** vuelve al LLM hasta que responde sin pedir más tools (máximo 8 pasos por mensaje).

El historial completo se mantiene en memoria durante la sesión.

| Tool | Endpoint | Cuándo se usa |
|---|---|---|
| `list_inventory` | `GET /inventory` | Consultar productos, cantidades o ids. |
| `add_product` | `POST /inventory` | Registrar un producto nuevo. |
| `update_stock` | `PATCH /inventory/{id}` | Entradas (delta positivo) y ventas (delta negativo). |
| `get_low_stock_alerts` | `GET /inventory/alerts` | Preguntar qué se está agotando. |

## Registro de conversación

Cada evento se añade a `conversation_log.csv`. El fichero es de solo adición: cada sesión agrega filas y nunca sobrescribe las anteriores.

| Campo | Descripción |
|---|---|
| `actor` | `user`, `agent` o `tool` |
| `message` | Texto del mensaje, argumentos de la tool o su resultado |
| `tool_call` | Nombre de la tool (vacío si no aplica) |
| `timestamp` | Fecha y hora en formato ISO 8601 |

## Limitaciones

- El stock es un total por producto; no se separa por local.
- Al reiniciar el agente, el LLM no recibe el historial de sesiones anteriores; el log solo se guarda.
- El CSV es adecuado para este alcance. La API serializa las escrituras dentro de un solo proceso, pero no está pensada para varios procesos escribiendo a la vez.
- Los mensajes ambiguos (por ejemplo, `50 unidades, 1kg`) pueden interpretarse de forma distinta a la esperada.
- Los límites de uso dependen del plan de Groq y del modelo elegido.
