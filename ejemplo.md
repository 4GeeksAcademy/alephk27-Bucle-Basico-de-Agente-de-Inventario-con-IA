# Sistema de Inventario con API REST y Agente de IA

Una pequeña empresa familiar — una tienda de suministros para cafeterías con dos locales físicos — está perdiendo dinero. No por las ventas, sino porque nadie en el equipo puede responder con seguridad a una pregunta simple en un momento dado: *"¿Tenemos suficiente de este producto para cubrir la semana?"*

El stock se lleva en una hoja de cálculo compartida que nadie actualiza de forma consistente. La dueña, Carla, se ha puesto en contacto contigo después de ver una demo de un asistente de IA en una feria del sector. No quiere un panel de control que tenga que mantener a mano — quiere poder hablar con un sistema y obtener respuestas. También quiere que el sistema actúe: registrar entregas, apuntar ventas y avisarle cuando algo esté por agotarse, todo mediante lenguaje natural.

Tu trabajo es construir ese sistema. Tiene dos partes que deben funcionar juntas:

**1. Una API REST** construida con FastAPI que gestiona los datos del inventario. Expone endpoints para listar productos, registrar nuevos, actualizar cantidades y obtener alertas de stock bajo. Los productos se almacenan en un fichero CSV para que los datos persistan entre sesiones.

**2. Un agente de IA** escrito en Python que se conecta a un LLM y utiliza tu API como conjunto de herramientas. El agente funciona en un bucle: recibe un mensaje de Carla, razona sobre qué acción tomar, llama al endpoint de la API correspondiente como una tool, y responde con el resultado. Cada paso de ese bucle queda registrado en un fichero `conversation_log.csv`.

---

## Conocimiento complementario: el bucle del agente y el uso de tools

A estas alturas del curso ya sabes construir una API con FastAPI y llamar a una API externa desde Python. Un agente de IA añade una capa sobre eso: en lugar de que *tú* decidas cuándo llamar a qué endpoint, lo decide el **LLM**. Describes tus endpoints como herramientas (tools) — cada una con un nombre, una descripción y sus parámetros esperados — y el modelo selecciona la adecuada según el mensaje del usuario.

El bucle sigue este ciclo:

```text
Observar (leer el input del usuario)
    → Pensar (enviar al LLM con las definiciones de tools)
        → Actuar (llamar a la tool que el LLM seleccionó)
            → Actualizar (inyectar el resultado de vuelta en el contexto del LLM)
                → Repetir hasta que el LLM dé una respuesta final
```

Tu agente debe implementar este ciclo en un único fichero Python (`agent.py`). Debe mantener el historial completo de mensajes en memoria durante la sesión para que el LLM pueda razonar sobre intercambios anteriores.

---

## Registro de conversación

Cada evento del bucle debe añadirse al fichero `conversation_log.csv` con estos cuatro campos:

| **Campo** | **Descripción** |
|:---------:|:---------------:|
| `actor` | `user`, `agent` o `tool` |
| `message` | El contenido del texto o resultado del evento |
| `tool_call` | Nombre de la tool llamada (vacío si no aplica) |
| `timestamp` | Fecha y hora del evento en formato ISO 8601 |

Este fichero es de solo adición (*append-only*). Cada sesión añade filas — no sobreescribe las anteriores.

> Carla ha enviado los siguientes requisitos por correo electrónico:
>
> *"Necesito poder decirle cosas al sistema como 'acaban de llegar 30 unidades de leche de avena' o 'vendimos 12 bolsas de arábica hoy'. Que me entienda y actualice el stock. También quiero poder preguntarle '¿qué productos están por agotarse?' y recibir una respuesta directa. Que se sienta como una conversación, no como rellenar un formulario."*

Tienes libertad creativa total sobre el catálogo de productos y la estructura de datos, siempre que soporte nombre, cantidad y unidad de medida (unidades, kg, litros, etc.).

Construye algo que Carla pueda usar el lunes por la mañana.

---

## 🌱 Cómo iniciar el proyecto

Este proyecto utiliza una plantilla de inicio en Python. Haz un fork y clónala:

```text
https://github.com/4GeeksAcademy/python-hello
```

Puedes trabajar en **GitHub Codespaces** (abre el repositorio y haz clic en *Code → Codespaces → Create*) o clonándolo localmente. Una vez clonado, crea tu propio repositorio en GitHub y actualiza la URL del remote para que tu progreso quede registrado ahí.

Instrucciones completas: [**cómo iniciar un proyecto de programación**](https://4geeks.com/lesson/how-to-start-a-project)

### Arrancar el sistema

Necesitas dos terminales abiertos al mismo tiempo — uno para la API y otro para el agente.

**Terminal 1 — arrancar la API**

```bash
uvicorn api.app:app --reload
```

**Terminal 2 — arrancar el agente**

```bash
python agent.py
```

### Detener el sistema

Pulsa `Ctrl + C` en cada terminal para detener el proceso correspondiente. Detén primero el agente y luego la API. El fichero `conversation_log.csv` se escribe de forma incremental, por lo que no se pierde ningún dato al detener la ejecución a mitad de sesión.

### Relanzar el agente

Ejecuta `python agent.py` de nuevo en el Terminal 2. No es necesario reiniciar la API. El agente iniciará una nueva sesión, pero todo el historial de conversaciones anteriores permanecerá intacto en `conversation_log.csv` — las filas nuevas siempre se añaden, nunca se sobreescriben.

### Instalar dependencias

Con el entorno listo, instala las dependencias:

```bash
uv add fastapi uvicorn openai python-dotenv
```

Crea un fichero `.env` en la raíz con tu clave de API del LLM:

```env
GROQ_API_KEY=tu_clave_aqui
```

⚠️ **IMPORTANTE:** No subas nunca tu fichero `.env` al repositorio. Añádelo al `.gitignore` antes de tu primer commit.
