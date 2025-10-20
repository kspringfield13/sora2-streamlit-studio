"""Create page: compose prompts and manage the current generation flow."""

from __future__ import annotations

import json
from typing import Dict, Optional

import streamlit as st

from lib.api import (
    create_video,
    download_video_bytes,
    extract_asset_url,
    get_openai_client,
    get_progress_percent,
    poll_until_complete,
    safe_get_id,
    to_dict,
)
from lib.state import (
    BALLOONS_KEY,
    VIDEO_HISTORY_KEY,
    cache_job,
    ensure_session_defaults,
    get_api_config,
    is_busy,
    set_busy,
    upsert_video_history,
)
from lib.ui import toast_error, toast_success, toast_warning


SIZE_PRESETS: Dict[str, str] = {
    "Landscape · 16:9 (1280x720)": "1280x720",
    "Portrait · 9:16 (720x1280)": "720x1280",
    "Square · 1:1 (1024x1024)": "1024x1024",
    "Vertical HD · 9:16 (1080x1920)": "1080x1920",
    "Wide HD · 16:9 (1920x1080)": "1920x1080",
}

MODELS = [
    "sora-2",
    "sora-2-pro",
]


def _ensure_create_defaults() -> None:
    defaults = {
        "create_prompt": "",
        "create_model": MODELS[0],
        "create_size_label": list(SIZE_PRESETS.keys())[0],
        "create_duration": 12,
        "create_last_job": None,
        "create_last_media_url": None,
        "create_last_media_bytes": None,
        "create_last_metadata": "",
        "create_validation_error": "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


_ensure_create_defaults()
ensure_session_defaults()

st.title("🎬 Prompt to Video")
st.write("Compose a prompt, tweak generation settings, and render high-quality video clips.")

cfg = get_api_config()


def _validate_inputs() -> Optional[str]:
    if not cfg.api_key:
        return "Add your OpenAI API key in the sidebar before generating."
    prompt_text = st.session_state.get("create_prompt", "").strip()
    if not prompt_text:
        return "Prompt cannot be empty."
    duration = int(st.session_state.get("create_duration", 0))
    if duration < 2 or duration > 25:
        return "Duration must be between 2 and 25 seconds."
    return None


output_container = st.container()
progress_placeholder = st.empty()


def _submit_generation() -> None:
    error = _validate_inputs()
    if error:
        st.session_state["create_validation_error"] = error
        toast_warning(error)
        return

    st.session_state["create_validation_error"] = ""
    set_busy(True)

    prompt_text = st.session_state.get("create_prompt", "").strip()

    size_label = st.session_state.get("create_size_label")
    size_value = SIZE_PRESETS.get(size_label, "1280x720")
    payload = {
        "prompt": prompt_text,
        "model": st.session_state.get("create_model"),
        "seconds": str(int(st.session_state.get("create_duration", 6))),
        "size": size_value,
    }

    image_file = st.session_state.get("create_image_ref")
    if image_file is not None:
        payload["input_reference"] = image_file

    client = get_openai_client(
        cfg.api_key,
        base_url=cfg.base_url,
    )

    try:
        with st.status("Submitting job…", expanded=False) as status:
            status.write("Sending payload to OpenAI Videos API.")
            job = create_video(client, payload)
            job_dict = to_dict(job)
            job_id = safe_get_id(job) or job_dict.get("id")
            if not job_id:
                raise RuntimeError(f"No video id returned from create(). Raw: {job_dict}")
            cache_job(job_dict)
            upsert_video_history(job_dict, prompt=prompt_text, source="generate")
            status.update(label="Queued…", state="running", expanded=True)

            progress_bar = progress_placeholder.progress(1, text="Queued…")

            def _on_tick(job_update: Dict[str, str]) -> None:
                job_copy = to_dict(job_update)
                cache_job(job_copy)
                upsert_video_history(job_copy, prompt=prompt_text, source="poll")
                pct_val = max(0, min(100, get_progress_percent(job_copy)))
                label = "Finalizing" if pct_val >= 99 else f"Rendering {pct_val}%"
                progress_bar.progress(max(pct_val, 1), text=label)
                status.update(label=f"{label}", state="running", expanded=True)

            status.write("Polling job status…")
            final_job = poll_until_complete(client, job_id, sleep_s=3, on_tick=_on_tick)
            final_dict = to_dict(final_job)
            cache_job(final_dict)
            upsert_video_history(final_dict, prompt=prompt_text, source="complete")
            progress_bar.progress(100, text="Ready")
            status.update(label="Ready", state="complete", expanded=True)

            status.write("Attempting to fetch rendered media…")
            media_url = extract_asset_url(final_dict)
            media_bytes = None
            if media_url:
                status.update(label="Ready", state="complete", expanded=False)
            else:
                progress_bar.progress(100, text="Downloading media…")
                try:
                    media_bytes = download_video_bytes(client, job_id)
                except Exception as download_err:  # pragma: no cover - network path
                    toast_error(f"Download failed: {download_err}")
                    status.update(label="Ready (download failed)", state="error", expanded=True)

        st.session_state["create_last_job"] = final_dict
        st.session_state["create_last_media_url"] = media_url
        st.session_state["create_last_media_bytes"] = media_bytes
        st.session_state["create_last_metadata"] = json.dumps(final_dict, indent=2)
        toast_success("Video ready!")
        if not st.session_state.get(BALLOONS_KEY):  # Celebrate first run only
            st.balloons()
            st.session_state[BALLOONS_KEY] = True

    except Exception as exc:  # pragma: no cover - API failure path
        st.session_state["create_validation_error"] = str(exc)
        toast_error(str(exc))
    finally:
        set_busy(False)
        progress_placeholder.empty()


# ---- Step 1: Compose prompt ----
with st.form("create_form"):
    st.text_area(
        "Prompt",
        key="create_prompt",
        height=160,
        placeholder="Describe the scene, motion, and style…",
    )

    col1, col2 = st.columns(2)
    with col1:
        st.selectbox("Model", MODELS, key="create_model")
        st.selectbox("Aspect & resolution", list(SIZE_PRESETS.keys()), key="create_size_label")
        st.slider("Duration (seconds)", 2, 25, key="create_duration")
    with col2:
        st.file_uploader(
            "Reference image (optional)",
            type=["png", "jpg", "jpeg"],
            key="create_image_ref",
        )

    st.form_submit_button(
        "Generate",
        type="primary",
        width="stretch",
        disabled=is_busy() or not cfg.api_key,
        on_click=_submit_generation,
    )


validation_error = st.session_state.get("create_validation_error")
if validation_error:
    st.error(validation_error)

st.divider()

# ---- Step 2: Review result ----
last_job = st.session_state.get("create_last_job")

if not last_job:
    st.info("Submit a prompt to see job details and download options here.")
else:
    job_id = last_job.get("id", "unknown")
    status_text = last_job.get("status", "unknown")
    st.markdown(f"**Job ID:** `{job_id}`")
    st.write(f"Status: {status_text}")
    meta_cols = st.columns(3)
    meta_cols[0].metric("Resolution", last_job.get("size", "—"))
    meta_cols[1].metric("Duration", f"{last_job.get('seconds', '—')}s")
    meta_cols[2].metric("Model", last_job.get("model", "—"))

    media_url = st.session_state.get("create_last_media_url")
    media_bytes = st.session_state.get("create_last_media_bytes")
    if media_url:
        st.video(media_url)
    elif media_bytes:
        st.video(media_bytes)
    else:
        st.warning("Media preview unavailable. Try downloading the MP4 below.")

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        if media_bytes:
            st.download_button(
                "Download MP4",
                data=media_bytes,
                file_name=f"{job_id}.mp4",
                mime="video/mp4",
                width="stretch",
            )
        elif media_url:
            st.markdown(
                f"[Download MP4]({media_url})",
                help="Opens the asset URL in a new tab.",
            )
        else:
            st.button("Download MP4", disabled=True, width="stretch")
    with col_dl2:
        st.download_button(
            "Download metadata JSON",
            data=st.session_state.get("create_last_metadata", "{}"),
            file_name=f"{job_id}.json",
            mime="application/json",
            width="stretch",
        )

    history = st.session_state.get(VIDEO_HISTORY_KEY, [])[:5]
    if history:
        st.markdown("#### Recent jobs this session")
        for entry in history:
            st.write(f"• `{entry.get('id')}` · {entry.get('status')} · {entry.get('size', '—')} · {entry.get('seconds', '—')}s")
