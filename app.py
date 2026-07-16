import os

import pandas as pd
import requests
import streamlit as st
from pandas.api.types import is_numeric_dtype

from csv_export import rows_to_csv

st.set_page_config(
    page_title="DataBridge AI",
    page_icon="🌉",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1180px;
        padding-top: 1.4rem;
        padding-bottom: 2rem;
    }
    [data-testid="stSidebar"] {
        border-right: 1px solid #dce2e8;
        min-width: 20rem !important;
        max-width: 20rem !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        width: 20rem !important;
    }
    [data-testid="stChatMessage"] {
        border: 1px solid #e0e5ea;
        border-radius: 6px;
        padding: 0.75rem 1rem;
        background: #ffffff;
    }
    [data-testid="stChatInput"] {
        border-color: #b8c4ce;
    }
    .db-status {
        display: flex;
        align-items: center;
        gap: 0.45rem;
        color: #43515e;
        font-size: 0.86rem;
        margin-bottom: 1rem;
    }
    .db-status-dot {
        width: 0.55rem;
        height: 0.55rem;
        border-radius: 50%;
        background: #16825d;
    }
    .stAppDeployButton {
        display: none;
    }
    [data-testid="stSidebar"] h1 {
        font-size: 1.7rem;
        line-height: 1.2;
    }
    [data-testid="stMain"] h1 {
        font-size: 2.25rem;
        line-height: 1.15;
    }
    [data-testid="stMain"] [data-testid="stButton"] button {
        min-height: 3.5rem;
    }
    h1, h2, h3 {
        letter-spacing: 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

TEXT = {
    "de": {
        "tagline": "Frag deine PostgreSQL-Datenbank in natürlicher Sprache.",
        "connected": "PostgreSQL verbunden · Nur Lesezugriff",
        "database": "Datenbank",
        "schema": "Schema",
        "refresh": "Aktualisieren",
        "schema_error": "Das Schema ist gerade nicht erreichbar.",
        "examples": "Beispielfragen",
        "clear": "Chat leeren",
        "input": "Frage zu Mitarbeitern, Abteilungen oder Projekten",
        "working": "Schema prüfen, SQL erstellen und Ergebnis verifizieren ...",
        "unauthorized": (
            "Die interne API-Authentifizierung ist nicht korrekt konfiguriert."
        ),
        "rate_limited": "Zu viele Anfragen. Bitte warte kurz und versuche es erneut.",
        "unavailable": "Der Datenbank-Agent ist noch nicht bereit.",
        "request_failed": "Die Anfrage konnte nicht verarbeitet werden.",
        "connection_failed": "Das Backend ist nicht erreichbar.",
        "table": "Tabelle",
        "chart": "Diagramm",
        "sql": "SQL",
        "download": "CSV herunterladen",
        "no_rows": "Die Abfrage hat keine Zeilen zurückgegeben.",
        "rows": "Zeilen",
        "truncated": "Ergebnis gekürzt",
        "examples_list": [
            "Wer verdient am meisten im Engineering?",
            "Wie hoch ist das durchschnittliche Gehalt pro Abteilung?",
            "Welche Projekte haben das höchste Budget?",
        ],
    },
    "en": {
        "tagline": "Ask your PostgreSQL database questions in plain language.",
        "connected": "PostgreSQL connected · Read-only access",
        "database": "Database",
        "schema": "Schema",
        "refresh": "Refresh",
        "schema_error": "The schema is currently unavailable.",
        "examples": "Example questions",
        "clear": "Clear chat",
        "input": "Ask about employees, departments, or projects",
        "working": "Inspecting the schema, writing SQL, and verifying the result ...",
        "unauthorized": "Internal API authentication is not configured correctly.",
        "rate_limited": "Too many requests. Wait briefly and try again.",
        "unavailable": "The database agent is not ready yet.",
        "request_failed": "The request could not be processed.",
        "connection_failed": "The backend is unavailable.",
        "table": "Table",
        "chart": "Chart",
        "sql": "SQL",
        "download": "Download CSV",
        "no_rows": "The query returned no rows.",
        "rows": "rows",
        "truncated": "Result truncated",
        "examples_list": [
            "Who earns the most in Engineering?",
            "What is the average salary by department?",
            "Which projects have the highest budget?",
        ],
    },
}

BACKEND_URL = os.environ.get("BACKEND_URL", "http://databridge_api:8000/api/v1/query")
BACKEND_SCHEMA_URL = os.environ.get(
    "BACKEND_SCHEMA_URL",
    BACKEND_URL.replace("/api/v1/query", "/api/v1/schema"),
)
APP_SECRET_TOKEN = os.environ.get("APP_SECRET_TOKEN")

if not APP_SECRET_TOKEN:
    st.error("APP_SECRET_TOKEN is not configured for the frontend service.")
    st.stop()


def api_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-API-Key": APP_SECRET_TOKEN,
    }


