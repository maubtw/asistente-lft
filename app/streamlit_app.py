"""Demo del Asistente LFT (Streamlit). Habla con la API (api/main.py) por HTTP.

    uv run uvicorn api.main:app          # en una terminal
    uv run streamlit run app/streamlit_app.py

o simplemente `make demo`.
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

API_URL = os.getenv("LFT_API_URL", "http://localhost:8000")
TIMEOUT_S = 180

EXAMPLES = [
    "Llevo 3 años en la empresa, ¿cuántos días de vacaciones tengo?",
    "Me despidieron sin causa, ¿qué puedo exigir?",
    "Si trabajo el 1 de enero, ¿cuánto me tienen que pagar?",
    "¿Los papás tienen derecho a permiso cuando nace su hijo?",
]

STAGE_LABELS = {
    "reescritura": "Reescritura de la consulta (LLM)",
    "busqueda": "Búsqueda vectorial + léxica",
    "reranker": "Reranker (cross-encoder)",
    "referencias": "Expansión de referencias",
    "generacion": "Generación de la respuesta (LLM)",
}

st.set_page_config(page_title="Asistente LFT", page_icon="⚖️", layout="centered")


# --- Llamadas a la API -----------------------------------------------------------------------


@st.cache_data(ttl=60, show_spinner=False)
def fetch_health() -> dict | None:
    try:
        response = httpx.get(f"{API_URL}/health", timeout=5)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return None


def ask_api(question: str, mode: str, user_key: str | None) -> dict:
    headers = {"X-OpenAI-Key": user_key} if user_key else {}
    try:
        response = httpx.post(
            f"{API_URL}/ask",
            json={"pregunta": question, "modo": mode, "debug": True},
            headers=headers,
            timeout=TIMEOUT_S,
        )
    except httpx.ConnectError:
        return {"error": f"No hay conexión con la API en {API_URL}. Arráncala con `make api`."}
    except httpx.TimeoutException:
        return {"error": "La respuesta tardó demasiado. Intenta de nuevo o usa el modo ligero."}
    if response.status_code != 200:
        detail = response.json().get("detail", response.text) if response.content else ""
        return {"error": f"Error {response.status_code}: {detail}"}
    return response.json()


# --- Presentación ----------------------------------------------------------------------------


def law_text_markdown(text: str) -> str:
    """El texto de la ley separa párrafos y fracciones con saltos simples."""
    return "\n\n".join(line for line in text.split("\n") if line.strip())


def render_citations(citations: list[dict]) -> None:
    if not citations:
        return
    st.markdown("**Artículos citados**")
    for cita in citations:
        location = cita.get("capitulo") or cita.get("titulo") or ""
        with st.expander(f"📄 Art. {cita['articulo']}, LFT — {location}"):
            if cita.get("titulo") and cita.get("capitulo"):
                st.caption(cita["titulo"])
            st.markdown(law_text_markdown(cita["texto"]))


def render_debug(data: dict) -> None:
    with st.expander("🔍 Modo debug: recuperación y latencias"):
        if data.get("consulta_reescrita"):
            st.markdown(f"**Consulta reescrita:** _{data['consulta_reescrita']}_")

        rows = []
        for position, item in enumerate(data.get("recuperados", []), start=1):
            ranks = item.get("ranks", {})
            detail = (
                f"citado por Art. {ranks['referido_por']}"
                if "referido_por" in ranks
                else ", ".join(f"{k} #{v}" for k, v in ranks.items())
            )
            rows.append(
                {
                    "#": position,
                    "Artículo": item.get("articulo") or ", ".join(item.get("articulos", [])),
                    "Origen": item["fuente"],
                    "Score": round(item["score"], 4),
                    "Posición en cada etapa": detail,
                }
            )
        if rows:
            st.markdown("**Artículos que recibió el modelo** (en orden)")
            st.dataframe(rows, hide_index=True, use_container_width=True)

        latencies = data.get("latencias_ms", {})
        total = latencies.get("total") or 1
        stages = [
            {
                "Etapa": STAGE_LABELS.get(name, name),
                "ms": ms,
                "% del total": f"{100 * ms / total:.0f}%",
            }
            for name, ms in latencies.items()
            if name != "total"
        ]
        if stages:
            st.markdown(f"**Latencia por etapa** (total {total / 1000:.1f} s)")
            st.dataframe(stages, hide_index=True, use_container_width=True)


def render_answer(data: dict, debug: bool) -> None:
    if "error" in data:
        st.error(data["error"])
        return
    if data.get("abstencion"):
        st.info(data["respuesta"])
        st.caption(
            "El sistema solo responde con el texto de la LFT. Si no encuentra el fundamento, "
            "lo dice en lugar de inventar."
        )
    else:
        st.markdown(data["respuesta"])
    render_citations(data.get("citas", []))
    seconds = data.get("latencias_ms", {}).get("total", 0) / 1000
    st.caption(
        f"Texto vigente: última reforma DOF {format_date(data.get('fecha_reforma'))} · "
        f"modo {data.get('modo', '')} · {seconds:.1f} s"
    )
    if debug:
        render_debug(data)


def format_date(iso: str | None) -> str:
    if not iso:
        return "desconocida"
    year, month, day = iso.split("-")
    return f"{day}-{month}-{year}"


# --- Página ----------------------------------------------------------------------------------

health = fetch_health()

with st.sidebar:
    st.header("Configuración")
    mode = st.radio(
        "Modo del pipeline",
        options=["completo", "ligero"],
        format_func=str.capitalize,
        help="Ambos son configuraciones medidas en la evaluación (ver docs/decisiones.md).",
    )
    if health:
        st.caption(health["modos"][mode])
    debug = st.toggle("Modo debug", help="Muestra los artículos recuperados y la latencia.")

    with st.expander("🔑 Tu API key de OpenAI (opcional)"):
        user_key = st.text_input(
            "API key",
            type="password",
            placeholder="sk-...",
            label_visibility="collapsed",
        )
        st.caption(
            "Si la dejas vacía se usa la del archivo `.env`. Si la escribes, se envía a tu API "
            "local solo en cada pregunta: no se guarda en disco ni en los registros."
        )

    st.divider()
    if health:
        st.success("API conectada", icon="✅")
        if not health["api_key_configurada"] and not user_key:
            st.warning("No hay API key en `.env`: escribe la tuya arriba.", icon="🔑")
    else:
        st.error(f"API no disponible en {API_URL}. Arráncala con `make api`.", icon="⚠️")
    if st.button("Limpiar conversación", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    st.caption(
        "Proyecto de portafolio: RAG sobre la Ley Federal del Trabajo con evaluación medida "
        "en cada mejora."
    )

st.title("⚖️ Asistente LFT")
st.markdown(
    "Pregúntale a la **Ley Federal del Trabajo** en lenguaje natural y obtén la respuesta con el "
    "**artículo exacto citado**."
)
st.warning("Información orientativa. No sustituye asesoría legal profesional.", icon="⚠️")
if health:
    st.caption(
        f"Texto vigente de la LFT · última reforma publicada en el DOF el "
        f"**{format_date(health['fecha_reforma'])}** · "
        f"{health['articulos_vigentes']:,} artículos vigentes"
    )

if "messages" not in st.session_state:
    st.session_state.messages = []

if not st.session_state.messages:
    st.markdown("##### Prueba con una pregunta de ejemplo")
    columns = st.columns(2)
    for i, example in enumerate(EXAMPLES):
        if columns[i % 2].button(example, key=f"example_{i}", use_container_width=True):
            st.session_state.pending_question = example
            st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar="⚖️" if message["role"] == "assistant" else None):
        if message["role"] == "user":
            st.markdown(message["content"])
        else:
            render_answer(message["data"], debug)

question = st.chat_input("Escribe tu pregunta sobre la LFT…") or st.session_state.pop(
    "pending_question", None
)
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant", avatar="⚖️"):
        with st.spinner("Buscando en la ley…"):
            data = ask_api(question, mode, user_key or None)
        render_answer(data, debug)
    st.session_state.messages.append({"role": "assistant", "data": data})
