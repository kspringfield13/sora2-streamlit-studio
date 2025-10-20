"""Jobs page: browse, filter, and manage video render jobs."""

from __future__ import annotations

import datetime as dt
import json
from typing import Dict, List

import pandas as pd
import streamlit as st

from lib.api import (
    delete_video,
    download_video_bytes,
    extract_asset_url,
    get_openai_client,
    get_progress_percent,
    get_video,
    list_videos,
    poll_until_complete,
    to_dict,
)
from lib.state import (
    JOBS_HAS_MORE_KEY,
    VIDEO_HISTORY_KEY,
    cache_job,
    ensure_session_defaults,
    get_api_config,
    is_busy,
    remove_video_from_history,
    set_busy,
    upsert_video_history,
)
from lib.state import format_ts
from lib.ui import job_status_badge, toast_error, toast_success


ensure_session_defaults()

st.title("📼 My Jobs")
st.write("Monitor render progress, download outputs, and manage your video jobs.")

cfg = get_api_config()

if not cfg.api_key:
    st.stop()


def _ensure_jobs_defaults() -> None:
    defaults = {
        "jobs_rows": [],
        "jobs_next_after": None,
        "jobs_last_error": "",
        "jobs_status_filter": "All",
        "jobs_use_date_filter": False,
        "jobs_date_start": None,
        "jobs_date_end": None,
        "jobs_selected_id": None,
        "jobs_selected_job": None,
        "jobs_selected_media_url": None,
        "jobs_selected_media_bytes": None,
        "jobs_pending_delete": None,
        "jobs_download_payload": None,
        "jobs_loaded_once": False,
        "jobs_last_filters": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


_ensure_jobs_defaults()


def _get_client():
    return get_openai_client(
        cfg.api_key,
        base_url=cfg.base_url,
    )


STATUS_OPTIONS = ["All", "In-progress", "Completed", "Failed"]
STATUS_TO_API = {
    "All": None,
    "In-progress": "in_progress",
    "Completed": "completed",
    "Failed": "failed",
}


with st.container():
    filter_cols = st.columns([2, 2, 2, 1])
    with filter_cols[0]:
        st.selectbox(
            "Status",
            STATUS_OPTIONS,
            key="jobs_status_filter",
        )
    with filter_cols[1]:
        st.checkbox("Filter by date range", key="jobs_use_date_filter")
        if st.session_state.get("jobs_use_date_filter"):
            default_start = st.session_state.get("jobs_date_start") or (dt.date.today() - dt.timedelta(days=7))
            default_end = st.session_state.get("jobs_date_end") or dt.date.today()
            start_date, end_date = st.date_input(
                "Created between",
                value=(default_start, default_end),
            )
            st.session_state["jobs_date_start"] = start_date
            st.session_state["jobs_date_end"] = end_date
        else:
            st.session_state["jobs_date_start"] = None
            st.session_state["jobs_date_end"] = None
    with filter_cols[2]:
        refresh_pressed = st.button("Refresh", width="stretch")
    with filter_cols[3]:
        load_more_pressed = st.button(
            "Load more",
            width="stretch",
            disabled=not st.session_state.get(JOBS_HAS_MORE_KEY, False) or is_busy(),
        )


def _filters_snapshot() -> Dict[str, Optional[str]]:
    return {
        "status": st.session_state.get("jobs_status_filter"),
        "use_date": st.session_state.get("jobs_use_date_filter"),
        "start": st.session_state.get("jobs_date_start"),
        "end": st.session_state.get("jobs_date_end"),
    }


filters_changed = st.session_state.get("jobs_last_filters") != _filters_snapshot()


def _fetch_jobs(*, reset: bool) -> None:
    set_busy(True)
    try:
        client = _get_client()
        status_filter = STATUS_TO_API.get(st.session_state.get("jobs_status_filter", "All"))
        after = None if reset else st.session_state.get("jobs_next_after")
        page = list_videos(
            client,
            limit=50,
            order="desc",
            after=after,
            status=status_filter,
        )
        data = page.get("data") or []
        if reset:
            st.session_state["jobs_rows"] = []
        for item in data:
            job_dict = to_dict(item)
            st.session_state["jobs_rows"].append(job_dict)
            cache_job(job_dict)
            upsert_video_history(job_dict, source="jobs")
        has_more = bool(page.get("has_more"))
        st.session_state[JOBS_HAS_MORE_KEY] = has_more
        st.session_state["jobs_next_after"] = data[-1].get("id") if has_more and data else None
        st.session_state["jobs_last_error"] = ""
        st.session_state["jobs_loaded_once"] = True
    except Exception as exc:  # pragma: no cover - network path
        st.session_state["jobs_last_error"] = str(exc)
    finally:
        set_busy(False)


if refresh_pressed:
    _fetch_jobs(reset=True)
elif load_more_pressed:
    _fetch_jobs(reset=False)
elif not st.session_state.get("jobs_loaded_once") or filters_changed:
    _fetch_jobs(reset=True)

st.session_state["jobs_last_filters"] = _filters_snapshot()

if st.session_state.get("jobs_last_error"):
    st.error(st.session_state["jobs_last_error"])

jobs = st.session_state.get("jobs_rows", [])


def _apply_date_filter(items: List[Dict]) -> List[Dict]:
    if not st.session_state.get("jobs_use_date_filter"):
        return items
    start = st.session_state.get("jobs_date_start")
    end = st.session_state.get("jobs_date_end")
    if not start and not end:
        return items
    filtered: List[Dict] = []
    for job in items:
        ts = job.get("created_at") or job.get("created")
        if not ts:
            filtered.append(job)
            continue
        try:
            created_dt = dt.datetime.fromtimestamp(int(ts)).date()
        except Exception:
            filtered.append(job)
            continue
        if start and created_dt < start:
            continue
        if end and created_dt > end:
            continue
        filtered.append(job)
    return filtered


visible_jobs = _apply_date_filter(jobs)

if not visible_jobs:
    st.info("No jobs found for the current filters.")
else:
    table_rows = []
    for job in visible_jobs:
        table_rows.append(
            {
                "Job ID": job.get("id", ""),
                "Status": job_status_badge(job.get("status")),
                "Created": format_ts(job.get("created_at") or job.get("created")),
                "Duration": f"{job.get('seconds', '—')}s",
                "Size": job.get("size", "—"),
                "Model": job.get("model", "—"),
            }
        )
    df = pd.DataFrame(table_rows)
    st.dataframe(df, width="stretch", hide_index=True)

    job_ids = [row.get("Job ID") for row in table_rows if row.get("Job ID")]
    if job_ids:
        default_id = st.session_state.get("jobs_selected_id") or job_ids[0]
        st.session_state["jobs_selected_id"] = st.selectbox(
            "Select a job",
            job_ids,
            index=job_ids.index(default_id) if default_id in job_ids else 0,
        )
    else:
        st.session_state["jobs_selected_id"] = None

selected_id = st.session_state.get("jobs_selected_id")
selected_job = None
if selected_id:
    for job in jobs:
        if job.get("id") == selected_id:
            selected_job = job
            break
    if selected_job:
        st.session_state["jobs_selected_job"] = selected_job


actions_container = st.container()


def _update_selected_job(job_dict: Dict) -> None:
    st.session_state["jobs_selected_job"] = job_dict
    st.session_state["jobs_selected_media_url"] = extract_asset_url(job_dict)
    st.session_state["jobs_selected_media_bytes"] = None
    rows = st.session_state.get("jobs_rows", [])
    for idx, existing in enumerate(rows):
        if existing.get("id") == job_dict.get("id"):
            rows[idx] = job_dict
            break
    else:
        rows.insert(0, job_dict)


with actions_container:
    st.markdown("#### Actions")
    if not selected_id:
        st.info("Select a job above to enable actions.")
    else:
        action_cols = st.columns(5)

        def _handle_open() -> None:
            set_busy(True)
            try:
                client = _get_client()
                with st.status("Fetching job…", expanded=False) as status:
                    job = get_video(client, selected_id)
                    job_dict = to_dict(job)
                    cache_job(job_dict)
                    upsert_video_history(job_dict, source="open")
                    _update_selected_job(job_dict)
                    status.update(label="Fetched", state="complete", expanded=False)
                toast_success("Job details refreshed.")
            except Exception as exc:  # pragma: no cover - network path
                toast_error(str(exc))
            finally:
                set_busy(False)

        def _handle_resume_polling() -> None:
            progress_placeholder = st.empty()
            set_busy(True)
            try:
                client = _get_client()
                progress_bar = progress_placeholder.progress(0, text="Resuming polling…")
                with st.status("Checking render…", expanded=False) as status:
                    def _tick(job_update: Dict) -> None:
                        job_dict = to_dict(job_update)
                        cache_job(job_dict)
                        upsert_video_history(job_dict, source="poll")
                        pct = max(0, min(100, get_progress_percent(job_dict)))
                        label = "Finalizing" if pct >= 99 else f"Rendering {pct}%"
                        progress_bar.progress(max(pct, 1), text=label)
                        status.update(label=label, state="running", expanded=True)

                    job_obj = poll_until_complete(client, selected_id, sleep_s=3, on_tick=_tick)
                    job_dict = to_dict(job_obj)
                    progress_bar.progress(100, text="Ready")
                    status.update(label="Ready", state="complete", expanded=False)
                    cache_job(job_dict)
                    upsert_video_history(job_dict, source="complete")
                    _update_selected_job(job_dict)
                toast_success("Job completed.")
            except Exception as exc:  # pragma: no cover - network path
                toast_error(str(exc))
            finally:
                progress_placeholder.empty()
                set_busy(False)

        def _handle_download() -> None:
            set_busy(True)
            try:
                client = _get_client()
                with st.status("Downloading MP4…", expanded=False) as status:
                    status.write("Requesting media stream…")
                    media_bytes = download_video_bytes(client, selected_id)
                    st.session_state["jobs_download_payload"] = {
                        "id": selected_id,
                        "bytes": media_bytes,
                        "file_name": f"{selected_id}.mp4",
                    }
                    st.session_state["jobs_selected_media_bytes"] = media_bytes
                    status.update(label="Download ready", state="complete", expanded=False)
                toast_success("Download ready below.")
            except Exception as exc:  # pragma: no cover - network path
                toast_error(str(exc))
            finally:
                set_busy(False)

        def _handle_delete() -> None:
            st.session_state["jobs_pending_delete"] = selected_id

        action_cols[0].button("Open", on_click=_handle_open, disabled=is_busy())
        action_cols[1].button("Resume polling", on_click=_handle_resume_polling, disabled=is_busy())
        action_cols[2].button("Download MP4", on_click=_handle_download, disabled=is_busy())
        with action_cols[3]:
            st.download_button(
                "Download JSON",
                data=json.dumps(selected_job or {}, indent=2),
                file_name=f"{selected_id}.json" if selected_id else "job.json",
                mime="application/json",
                width="stretch",
                disabled=is_busy() or selected_job is None,
            )
        action_cols[4].button("Delete", on_click=_handle_delete, disabled=is_busy())

        download_payload = st.session_state.get("jobs_download_payload")
        if download_payload and download_payload.get("id") == selected_id:
            st.download_button(
                "Save MP4",
                data=download_payload.get("bytes"),
                file_name=download_payload.get("file_name"),
                mime="video/mp4",
                width="stretch",
            )

        pending_delete = st.session_state.get("jobs_pending_delete")
        if pending_delete == selected_id:
            st.warning("This will permanently delete the video from OpenAI. Confirm?")
            confirm_cols = st.columns([1, 1, 3])

            def _execute_delete() -> None:
                set_busy(True)
                try:
                    client = _get_client()
                    with st.status("Deleting video…", expanded=False) as status:
                        status.write("Sending delete request…")
                        delete_video(client, selected_id)
                        remove_video_from_history(selected_id)
                        st.session_state["jobs_rows"] = [
                            job for job in st.session_state.get("jobs_rows", []) if job.get("id") != selected_id
                        ]
                        st.session_state["jobs_selected_job"] = None
                        st.session_state["jobs_selected_media_url"] = None
                        st.session_state["jobs_selected_media_bytes"] = None
                        if st.session_state.get("jobs_download_payload", {}).get("id") == selected_id:
                            st.session_state["jobs_download_payload"] = None
                        status.update(label="Deleted", state="complete", expanded=False)
                    toast_success("Video deleted.")
                except Exception as exc:  # pragma: no cover - network path
                    toast_error(str(exc))
                finally:
                    st.session_state["jobs_pending_delete"] = None
                    set_busy(False)

            confirm_cols[0].button("Confirm delete", on_click=_execute_delete, disabled=is_busy())
            confirm_cols[1].button(
                "Cancel",
                on_click=lambda: st.session_state.update({"jobs_pending_delete": None}),
                disabled=is_busy(),
            )


st.divider()

st.markdown("### Job details")
selected_job = st.session_state.get("jobs_selected_job")

if not selected_job:
    st.info("Select a job and choose an action to view details here.")
else:
    job_id = selected_job.get("id", "unknown")
    st.markdown(f"**Job ID:** `{job_id}`")
    detail_cols = st.columns(4)
    detail_cols[0].metric("Status", selected_job.get("status", "unknown"))
    detail_cols[1].metric("Duration", f"{selected_job.get('seconds', '—')}s")
    detail_cols[2].metric("Size", selected_job.get("size", "—"))
    detail_cols[3].metric("Created", format_ts(selected_job.get("created_at") or selected_job.get("created")))

    media_url = st.session_state.get("jobs_selected_media_url")
    media_bytes = st.session_state.get("jobs_selected_media_bytes")
    if media_url:
        st.video(media_url)
    elif media_bytes:
        st.video(media_bytes)
    else:
        st.caption("Open the job or resume polling to load a preview.")

    st.markdown("#### Raw metadata")
    st.code(json.dumps(selected_job, indent=2), language="json")

recent_jobs = st.session_state.get(VIDEO_HISTORY_KEY, [])[:8]
if recent_jobs:
    st.markdown("#### Recent session jobs")
    for entry in recent_jobs:
        st.write(f"• `{entry.get('id')}` · {entry.get('status')} · {entry.get('size', '—')} · {entry.get('seconds', '—')}s")
