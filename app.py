from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path

import httpx
import streamlit as st

from ui_contract import API_PATHS, current_conversation_id, load_personas, select_persona, start_new_conversation
from ui_format import (
    WIB,
    alert_rows,
    confirmation_message,
    error_message,
    example_questions,
    leave_request_rows,
    outcome_label,
    proposal_markdown,
    technical_details,
)


API_URL = os.getenv("API_URL", "http://localhost:8000")


def request(method: str, path: str, token: str, **kwargs):
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = httpx.request(method, f"{API_URL}{path}", headers=headers, timeout=40, **kwargs)
    except httpx.HTTPError:  # API down or too slow: a message instead of a stack trace
        st.error("API tidak bisa dihubungi. Pastikan layanan API berjalan, lalu coba lagi.")
        return None
    if response.is_error:
        detail = response.json().get("detail", response.text)
        st.error(error_message(response.status_code, detail))
        return None
    return response.json()


st.set_page_config(page_title="Asisten HR Nusantara Digital", page_icon="🧭", layout="wide")
st.title("Asisten Kebijakan HR dan Cuti")
st.caption("Data dan token pada aplikasi ini sepenuhnya sintetis untuk kebutuhan pembelajaran.")

personas = load_personas(Path(__file__).with_name("demo_personas.json"))
team_personas = Path(__file__).with_name("demo_personas_team.json")
if team_personas.exists():  # optional manager personas; without the file the UI is exactly the original
    personas += load_personas(team_personas)
persona = st.sidebar.selectbox("Persona demo", personas, format_func=lambda item: item["label"])
select_persona(st.session_state, persona)
st.sidebar.caption(persona["scenario"])
if st.sidebar.button(
    "Percakapan baru",
    help="Mulai percakapan baru: memori singkat dan draf tiket yang belum dikirim tidak ikut terbawa.",
):
    start_new_conversation(st.session_state)
token = persona["demo_token"]

# Ready-made questions for the demo. A click sends the question exactly as if it were typed.
picked = None
examples = example_questions(persona["employee_id"], datetime.now(WIB).date())
if examples:
    st.sidebar.markdown("**Coba tanyakan**")
    for number, example in enumerate(examples):
        if st.sidebar.button(example, key=f"example_{persona['employee_id']}_{number}"):
            picked = example


def show_proposal(turn: dict, proposal: dict) -> None:
    """Nothing is created until Konfirmasi; after it, the result replaces the button."""
    confirmed = turn.get("confirmation")
    if not confirmed:
        st.warning("Pengajuan cuti belum dibuat. Periksa detail di bawah, lalu tekan Konfirmasi.")
    st.markdown(proposal_markdown(proposal))
    with st.expander("Data proposal (JSON)"):
        st.json(proposal)
    if confirmed:
        st.success(confirmation_message(confirmed))
        return
    key_name = f"idem_{proposal['proposal_id']}"
    st.session_state.setdefault(key_name, str(uuid.uuid4()))
    if st.button("Konfirmasi pembuatan permintaan pending", key=proposal["proposal_id"]):
        result = request(
            "POST",
            API_PATHS["confirm"].format(proposal_id=proposal["proposal_id"]),
            token,
            json={"idempotency_key": st.session_state[key_name]},
        )
        if result:
            turn["confirmation"] = result
            st.rerun()


def show_turn(turn: dict) -> None:
    """One question and the API's answer: answer, sources, proposal, then the technical details."""
    result = turn["response"]
    with st.chat_message("user"):
        st.markdown(turn["question"])
    with st.chat_message("assistant"):
        st.markdown(result["answer"])
        if result["citations"]:
            with st.expander("Sumber kebijakan"):
                for citation in result["citations"]:
                    st.markdown(f"**{citation['document_id']} — {citation['section']}**")
                    st.write(citation["excerpt"])
        if result.get("action_proposal"):
            show_proposal(turn, result["action_proposal"])
        with st.expander(f"Detail teknis · {outcome_label(result['outcome'])}"):
            st.caption(technical_details(result))


chat_tab, leave_tab, monitor_tab = st.tabs(["Percakapan", "Permintaan Cuti", "Monitoring"])

with chat_tab:
    # The API remembers the last messages of this conversation, so the page shows them too.
    history = st.session_state.setdefault("chat_history", [])
    if not history:
        st.caption("Tulis pertanyaan di bawah, atau pilih contoh di sidebar.")
    for turn in history:
        show_turn(turn)
    waiting = st.container()  # the question being answered shows above the input box, not below it
    typed = st.chat_input("Pertanyaan atau permintaan, misalnya: Berapa saldo cuti saya?", max_chars=4000)
    question = typed or picked
    if question:
        with waiting, st.chat_message("user"):
            st.markdown(question)
        with waiting, st.chat_message("assistant"), st.spinner("Asisten sedang menjawab..."):
            result = request(
                "POST", API_PATHS["chat"], token,
                json={"message": question, "conversation_id": current_conversation_id(st.session_state)},
            )
        if result:
            history.append({"question": question, "response": result})
            st.rerun()

with leave_tab:
    if st.button("Muat permintaan saya"):
        data = request("GET", API_PATHS["my_requests"], token)
        if data:
            st.dataframe(leave_request_rows(data), hide_index=True, use_container_width=True)
        elif data is not None:
            st.info("Belum ada permintaan cuti.")

with monitor_tab:
    st.info("Gunakan token monitoring admin untuk membuka metrik dan alert agregat.")
    if st.button("Muat monitoring"):
        summary = request("GET", API_PATHS["monitoring_summary"], token)
        # Same access rule for both: after a refused summary, the alerts would only repeat the 403.
        alerts = request("GET", API_PATHS["monitoring_alerts"], token) if summary else None
        if summary:
            columns = st.columns(4)
            columns[0].metric("Runs", summary["run_count"])
            columns[1].metric("Error rate", f"{float(summary['error_rate']):.1%}")
            columns[2].metric("p95 latency", f"{int(summary['p95_latency_ms'])} ms")
            columns[3].metric("Tool calls", summary["tool_calls"])
        if alerts is not None:
            st.subheader("Alert aktif")
            if alerts:
                st.dataframe(alert_rows(alerts), hide_index=True, use_container_width=True)
            else:
                st.success("Tidak ada alert aktif.")
