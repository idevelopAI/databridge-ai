import os
from html import escape
from pathlib import Path
from uuid import uuid4

import pandas as pd
import requests
import streamlit as st
from pandas.api.types import is_numeric_dtype

from csv_export import rows_to_csv

st.set_page_config(
    page_title="DataBridge AI",
    page_icon=":material/database:",
    layout="wide",
    initial_sidebar_state="auto",
)
stylesheet = Path(__file__).with_name("frontend") / "styles.css"
st.html(f"<style>{stylesheet.read_text()}</style>")

TEXT = {
    "en": {
        "workspace": "Workspace",
        "ask": "Ask DataBridge",
        "schema": "Database schema",
        "new": "New chat",
        "popular": "Suggested questions",
        "recent": "Recent chats",
        "no_chats": "No conversations yet",
        "session": "This session",
        "connected": "Connected",
        "offline": "Unavailable",
        "readonly": "Read-only",
        "database": "Database",
        "tables": "tables",
        "columns": "columns",
        "refresh": "Refresh schema",
        "search": "Find a table",
        "no_tables": "No matching tables",
        "schema_error": "The database schema is unavailable.",
        "input": "Ask a question about your data...",
        "reply": "Your clarification...",
        "working": "Querying the database...",
        "welcome": "A new conversation with your data.",
        "empty": "No query results yet",
        "you": "You",
        "result": "Query result",
        "table": "Table",
        "chart": "Chart",
        "sql": "SQL",
        "download": "Download CSV",
        "no_rows": "This query returned no rows.",
        "rows": "rows",
        "truncated": "Result limit reached",
        "correct": "Mark correct",
        "incorrect": "Mark incorrect",
        "feedback_saved": "Feedback saved",
        "feedback_failed": "Feedback could not be saved.",
        "export_feedback": "Export feedback",
        "details": "Query details",
        "clarify": "Clarification needed",
        "rejected": "Request declined",
        "recorded": "Recorded demo",
        "live": "Live",
        "unauthorized": "The internal API authentication is not configured correctly.",
        "rate_limited": "Too many requests. Wait a moment and try again.",
        "unavailable": "The database agent is not ready yet.",
        "request_failed": "The request could not be completed. Please try again.",
        "invalid_question": "Enter a question between 1 and 1,000 characters.",
        "no_result": "No verified database result was returned.",
        "restricted": "This request includes data blocked by the privacy policy.",
        "unsafe": "Database modifications are not allowed.",
        "connection_failed": "The backend is unavailable. Please try again.",
        "examples": [
            "Which projects have the highest budget?",
            "What is the average annual gross salary by department?",
            "Who earns the most in Engineering?",
        ],
    },
    "de": {
        "workspace": "Arbeitsbereich",
        "ask": "DataBridge fragen",
        "schema": "Datenbankschema",
        "new": "Neuer Chat",
        "popular": "Beispielfragen",
        "recent": "Letzte Chats",
        "no_chats": "Noch keine Unterhaltungen",
        "session": "Diese Sitzung",
        "connected": "Verbunden",
        "offline": "Nicht erreichbar",
        "readonly": "Nur Lesezugriff",
        "database": "Datenbank",
        "tables": "Tabellen",
        "columns": "Spalten",
        "refresh": "Schema aktualisieren",
        "search": "Tabelle suchen",
        "no_tables": "Keine passenden Tabellen",
        "schema_error": "Das Datenbankschema ist nicht erreichbar.",
        "input": "Stelle eine Frage zu deinen Daten...",
        "reply": "Deine Präzisierung...",
        "working": "Datenbank wird abgefragt...",
        "welcome": "Eine neue Unterhaltung mit deinen Daten.",
        "empty": "Noch keine Abfrageergebnisse",
        "you": "Du",
        "result": "Abfrageergebnis",
        "table": "Tabelle",
        "chart": "Diagramm",
        "sql": "SQL",
        "download": "CSV herunterladen",
        "no_rows": "Diese Abfrage hat keine Zeilen zurückgegeben.",
        "rows": "Zeilen",
        "truncated": "Ergebnislimit erreicht",
        "correct": "Als korrekt bewerten",
        "incorrect": "Als falsch bewerten",
        "feedback_saved": "Feedback gespeichert",
        "feedback_failed": "Feedback konnte nicht gespeichert werden.",
        "export_feedback": "Feedback exportieren",
        "details": "Abfragedetails",
        "clarify": "Rückfrage",
        "rejected": "Anfrage abgelehnt",
        "recorded": "Aufgezeichnete Demo",
        "live": "Live",
        "unauthorized": "Die interne API-Authentifizierung ist falsch konfiguriert.",
        "rate_limited": "Zu viele Anfragen. Bitte warte kurz und versuche es erneut.",
        "unavailable": "Der Datenbank-Agent ist noch nicht bereit.",
        "request_failed": "Die Anfrage ist fehlgeschlagen. Bitte erneut versuchen.",
        "invalid_question": "Bitte gib eine Frage mit 1 bis 1.000 Zeichen ein.",
        "no_result": "Es wurde kein verifiziertes Datenbankergebnis zurückgegeben.",
        "restricted": "Die Datenschutzrichtlinie sperrt die angefragten Daten.",
        "unsafe": "Datenbankänderungen sind nicht erlaubt.",
        "connection_failed": "Das Backend ist nicht erreichbar.",
        "examples": [
            "Welche Projekte haben das höchste Budget?",
            "Wie hoch ist das durchschnittliche Bruttojahresgehalt pro Abteilung?",
            "Wer verdient am meisten im Engineering?",
        ],
    },
}

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000/api/v1/query")
BACKEND_SCHEMA_URL = os.environ.get(
    "BACKEND_SCHEMA_URL", BACKEND_URL.replace("/api/v1/query", "/api/v1/schema")
)
BACKEND_FEEDBACK_URL = os.environ.get(
    "BACKEND_FEEDBACK_URL", BACKEND_URL.replace("/api/v1/query", "/api/v1/feedback")
)
APP_SECRET_TOKEN = os.environ.get("APP_SECRET_TOKEN")
APP_MODE = os.environ.get("APP_MODE", "live").strip().casefold()

