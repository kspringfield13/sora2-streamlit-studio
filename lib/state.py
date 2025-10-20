"""Session state helpers and cache utilities for the Streamlit app."""

from __future__ import annotations

import time
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

import streamlit as st
from collections.abc import Mapping
from dotenv import load_dotenv

from lib.api import to_dict


# Session keys
VIDEO_HISTORY_KEY = "video_history"
JOBS_CACHE_KEY = "jobs_cache"
JOBS_CURSOR_KEY = "jobs_cursor"
JOBS_HAS_MORE_KEY = "jobs_has_more"
BUSY_KEY = "busy"
BALLOONS_KEY = "celebrated_first_render"
API_CFG_KEY = "api_config"
POLLING_KEY = "job_polling"
SELECTED_JOB_KEY = "selected_job_id"


@dataclass
class ApiConfig:
    api_key: str
    base_url: Optional[str] = None


def ensure_session_defaults() -> None:
    # Load environment variables from .env once per session init.
    if not st.session_state.get("_env_loaded", False):
        load_dotenv()
        st.session_state["_env_loaded"] = True

    state = st.session_state
    state.setdefault(VIDEO_HISTORY_KEY, [])
    state.setdefault(JOBS_CACHE_KEY, {})
    state.setdefault(JOBS_CURSOR_KEY, None)
    state.setdefault(JOBS_HAS_MORE_KEY, False)
    state.setdefault(BUSY_KEY, False)
    state.setdefault(BALLOONS_KEY, False)
    state.setdefault(API_CFG_KEY, {})
    state.setdefault(POLLING_KEY, {})
    state.setdefault(SELECTED_JOB_KEY, None)

    if not state.get(API_CFG_KEY):
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL") or None
        state[API_CFG_KEY] = {
            "api_key": api_key,
            "base_url": base_url,
        }


def set_busy(value: bool) -> None:
    st.session_state[BUSY_KEY] = value


def is_busy() -> bool:
    return bool(st.session_state.get(BUSY_KEY))


def update_api_config(**kwargs: Any) -> None:
    cfg = st.session_state.get(API_CFG_KEY, {}).copy()
    for key, value in kwargs.items():
        if value is None:
            cfg.pop(key, None)
        else:
            cfg[key] = value
    st.session_state[API_CFG_KEY] = cfg


def get_api_config() -> ApiConfig:
    cfg = st.session_state.get(API_CFG_KEY, {})
    return ApiConfig(
        api_key=cfg.get("api_key", ""),
        base_url=cfg.get("base_url"),
    )


def cache_job(job_dict: Dict[str, Any]) -> None:
    job_id = job_dict.get("id")
    if not job_id:
        return
    store = st.session_state.setdefault(JOBS_CACHE_KEY, {})
    store[job_id] = job_dict


def get_cached_job(job_id: str) -> Optional[Dict[str, Any]]:
    store = st.session_state.get(JOBS_CACHE_KEY, {})
    return store.get(job_id)


# =========================
# Legacy helper functions (kept)
# =========================

def upsert_video_history(job: Union[Mapping, dict], *, prompt: Optional[str] = None, source: str = "create") -> None:
    """Store or update a video entry in session history (newest first)."""
    job_dict = to_dict(job)
    vid = job_dict.get("id")
    if not vid:
        return

    prompt_text = prompt or job_dict.get("prompt") or ""
    prompt_snippet = " ".join(str(prompt_text).split())
    if len(prompt_snippet) > 80:
        prompt_snippet = f"{prompt_snippet[:77]}…"

    entry = {
        "id": str(vid),
        "prompt": prompt_snippet,
        "status": job_dict.get("status"),
        "seconds": job_dict.get("seconds") or job_dict.get("duration"),
        "size": job_dict.get("size") or job_dict.get("resolution"),
        "source": source,
        "updated_at": job_dict.get("updated_at")
        or job_dict.get("created_at")
        or job_dict.get("created"),
    }

    history = [
        existing
        for existing in st.session_state.get(VIDEO_HISTORY_KEY, [])
        if existing.get("id") != entry["id"]
    ]
    history.insert(0, entry)
    st.session_state[VIDEO_HISTORY_KEY] = history[:20]  # keep recent set manageable


def remove_video_from_history(video_id: str) -> None:
    """Remove a video entry from session history if it exists."""
    st.session_state[VIDEO_HISTORY_KEY] = [
        entry for entry in st.session_state.get(VIDEO_HISTORY_KEY, []) if entry.get("id") != video_id
    ]


def describe_video_entry(entry: Dict[str, Any]) -> str:
    """Produce a short label for select widgets."""
    prompt = entry.get("prompt") or ""
    size = entry.get("size")
    seconds = entry.get("seconds")
    bits = [entry.get("id") or "unknown"]
    if size:
        bits.append(str(size))
    if seconds:
        bits.append(f"{seconds}s")
    if prompt:
        bits.append(prompt)
    return " • ".join(filter(None, bits))


def format_ts(ts: Optional[int]) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ts)))
    except Exception:
        return "-"
