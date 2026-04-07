from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import tempfile

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.customer import CustomerProfile
from app.models.instagram import InstagramCarouselDraft, InstagramPublishJob
from app.repositories.instagram import InstagramCarouselDraftRepository

logger = logging.getLogger(__name__)

MAX_PUBLISH_ATTEMPTS = 3


@dataclass
class RenderedSlideAsset:
    slide_number: int
    template_id: str | None
    template_version: str | None
    schema_version: str | None
    width: int
    height: int
    content_hash: str
    filename: str
    content: bytes


class InstagramRenderer:
    def __init__(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.script_path = repo_root / "frontend" / "scripts" / "render-instagram.mjs"

    def render(self, draft: InstagramCarouselDraft) -> list[RenderedSlideAsset]:
        payload = {
            "draft_id": draft.id,
            "lane": draft.lane,
            "title": draft.title,
            "hook": draft.hook,
            "angle": draft.angle,
            "slides": draft.slides,
            "template_version": draft.template_version,
            "template_bundle_version": draft.template_bundle_version,
            "schema_version": draft.schema_version,
        }
        with tempfile.TemporaryDirectory(prefix="ig-render-") as tmpdir:
            tmpdir_path = Path(tmpdir)
            input_path = tmpdir_path / "input.json"
            output_dir = tmpdir_path / "rendered"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            output_dir.mkdir(parents=True, exist_ok=True)
            completed = subprocess.run(
                ["node", str(self.script_path), str(input_path), str(output_dir)],
                capture_output=True,
                text=True,
                check=True,
            )
            manifest = json.loads((completed.stdout or "{}").strip() or "{}")
            assets: list[RenderedSlideAsset] = []
            for slide in manifest.get("slides") or []:
                file_path = output_dir / str(slide["filename"])
                assets.append(
                    RenderedSlideAsset(
                        slide_number=int(slide["slide_number"]),
                        template_id=slide.get("template_id"),
                        template_version=slide.get("template_version"),
                        schema_version=slide.get("schema_version"),
                        width=int(slide.get("width") or 1080),
                        height=int(slide.get("height") or 1350),
                        content_hash=str(slide.get("content_hash") or _hash_bytes(file_path.read_bytes())),
                        filename=file_path.name,
                        content=file_path.read_bytes(),
                    )
                )
            return assets


class SupabaseStorageClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = (self.settings.supabase_url or "").rstrip("/")
        self.service_key = self.settings.supabase_service_role_key
        self.bucket = self.settings.instagram_asset_bucket

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.service_key)

    def ensure_bucket(self) -> None:
        if not self.enabled:
            raise RuntimeError("supabase_storage_not_configured")
        headers = self._headers()
        with httpx.Client(timeout=20.0) as client:
            response = client.get(f"{self.base_url}/storage/v1/bucket/{self.bucket}", headers=headers)
            if response.status_code == 200:
                return
            if response.status_code != 404:
                response.raise_for_status()
            create = client.post(
                f"{self.base_url}/storage/v1/bucket",
                headers=headers,
                json={"id": self.bucket, "name": self.bucket, "public": True},
            )
            create.raise_for_status()

    def upload_png(self, *, path: str, content: bytes) -> str:
        self.ensure_bucket()
        headers = self._headers()
        headers["x-upsert"] = "true"
        headers["content-type"] = "image/png"
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{self.base_url}/storage/v1/object/{self.bucket}/{path}",
                headers=headers,
                content=content,
            )
            response.raise_for_status()
        return f"{self.base_url}/storage/v1/object/public/{self.bucket}/{path}"

    def _headers(self) -> dict[str, str]:
        key = self.service_key or ""
        return {
            "Authorization": f"Bearer {key}",
            "apikey": key,
        }