if not APP_SECRET_TOKEN:
    st.error("APP_SECRET_TOKEN is not configured for the frontend service.")
    st.stop()


def api_headers() -> dict[str, str]:
    return {"Content-Type": "application/json", "X-API-Key": APP_SECRET_TOKEN}


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


def new_conversation() -> None:
    conversation_id = uuid4().hex
    st.session_state.conversations[conversation_id] = {"messages": [], "title": ""}
    st.session_state.active_conversation = conversation_id
    # Keep conversation content in this browser session, with bounded memory.
    while len(st.session_state.conversations) > 12:
        oldest = next(iter(st.session_state.conversations))
        del st.session_state.conversations[oldest]


def chart_columns(frame: pd.DataFrame) -> tuple[str, str] | None:
    if len(frame.index) < 2:
        return None
    numeric = [column for column in frame.columns if is_numeric_dtype(frame[column])]
    labels = [column for column in frame.columns if column not in numeric]
    return (labels[0], numeric[0]) if labels and numeric else None


def submit_query_feedback(question: str, generated_sql: str, rating: str) -> None:
    response = requests.post(
        BACKEND_FEEDBACK_URL,
        json={"question": question, "generated_sql": generated_sql, "feedback": rating},
        headers=api_headers(),
        timeout=10,
    )
    response.raise_for_status()


