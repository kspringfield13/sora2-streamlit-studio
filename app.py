"""Streamlit entrypoint with navigation for the prompt-to-video generator."""

from __future__ import annotations

import streamlit as st

from lib.state import ensure_session_defaults, get_api_config


st.set_page_config(
    page_title="Sora 2 – Prompt to Video",
    page_icon="🎬",
    layout="centered",
    initial_sidebar_state="expanded",
)

ensure_session_defaults()

with st.sidebar:
    st.caption("OpenAI credentials are loaded from environment variables.")
    st.markdown(
        "Set `OPENAI_API_KEY` (and optional `OPENAI_BASE_URL`) in a `.env` file before running the app."
    )

cfg = get_api_config()
st.session_state["has_api_key"] = bool(cfg.api_key)

create = st.Page("pages/create.py", title="Create", icon="🎬")
jobs = st.Page("pages/jobs.py", title="Jobs", icon="📼")

pg = st.navigation([create, jobs])
pg.run()