@st.cache_data(ttl=60)
def load_schema(refresh: bool = False) -> list[dict]:
    response = requests.get(
        BACKEND_SCHEMA_URL,
        headers=api_headers(),
        params={"refresh": refresh},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def execution_frame(execution: dict) -> pd.DataFrame:
    return pd.DataFrame(
        execution.get("rows", []),
        columns=execution.get("columns", []),
    )


def chart_columns(frame: pd.DataFrame) -> tuple[str, str] | None:
    if len(frame.index) < 2:
        return None
    numeric_columns = [
        column for column in frame.columns if is_numeric_dtype(frame[column])
    ]
    label_columns = [
        column for column in frame.columns if column not in numeric_columns
    ]
    if not numeric_columns or not label_columns:
        return None
    return label_columns[0], numeric_columns[0]


def render_execution(
    execution: dict,
    *,
    execution_index: int,
    message_index: int,
    labels: dict,
) -> None:
    row_count = execution.get("row_count", 0)
    row_label = f"{row_count} {labels['rows']}"
    if execution.get("truncated"):
        row_label += "+"
    duration = execution.get("duration_ms", 0)
    title = f"Query {execution_index} · {row_label} · {duration} ms"
    frame = execution_frame(execution)
    chart = chart_columns(frame)

    with st.expander(title):
        tab_names = [labels["table"]]
        if chart:
            tab_names.append(labels["chart"])
        tab_names.append(labels["sql"])
        tabs = st.tabs(tab_names)

        with tabs[0]:
            if frame.empty:
                st.info(labels["no_rows"])
            else:
                st.dataframe(frame, hide_index=True, width="stretch")
                st.download_button(
                    labels["download"],
                    data=rows_to_csv(
                        frame.columns,
                        frame.itertuples(index=False, name=None),
                    ),
                    file_name=f"databridge-query-{execution_index}.csv",
                    mime="text/csv",
                    key=f"download-{message_index}-{execution_index}",
                    icon=":material/download:",
                    on_click="ignore",
                )
            if execution.get("truncated"):
                st.caption(labels["truncated"])

        sql_tab_index = 2 if chart else 1
        if chart:
            with tabs[1]:
                label_column, value_column = chart
                st.bar_chart(
                    frame,
                    x=label_column,
                    y=value_column,
                    color="#0B7A75",
                    width="stretch",
                )

        with tabs[sql_tab_index]:
            st.code(execution.get("sql", ""), language="sql")


def render_assistant_message(message: dict, message_index: int, labels: dict) -> None:
    st.markdown(message["content"])
    for execution_index, execution in enumerate(message.get("executions", []), start=1):
        render_execution(
            execution,
            execution_index=execution_index,
            message_index=message_index,
            labels=labels,
        )
    if message.get("duration_ms"):
        st.caption(f"{message['duration_ms']} ms")


if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.title("DataBridge AI")
    language = st.segmented_control(
        "Language / Sprache",
        options=["de", "en"],
        default="de",
        format_func=lambda value: value.upper(),
        key="language",
        required=True,
        width="stretch",
    )
    labels = TEXT[language]
    st.caption(labels["tagline"])

    st.divider()
    database_heading, refresh_column = st.columns([3, 2])
    with database_heading:
        st.markdown(f"#### {labels['database']}")
    with refresh_column:
        refresh_schema = st.button(
            labels["refresh"],
            icon=":material/refresh:",
            help=labels["refresh"],
            type="tertiary",
            key="refresh-schema",
        )
    if refresh_schema:
        load_schema.clear()

    try:
        schema_tables = load_schema(refresh_schema)
        st.markdown(
            f"""
            <div class="db-status">
                <span class="db-status-dot"></span>
                <span>{labels["connected"]}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(f"#### {labels['schema']}")
        for table in schema_tables:
            with st.expander(table["name"]):
                lines = []
                for column in table["columns"]:
                    flags = (
                        f" ({', '.join(column['flags'])})" if column["flags"] else ""
                    )
                    nullable = "" if column["nullable"] else " NOT NULL"
                    lines.append(f"{column['name']} {column['type']}{flags}{nullable}")
                st.code("\n".join(lines))
    except requests.RequestException:
        st.warning(labels["schema_error"])

    st.divider()
    if st.button(
        labels["clear"],
        icon=":material/delete:",
        width="stretch",
        key="clear-chat",
    ):
        st.session_state.messages = []
        st.rerun()

st.title("DataBridge AI")
st.caption(labels["tagline"])

st.markdown(f"#### {labels['examples']}")
example_columns = st.columns(3)
selected_example = None
for index, question in enumerate(labels["examples_list"]):
    with example_columns[index]:
        if st.button(
            question,
            key=f"example-{language}-{index}",
            width="stretch",
        ):
            selected_example = question

for message_index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            render_assistant_message(message, message_index, labels)
        else:
            st.markdown(message["content"])

prompt = selected_example or st.chat_input(labels["input"])
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    history_lines = []
    for message in st.session_state.messages[:-1][-6:]:
        role = "User" if message["role"] == "user" else "Assistant"
        history_lines.append(f"{role}: {message['content']}")
    history = "\n".join(history_lines)[-4000:]

    with st.chat_message("assistant"), st.spinner(labels["working"]):
        try:
            response = requests.post(
                BACKEND_URL,
                json={
                    "question": prompt,
                    "chat_history": history,
                    "language": language,
                },
                headers=api_headers(),
                timeout=120,
            )
            if response.status_code == 200:
                payload = response.json()
                assistant_message = {
                    "role": "assistant",
                    "content": payload.get("answer", labels["request_failed"]),
                    "executions": payload.get("executions", []),
                    "duration_ms": payload.get("duration_ms", 0),
                }
                render_assistant_message(
                    assistant_message,
                    len(st.session_state.messages),
                    labels,
                )
                st.session_state.messages.append(assistant_message)
            elif response.status_code == 401:
                st.error(labels["unauthorized"])
            elif response.status_code == 429:
                st.warning(labels["rate_limited"])
            elif response.status_code == 503:
                st.warning(labels["unavailable"])
            else:
                st.error(labels["request_failed"])
        except requests.RequestException:
            st.error(labels["connection_failed"])