def render_execution(execution: dict, message_index: int, execution_index: int) -> None:
    frame = pd.DataFrame(
        execution.get("rows", []), columns=execution.get("columns", [])
    )
    chart = chart_columns(frame)
    rows = int(execution.get("row_count", len(frame)))
    duration = float(execution.get("duration_ms", 0))
    st.markdown(
        f'<div class="db-result-heading"><strong>{labels["result"]}</strong>'
        f"<span>{rows} {labels['rows']} &middot; {duration:g} ms</span></div>",
        unsafe_allow_html=True,
    )
    names = [f":material/table: {labels['table']}"]
    if chart:
        names.append(f":material/bar_chart: {labels['chart']}")
    names.append(":material/code: SQL")
    tabs = st.tabs(names)
    with tabs[0]:
        if frame.empty:
            st.info(labels["no_rows"])
        else:
            st.dataframe(frame, hide_index=True, width="stretch")
    if chart:
        with tabs[1]:
            label_column, value_column = chart
            st.bar_chart(
                frame,
                x=label_column,
                y=value_column,
                horizontal=True,
                color="#438b70",
                height=280,
                width="stretch",
            )
    with tabs[-1]:
        st.code(execution.get("sql", ""), language="sql")
    with st.container(horizontal=True, vertical_alignment="center"):
        st.download_button(
            labels["download"],
            data=rows_to_csv(frame.columns, frame.itertuples(index=False, name=None)),
            file_name=f"databridge-query-{execution_index}.csv",
            mime="text/csv",
            key=f"download-{st.session_state.active_conversation}-{message_index}-{execution_index}",
            icon=":material/download:",
            type="tertiary",
            on_click="ignore",
        )
        if execution.get("truncated"):
            st.caption(labels["truncated"])


def render_feedback(message: dict, message_index: int) -> None:
    executions = message.get("executions", [])
    if not executions or not message.get("question"):
        return
    if message.get("feedback"):
        st.caption(f":material/check: {labels['feedback_saved']}")
        return
    with st.container(horizontal=True, vertical_alignment="center"):
        rating = None
        for value, icon, help_text in (
            ("correct", "thumb_up", labels["correct"]),
            ("incorrect", "thumb_down", labels["incorrect"]),
        ):
            if st.button(
                "",
                icon=f":material/{icon}:",
                help=help_text,
                type="tertiary",
                key=f"feedback-{value}-{st.session_state.active_conversation}-{message_index}",
            ):
                rating = value
        if rating:
            try:
                submit_query_feedback(
                    message["question"], executions[-1]["sql"], rating
                )
                message["feedback"] = rating
                st.rerun()
            except requests.RequestException:
                st.warning(labels["feedback_failed"])
        with st.popover("", icon=":material/info:", help=labels["details"]):
            st.caption(labels["details"])
            for name in (
                "duration_ms",
                "model_duration_ms",
                "tool_call_count",
                "input_tokens",
                "output_tokens",
                "request_id",
            ):
                if message.get(name) is not None:
                    st.text(f"{name}: {message[name]}")


def render_message(message: dict, index: int) -> None:
    is_user = message["role"] == "user"
    avatar = None if is_user else ":material/auto_awesome:"
    with st.chat_message(message["role"], avatar=avatar):
        name = labels["you"] if is_user else "DataBridge AI"
        st.markdown(
            f'<div class="db-message-label">{name}</div>', unsafe_allow_html=True
        )
        if message.get("status") == "clarification_required":
            st.caption(f":material/help: {labels['clarify']}")
        if message.get("status") == "error":
            st.warning(message["content"])
        else:
            st.markdown(message["content"])
        for execution_index, execution in enumerate(message.get("executions", []), 1):
            render_execution(execution, index, execution_index)
        render_feedback(message, index)