class InstagramPublisher:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.instagram_graph_api_base.rstrip("/")

    def publish_carousel(self, profile: CustomerProfile, draft: InstagramCarouselDraft) -> dict:
        token_store = profile.token_store or {}
        access_token = token_store.get("instagram_access_token")
        account_id = token_store.get("instagram_business_account_id")
        if not access_token or not account_id:
            raise RuntimeError("instagram_credentials_missing")
        manifest = dict(draft.asset_manifest or {})
        preview_slides = list(manifest.get("slides") or [])
        if not preview_slides:
            raise RuntimeError("instagram_assets_missing")

        caption = _compose_instagram_caption(draft)
        with httpx.Client(timeout=30.0) as client:
            child_ids: list[str] = []
            for slide in preview_slides:
                child_response = client.post(
                    f"{self.base_url}/{account_id}/media",
                    data={
                        "image_url": slide["preview_url"],
                        "is_carousel_item": "true",
                        "access_token": access_token,
                    },
                )
                child_response.raise_for_status()
                child_payload = child_response.json()
                child_id = str(child_payload.get("id") or "")
                if not child_id:
                    raise RuntimeError("instagram_child_container_missing_id")
                child_ids.append(child_id)

            parent_response = client.post(
                f"{self.base_url}/{account_id}/media",
                data={
                    "media_type": "CAROUSEL",
                    "children": ",".join(child_ids),
                    "caption": caption,
                    "access_token": access_token,
                },
            )
            parent_response.raise_for_status()
            parent_payload = parent_response.json()
            parent_id = str(parent_payload.get("id") or "")
            if not parent_id:
                raise RuntimeError("instagram_parent_container_missing_id")

            publish_response = client.post(
                f"{self.base_url}/{account_id}/media_publish",
                data={
                    "creation_id": parent_id,
                    "access_token": access_token,
                },
            )
            publish_response.raise_for_status()
            publish_payload = publish_response.json()
            publish_id = str(publish_payload.get("id") or "")
            if not publish_id:
                raise RuntimeError("instagram_publish_missing_id")
        return {
            "child_ids": child_ids,
            "container_id": parent_id,
            "publish_id": publish_id,
            "publish_payload": publish_payload,
        }


def render_instagram_draft(
    db: Session,
    draft: InstagramCarouselDraft,
    *,
    renderer: InstagramRenderer | None = None,
    storage: SupabaseStorageClient | None = None,
) -> InstagramCarouselDraft:
    repo = InstagramCarouselDraftRepository(db)
    render_hash = _draft_render_hash(draft)
    existing_manifest = dict(draft.asset_manifest or {})
    if draft.render_status == "rendered" and existing_manifest.get("render_hash") == render_hash:
        return draft
    actual_renderer = renderer or InstagramRenderer()
    actual_storage = storage or SupabaseStorageClient()
    try:
        assets = actual_renderer.render(draft)
        render_version = int(existing_manifest.get("render_version") or 0) + 1
        manifest_slides = []
        for asset in assets:
            storage_path = f"instagram/{draft.customer_profile_id}/{draft.id}/{render_version}/slide-{asset.slide_number:02d}.png"
            preview_url = actual_storage.upload_png(path=storage_path, content=asset.content)
            manifest_slides.append(
                {
                    "slide_number": asset.slide_number,
                    "template_id": asset.template_id,
                    "template_version": asset.template_version,
                    "schema_version": asset.schema_version,
                    "storage_path": storage_path,
                    "preview_url": preview_url,
                    "width": asset.width,
                    "height": asset.height,
                    "content_hash": asset.content_hash,
                }
            )
        manifest = {
            "bucket": actual_storage.bucket,
            "render_hash": render_hash,
            "render_version": render_version,
            "rendered_at": datetime.now(timezone.utc).isoformat(),
            "slides": manifest_slides,
        }
        repo.mark_render_state(draft, status="rendered", manifest=manifest, error=None)
        return draft
    except Exception as exc:
        logger.exception("instagram render failed for draft %s", draft.id)
        repo.mark_render_state(draft, status="render_failed", error=str(exc))
        return draft


def schedule_instagram_draft(
    db: Session,
    draft: InstagramCarouselDraft,
    *,
    scheduled_for: datetime | None = None,
) -> InstagramPublishJob:
    repo = InstagramCarouselDraftRepository(db)
    if draft.review_status != "approved":
        raise ValueError("instagram_draft_not_approved")
    if draft.render_status != "rendered" or not (draft.asset_manifest or {}).get("slides"):
        raise ValueError("instagram_draft_not_rendered")
    active = repo.get_active_job_for_draft(draft.id)
    if active is not None:
        if scheduled_for is not None:
            active.scheduled_for = scheduled_for
        draft.publish_status = "scheduled"
        draft.scheduled_for = active.scheduled_for
        db.flush()
        return active
    job = repo.add_publish_job(draft_id=draft.id, scheduled_for=scheduled_for or datetime.now(timezone.utc))
    repo.mark_publish_state(draft, status="scheduled", scheduled_for=job.scheduled_for, error=None)
    return job


