"""OpenAI Videos API helpers and shared utility functions."""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, Optional

from collections.abc import Mapping
from openai import OpenAI


# =========================
# Shared utilities (kept from original app)
# =========================

def to_dict(obj) -> dict:
    """Normalize SDK responses/models to a plain dict for safe .get(...)."""
    if obj is None:
        return {}
    if isinstance(obj, Mapping):
        return dict(obj)
    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        try:
            return obj.model_dump()
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        try:
            return dict(obj.__dict__)
        except Exception:
            pass
    # Last resort: wrap scalars so callers can still access an 'id'
    if isinstance(obj, (str, int)):
        return {"id": str(obj)}
    return {"value": obj}


def safe_get_id(obj) -> Optional[str]:
    """Extract an id regardless of whether obj is a dict, model, or scalar."""
    if obj is None:
        return None
    if isinstance(obj, (str, int)):
        return str(obj)
    if hasattr(obj, "id"):
        try:
            vid = getattr(obj, "id")
            if isinstance(vid, (str, int)):
                return str(vid)
        except Exception:
            pass
    d = to_dict(obj)
    vid = d.get("id")
    return str(vid) if isinstance(vid, (str, int)) else None


def get_progress_percent(job: dict) -> int:
    """
    Normalize job progress to 0–100.
    Docs: `progress` is an integer percent; some SDKs may expose `percent_complete`.
    """
    status = str(job.get("status", "")).lower()
    p = job.get("progress", None)

    # Primary (per docs): integer percent
    if isinstance(p, (int, float, str)):
        try:
            return max(0, min(100, int(p)))
        except Exception:
            pass

    # Fallback: alternate field name
    alt = job.get("percent_complete", None)
    if isinstance(alt, (int, float, str)):
        try:
            return max(0, min(100, int(alt)))
        except Exception:
            pass

    # Status-based fallback
    if status in ("queued", "in_progress"):
        return 0
    if status in ("succeeded", "completed", "complete"):
        return 100
    return 0


def poll_until_complete(
    client: OpenAI,
    video_id: str,
    sleep_s: int = 3,
    on_tick: Optional[Callable[[dict], None]] = None,
) -> dict:
    """
    Poll GET /v1/videos/{video_id} until the job is complete or failed.
    Returns the final job as a dict.
    """
    while True:
        job = client.videos.retrieve(video_id)
        job_dict = to_dict(job)
        if callable(on_tick):
            on_tick(job_dict)
        status = str(job_dict.get("status", "")).lower()
        if status in ("succeeded", "completed", "complete"):
            return job_dict
        if status in ("failed", "error", "canceled", "cancelled"):
            raise RuntimeError(f"Video job {status}. Details:\n{json.dumps(job_dict, indent=2)}")
        time.sleep(sleep_s)


def download_video_bytes(client: OpenAI, video_id: str, variant: Optional[str] = None) -> bytes:
    """
    Downloads rendered media via GET /v1/videos/{video_id}/content.
    If variant is None, server defaults to MP4.
    """
    if variant:
        resp = client.videos.download_content(video_id=video_id, variant=variant)
    else:
        resp = client.videos.download_content(video_id=video_id)
    return resp.read()


# ---- Helper: extract video URL from job object (kept) ----

def extract_asset_url(job: dict) -> Optional[str]:
    # Try a few common shapes
    try:
        url = job.get("assets", [{}])[0].get("url")
        if isinstance(url, str) and url.startswith("http"):
            return url
    except Exception:
        pass
    try:
        url = job.get("output", [{}])[0].get("url")
        if isinstance(url, str) and url.startswith("http"):
            return url
    except Exception:
        pass
    url = job.get("download_url")
    if isinstance(url, str) and url.startswith("http"):
        return url
    try:
        url = (job.get("assets") or {}).get("video", {}).get("url")
        if isinstance(url, str) and url.startswith("http"):
            return url
    except Exception:
        pass
    return None


def list_videos_page(
    client: OpenAI,
    limit: int = 10,
    order: str = "desc",
    after: Optional[str] = None,
):
    """
    Calls GET /v1/videos with pagination. Returns (items, has_more, next_after, raw_page_dict).
    We compute next_after as the last id on this page (works with 'after' pagination).
    """
    page = (
        client.videos.list(limit=limit, order=order, after=after)
        if after
        else client.videos.list(limit=limit, order=order)
    )
    page_dict = to_dict(page)
    data = page_dict.get("data") or []
    items = [to_dict(x) for x in data]
    has_more = bool(page_dict.get("has_more"))
    next_after = items[-1].get("id") if items else None
    return items, has_more, next_after, page_dict


# =========================
# Wrapper functions for the new UI
# =========================


def get_openai_client(
    api_key: str,
    *,
    base_url: Optional[str] = None,
) -> OpenAI:
    kwargs: Dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def create_video(client: OpenAI, payload: Dict[str, Any]):
    return client.videos.create(**payload)


def get_video(client: OpenAI, video_id: str):
    return client.videos.retrieve(video_id)


def delete_video(client: OpenAI, video_id: str):
    return client.videos.delete(video_id)


def list_videos(
    client: OpenAI,
    *,
    limit: int = 50,
    order: str = "desc",
    after: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {"limit": limit, "order": order}
    if after:
        params["after"] = after
    if status and status.lower() != "all":
        params["status"] = status
    page = client.videos.list(**params)
    return to_dict(page)


def download_video_to_file(
    client: OpenAI,
    video_id: str,
    *,
    variant: Optional[str] = None,
    chunk_size: int = 1024 * 512,
    writer: Optional[Callable[[bytes], None]] = None,
) -> bytes:
    resp = (
        client.videos.download_content(video_id=video_id, variant=variant)
        if variant
        else client.videos.download_content(video_id=video_id)
    )
    if writer:
        content = b""
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            writer(chunk)
            content += chunk
        return content
    return resp.read()