def request_answer(prompt: str, conversation: dict) -> None:
    messages = conversation["messages"]
    user_message = {"role": "user", "content": prompt, "accepted_for_context": False}
    history = [
        f"{'User' if item['role'] == 'user' else 'Assistant'}: {item['content']}"
        for item in messages[-6:]
        if item.get("accepted_for_context", False)
    ]
    messages.append(user_message)
    if not conversation["title"]:
        conversation["title"] = prompt
    answer = {"role": "assistant", "status": "error", "accepted_for_context": False}
    try:
        response = requests.post(
            BACKEND_URL,
            json={
                "question": prompt,
                "chat_history": "\n".join(history)[-4000:],
                "language": language,
            },
            headers=api_headers(),
            timeout=120,
        )
        if response.status_code == 200:
            payload = response.json()
            user_message["accepted_for_context"] = True
            answer.update(
                content=payload.get("answer", labels["request_failed"]),
                status=payload.get("status", "answered"),
                accepted_for_context=True,
                question=prompt,
                executions=payload.get("executions", []),
            )
            for field in (
                "duration_ms",
                "model_duration_ms",
                "tool_call_count",
                "input_tokens",
                "output_tokens",
                "request_id",
            ):
                if field in payload:
                    answer[field] = payload[field]
        else:
            error_key = {
                401: "unauthorized",
                422: "invalid_question",
                429: "rate_limited",
                502: "no_result",
                503: "unavailable",
            }.get(response.status_code, "request_failed")
            if response.status_code == 403:
                try:
                    detail = str(response.json().get("detail", "")).casefold()
                except requests.JSONDecodeError:
                    detail = ""
                error_key = (
                    "unsafe"
                    if "modification" in detail or "änderung" in detail
                    else "restricted"
                )
            answer["content"] = labels[error_key]
    except (requests.RequestException, ValueError):
        answer["content"] = labels["connection_failed"]
    messages.append(answer)


def render_schema(tables: list[dict]) -> None:
    search = st.text_input(
        labels["search"],
        placeholder=labels["search"],
        icon=":material/search:",
        label_visibility="collapsed",
        key="schema-search",
    ).casefold()
    selected = [table for table in tables if search in table["name"].casefold()]
    if not selected:
        st.info(labels["no_tables"])
    for table in selected:
        columns = table.get("columns", [])
        with st.expander(
            f"{table.get('schema', 'public')}.{table['name']}"
            f" · {len(columns)} {labels['columns']}",
            expanded=len(selected) == 1,
            icon=":material/table:",
        ):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Column": column["name"],
                            "Type": column["type"],
                            "Key": ", ".join(column.get("flags", [])),
                            "Nullable": column.get("nullable", True),
                        }
                        for column in columns
                    ]
                ),
                hide_index=True,
                width="stretch",
            )


if "conversations" not in st.session_state:
    st.session_state.conversations = {}
    new_conversation()
if "view" not in st.session_state:
    st.session_state.view = "chat"

