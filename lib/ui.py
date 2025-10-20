"""Reusable UI widgets and helpers for the Streamlit app."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import streamlit as st


def run_with_status(label: str, runner: Callable[..., Any], *args, **kwargs) -> Any:
    """Run a callable while displaying a Streamlit status block."""
    with st.status(label, expanded=False) as status:
        try:
            status.update(label="Submitting…", state="running", expanded=True)
            result = runner(status, *args, **kwargs)
            status.update(label="Complete", state="complete", expanded=False)
            return result
        except Exception as exc:  # pragma: no cover - UI feedback path
            status.update(label=f"Failed: {exc}", state="error", expanded=True)
            raise


def job_status_badge(status_value: Optional[str]) -> str:
    """Return a short badge-like string for use inside DataFrames."""
    if not status_value:
        return "⚪️ Unknown"
    normalized = str(status_value).lower()
    mapping: Dict[str, str] = {
        "queued": "🟡 Queued",
        "in_progress": "🟡 In progress",
        "processing": "🟡 Processing",
        "pending": "🟡 Pending",
        "succeeded": "✅ Succeeded",
        "completed": "✅ Completed",
        "complete": "✅ Completed",
        "failed": "🔴 Failed",
        "canceled": "⚪️ Canceled",
        "cancelled": "⚪️ Canceled",
    }
    return mapping.get(normalized, f"🔘 {status_value}")


def disabled_button(label: str, *, disabled: bool, key: Optional[str] = None, help: Optional[str] = None):
    """Shorthand for rendering buttons that respect global busy state."""
    return st.button(label, key=key, disabled=disabled, help=help)


def toast_success(message: str) -> None:
    st.toast(message, icon="✅")


def toast_warning(message: str) -> None:
    st.toast(message, icon="⚠️")


def toast_error(message: str) -> None:
    st.toast(message, icon="🚫")