def publish_instagram_job(
    db: Session,
    job: InstagramPublishJob,
    *,
    publisher: InstagramPublisher | None = None,
) -> InstagramPublishJob:
    repo = InstagramCarouselDraftRepository(db)
    draft = repo.get(job.instagram_draft_id)
    if draft is None:
        repo.update_publish_job(job, status="failed", error="instagram_draft_missing", result_message="draft_missing")
        return job
    profile = db.get(CustomerProfile, draft.customer_profile_id)
    if profile is None:
        repo.update_publish_job(job, status="failed", error="instagram_profile_missing", result_message="profile_missing")
        return job
    if draft.review_status != "approved" or draft.render_status != "rendered":
        repo.update_publish_job(job, status="failed", error="instagram_draft_not_publishable", result_message="not_publishable")
        repo.mark_publish_state(draft, status="publish_failed", error="instagram_draft_not_publishable")
        return job
    actual_publisher = publisher or InstagramPublisher()
    repo.update_publish_job(job, status="publishing", error=None, result_message="publishing")
    repo.mark_publish_state(draft, status="publishing", scheduled_for=job.scheduled_for, error=None)
    try:
        result = actual_publisher.publish_carousel(profile, draft)
        posted_at = datetime.now(timezone.utc)
        repo.update_publish_job(job, status="posted", error=None, result_message="instagram_published")
        repo.mark_publish_state(
            draft,
            status="published",
            scheduled_for=job.scheduled_for,
            published_at=posted_at,
            error=None,
            media_container_id=result.get("container_id"),
            publish_id=result.get("publish_id"),
        )
        repo.add_publish_log(
            job_id=job.id,
            platform_post_id=result.get("publish_id"),
            posted_at=posted_at,
            response_payload=result,
        )
    except Exception as exc:
        logger.exception("instagram publish failed for draft %s", draft.id)
        final_status = "failed"
        message = "publish_failed"
        draft_status = "publish_failed"
        if (job.attempt_count or 0) < MAX_PUBLISH_ATTEMPTS:
            final_status = "queued"
            message = "retry_scheduled"
            draft_status = "scheduled"
            job.scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=5)
        repo.update_publish_job(job, status=final_status, error=str(exc), result_message=message)
        repo.mark_publish_state(draft, status=draft_status, scheduled_for=job.scheduled_for, error=str(exc))
    return job


def run_instagram_publish_cycle() -> dict:
    from app.db.session import SessionLocal

    summary = {"jobs_considered": 0, "posted": 0, "failed": 0, "queued": 0}
    with SessionLocal() as db:
        repo = InstagramCarouselDraftRepository(db)
        jobs = repo.list_due_publish_jobs(limit=10)
        summary["jobs_considered"] = len(jobs)
        for job in jobs:
            publish_instagram_job(db, job)
            if job.status == "posted":
                summary["posted"] += 1
            elif job.status == "queued":
                summary["queued"] += 1
            else:
                summary["failed"] += 1
        db.commit()
    return summary


def serialize_instagram_publish_job(job: InstagramPublishJob, draft: InstagramCarouselDraft | None = None) -> dict:
    return {
        "id": job.id,
        "instagram_draft_id": job.instagram_draft_id,
        "status": job.status,
        "scheduled_for": job.scheduled_for.isoformat() if job.scheduled_for else None,
        "attempt_count": job.attempt_count,
        "last_error": job.last_error,
        "result_message": job.result_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "draft": None if draft is None else {
            "id": draft.id,
            "lane": draft.lane,
            "title": draft.title,
            "publish_status": draft.publish_status,
            "render_status": draft.render_status,
        },
    }


def serialize_instagram_publish_log(log) -> dict:
    return {
        "id": log.id,
        "instagram_publish_job_id": log.instagram_publish_job_id,
        "platform_post_id": log.platform_post_id,
        "posted_at": log.posted_at.isoformat() if log.posted_at else None,
        "response_payload": log.response_payload,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _compose_instagram_caption(draft: InstagramCarouselDraft) -> str:
    caption = dict(draft.caption or {})
    parts = [
        str(caption.get("hook") or "").strip(),
        str(caption.get("body") or "").strip(),
        str(caption.get("cta") or "").strip(),
    ]
    return "\n\n".join(part for part in parts if part)


def _draft_render_hash(draft: InstagramCarouselDraft) -> str:
    payload = {
        "lane": draft.lane,
        "title": draft.title,
        "hook": draft.hook,
        "angle": draft.angle,
        "slides": draft.slides,
        "caption": draft.caption,
        "template_version": draft.template_version,
        "template_bundle_version": draft.template_bundle_version,
        "schema_version": draft.schema_version,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