with st.sidebar:
    st.markdown(
        '<div class="db-brand">DataBridge<span> AI</span></div>'
        '<div class="db-brand-sub">POSTGRESQL WORKSPACE</div>',
        unsafe_allow_html=True,
    )
    language = st.segmented_control(
        "Language / Sprache",
        options=["de", "en"],
        default="de",
        format_func=str.upper,
        key="language",
        required=True,
        width="stretch",
        label_visibility="collapsed",
    )
    labels = TEXT[language]
    st.space("small")
    for view, title, icon in (
        ("chat", labels["ask"], "chat_bubble_outline"),
        ("schema", labels["schema"], "table_view"),
    ):
        if st.button(
            title,
            icon=f":material/{icon}:",
            key=f"nav-{view}",
            type="primary" if st.session_state.view == view else "tertiary",
            width="stretch",
        ):
            st.session_state.view = view
            st.rerun()
    if st.button(labels["new"], icon=":material/add:", key="new-chat", width="stretch"):
        new_conversation()
        st.session_state.view = "chat"
        st.rerun()
    st.divider()
    with st.container(key="recent-chats"):
        st.caption(labels["recent"])
        recent = [
            (key, value)
            for key, value in st.session_state.conversations.items()
            if value["title"]
        ]
        if not recent:
            st.caption(labels["no_chats"])
        for conversation_id, item in reversed(recent):
            if st.button(
                item["title"],
                help=item["title"],
                key=f"conversation-{conversation_id}",
                type="secondary"
                if conversation_id == st.session_state.active_conversation
                else "tertiary",
                width="stretch",
            ):
                st.session_state.active_conversation = conversation_id
                st.session_state.view = "chat"
                st.rerun()
    st.divider()
    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption(labels["database"])
        refresh = st.button(
            "",
            icon=":material/refresh:",
            help=labels["refresh"],
            key="refresh-schema",
            type="tertiary",
        )
    if refresh:
        load_schema.clear()
    try:
        schema_tables = load_schema(refresh)
        connected = True
    except (requests.RequestException, ValueError):
        schema_tables = []
        connected = False
    connection_state = labels["connected"] if connected else labels["offline"]
    connection_class = "db-connected" if connected else "db-offline"
    st.markdown(
        '<div class="db-connection"><strong>PostgreSQL</strong>'
        f'<div class="{connection_class}">{connection_state}</div>'
        f"<div>{labels['readonly']} &middot; "
        f"{len(schema_tables)} {labels['tables']}</div></div>",
        unsafe_allow_html=True,
    )
    st.divider()
    if st.button(
        labels["export_feedback"],
        icon=":material/download:",
        key="prepare-feedback",
        type="tertiary",
        width="stretch",
    ):
        try:
            response = requests.get(
                f"{BACKEND_FEEDBACK_URL}/export",
                headers=api_headers(),
                timeout=10,
            )
            response.raise_for_status()
            st.session_state.feedback_export = response.content
        except requests.RequestException:
            st.warning(labels["feedback_failed"])
    if "feedback_export" in st.session_state:
        st.download_button(
            "JSONL",
            data=st.session_state.feedback_export,
            file_name="databridge-reviewed-examples.jsonl",
            mime="application/x-ndjson",
            icon=":material/download:",
            on_click="ignore",
            key="export-feedback",
        )
    st.caption(labels["recorded"] if APP_MODE == "recorded" else "Gemini")

mode = labels["recorded"] if APP_MODE == "recorded" else labels["live"]
view_title = labels["ask"] if st.session_state.view == "chat" else labels["schema"]
st.markdown(
    f'<div class="db-heading"><h1>{view_title}</h1>'
    f'<span class="db-mode">{mode}</span></div>',
    unsafe_allow_html=True,
)
if not connected:
    st.warning(labels["schema_error"])

if st.session_state.view == "schema":
    render_schema(schema_tables)
else:
    selected_example = None
    conversation = st.session_state.conversations[st.session_state.active_conversation]
    messages = conversation["messages"]
    with st.container(key="chat-surface", border=True):
        title = conversation["title"] or labels["new"]
        st.markdown(
            f'<div class="db-chat-title">{escape(title)}</div>',
            unsafe_allow_html=True,
        )
        with st.container(height=500, border=False, key="chat-log", autoscroll=True):
            if not messages:
                st.markdown(
                    f'<div class="db-empty"><span class="db-empty-mark">DB</span>'
                    f"<h2>{labels['welcome']}</h2><p>{labels['empty']}</p></div>",
                    unsafe_allow_html=True,
                )
                with st.container(key="suggestions"):
                    for index, question in enumerate(labels["examples"]):
                        if st.button(
                            question,
                            key=f"example-{index}",
                            type="tertiary",
                            icon=":material/arrow_outward:",
                            width="stretch",
                        ):
                            selected_example = question
            for index, message in enumerate(messages):
                render_message(message, index)
            if selected_example:
                with st.spinner(labels["working"]):
                    request_answer(selected_example, conversation)
                st.rerun()
        is_clarification = (
            messages and messages[-1].get("status") == "clarification_required"
        )
        prompt = st.chat_input(
            labels["reply"] if is_clarification else labels["input"],
            key=f"composer-{st.session_state.active_conversation}",
            max_chars=1000,
        )
        if prompt:
            with st.spinner(labels["working"]):
                request_answer(prompt, conversation)
            st.rerun()
