from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from types import SimpleNamespace

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.wire_feed import WireCandidate, WireJob
from app.repositories.customers import CustomerProfileRepository
from app.repositories.wire_feed import WireCandidateRepository, WireJobRepository
from app.services.publishing.x_client import XPublisher
from app.services.drafting.service import DraftingService
from app.wire_feed.pipeline import fetch_and_process, generate_ai_evergreen_backlog_results
from app.wire_feed.policy import plan_wire_queue
from app.wire_feed.products import normalize_wire_product, policy_for_product
from app.wire_feed.sources import get_wire_sources
from app.wire_feed.web_pipeline import fetch_web_breaking_candidates, get_due_web_runs

logger = logging.getLogger(__name__)
_WIRE_MAX_ATTEMPTS = 3
_BASE_FETCH_INTERVAL = timedelta(hours=1)
_MAX_POST_LENGTH = 280
_DANGLING_ENDINGS = (
    "for",
    "with",
    "by",
    "as",
    "to",
    "from",
    "and",
    "or",
    "of",
    "in",
    "on",
    "at",
    "into",
    "over",
    "under",
    "after",
    "before",
    "vs",
    "vs.",
)


def _enabled_source_families(profile) -> set[str]:
    store = dict(getattr(profile, "token_store", {}) or {})
    configured = store.get("source_families")
    if isinstance(configured, list):
        enabled = {str(item).strip().lower() for item in configured if str(item).strip().lower() in {"base", "web"}}
        if enabled:
            return enabled
    return {"base", "web"}


def run_wire_cycle() -> dict[str, list[dict] | int]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    summary: dict[str, list[dict] | int] = {
        "sources_processed": 0,
        "candidates": 0,
        "post_now": 0,
        "queued": 0,
        "skipped": 0,
        "posted": 0,
        "failed": 0,
        "items": [],
    }
    with SessionLocal() as db:
        candidate_repo = WireCandidateRepository(db)
        job_repo = WireJobRepository(db)
        customer_repo = CustomerProfileRepository(db)
        list_active = getattr(customer_repo, "list_active_autopost_customers", None)
        if callable(list_active):
            active_profiles = list_active()
        else:
            get_active = getattr(customer_repo, "get_active_autopost_customer", None)
            profile = get_active() if callable(get_active) else None
            if profile is not None:
                active_profiles = [profile]
            elif getattr(customer_repo, "has_active_autopost_customer", lambda: False)():
                active_profiles = [SimpleNamespace(id=0, wire_product="finance", token_store={})]
            else:
                active_profiles = []

        for profile in active_profiles:
            product = normalize_wire_product(getattr(profile, "wire_product", "finance"))
            store = dict(getattr(profile, "token_store", {}) or {})
            enabled_source_families = _enabled_source_families(profile)
            try:
                drafting = DraftingService(api_key=store.get("openai_api_key"), model=settings.openai_model)
            except TypeError:
                drafting = DraftingService()
            policy = policy_for_product(product)
            try:
                expired = job_repo.expire_stale_jobs(now, policy, customer_profile_id=profile.id)
            except TypeError:
                expired = job_repo.expire_stale_jobs(now, policy)
            try:
                recent_records = job_repo.recent_post_records(now - timedelta(days=1), profile.id)
            except TypeError:
                recent_records = job_repo.recent_post_records(now - timedelta(days=1))
            summary["skipped"] += expired

            candidate_batches: list[tuple[str, list]] = []
            try:
                sources = get_wire_sources(product)
            except TypeError:
                sources = get_wire_sources()
            if "base" in enabled_source_families:
                for source in sources:
                    source_name = getattr(source, "name", None) or f"{source.key}_feed"
                    has_source_since = getattr(candidate_repo, "has_source_candidate_since", None)
                    if callable(has_source_since):
                        try:
                            has_recent = has_source_since(profile.id, source_name, now - _BASE_FETCH_INTERVAL)
                        except TypeError:
                            has_recent = has_source_since(source_name, now - _BASE_FETCH_INTERVAL)
                    else:
                        has_recent = False
                    if has_recent:
                        continue
                    candidate_batches.append((source.key, fetch_and_process(source, drafting)))
                if product == "ai":
                    candidate_batches.append(("ai_evergreen_backlog", generate_ai_evergreen_backlog_results(drafting)))

            if settings.wire_web_breaking_enabled and "web" in enabled_source_families:
                def _has_source_since(source_name, since):
                    try:
                        return candidate_repo.has_source_candidate_since(profile.id, source_name, since)
                    except TypeError:
                        return candidate_repo.has_source_candidate_since(source_name, since)

                due_runs = get_due_web_runs(
                    now,
                    _has_source_since,
                    product=product,
                )
                for run in due_runs:
                    candidate_batches.append(
                        (
                            run.key,
                            fetch_web_breaking_candidates(
                                run,
                                openai_api_key=store.get("openai_api_key"),
                                tavily_api_key=store.get("tavily_api_key"),
                            ),
                        )
                    )

            all_results = [result for _, results in candidate_batches for result in results]
            _apply_customer_branding(all_results, profile)
            decisions = plan_wire_queue(all_results, recent_posts=recent_records, now=now, settings=policy)
            decisions_by_source: dict[str, list] = {source_key: [] for source_key, _ in candidate_batches}
            for decision in decisions:
                source_key = getattr(decision.result, "source_name", None) or (
                    candidate_batches[0][0] if len(candidate_batches) == 1 else "unknown"
                )
                if source_key == "tradient_market_news":
                    source_key = "tradient"
                if source_key.startswith("tavily_"):
                    source_key = source_key.removeprefix("tavily_")
                decisions_by_source.setdefault(source_key, []).append(decision)

            summary["sources_processed"] += len(candidate_batches)
            summary["candidates"] += len(all_results)

            for source_key, source_decisions in decisions_by_source.items():
                source_items: list[dict] = []
                for decision in source_decisions:
                    try:
                        candidate = candidate_repo.upsert_from_result(profile.id, decision.result)
                    except TypeError:
                        candidate = candidate_repo.upsert_from_result(decision.result)
                    if decision.priority == "breaking" and decision.action in {"post_now", "queue", "defer"} and decision.scheduled_for is not None:
                        try:
                            job_repo.bump_non_breaking_queue(decision.scheduled_for, policy, customer_profile_id=profile.id)
                        except TypeError:
                            job_repo.bump_non_breaking_queue(decision.scheduled_for, policy)
                    job_repo.record_decision(candidate, decision)
                    if decision.action == "post_now":
                        summary["post_now"] += 1
                    elif decision.action in {"queue", "defer"}:
                        summary["queued"] += 1
                    else:
                        summary["skipped"] += 1
                    source_items.append(
                        {
                            "customer_profile_id": profile.id,
                            "product": product,
                            "action": decision.action,
                            "priority": decision.priority,
                            "scheduled_for": decision.scheduled_for.isoformat() if decision.scheduled_for else None,
                            "reason": decision.reason,
                            "title": decision.result.title,
                            "draft_text": decision.result.draft_text,
                            "score": decision.result.importance_score,
                        }
                    )
                cast_items = summary["items"]
                if isinstance(cast_items, list):
                    cast_items.append({"source": source_key, "customer_profile_id": profile.id, "product": product, "decisions": source_items})

            db.commit()
            try:
                publish_counts = _publish_due_jobs(db, profile, now)
            except TypeError:
                publish_counts = _publish_due_jobs(db, now)
            summary["posted"] += publish_counts["posted"]
            summary["failed"] += publish_counts["failed"]

    return summary


def _apply_customer_branding(results: list, profile) -> None:
    suffix = _customer_brand_suffix(profile)
    if not suffix:
        return
    for result in results:
        draft_text = str(getattr(result, "draft_text", "") or "").strip()
        if not draft_text:
            continue
        result.draft_text = _append_suffix(draft_text, suffix)
        raw_payload = dict(getattr(result, "raw_payload", {}) or {})
        raw_payload["brand_suffix"] = suffix
        setattr(result, "raw_payload", raw_payload)


def _customer_brand_suffix(profile) -> str:
    store = dict(getattr(profile, "token_store", {}) or {})
    brand_name = str(store.get("brand_name") or getattr(profile, "display_name", "") or "").strip()
    sebi_registration = str(store.get("sebi_registration") or "").strip()
    cta_short = str(store.get("cta_short") or "").strip()
    lines: list[str] = []
    if brand_name and sebi_registration:
        lines.append(f"{brand_name} | SEBI Registered RA ({sebi_registration})")
    elif brand_name:
        lines.append(brand_name)
    if cta_short:
        lines.append(cta_short)
    return "\n".join(lines).strip()


def _append_suffix(text: str, suffix: str) -> str:
    if not suffix:
        return text
    separator = "\n\n"
    combined = f"{text}{separator}{suffix}".strip()
    if len(combined) <= _MAX_POST_LENGTH:
        return combined
    allowed = _MAX_POST_LENGTH - len(separator) - len(suffix)
    if allowed <= 20:
        return suffix[:_MAX_POST_LENGTH]
    trimmed = _trim_publish_body(text, allowed)
    return f"{trimmed}{separator}{suffix}"


def _trim_publish_body(text: str, allowed: int) -> str:
    cleaned = " ".join((text or "").split()).strip()
    if len(cleaned) <= allowed:
        return cleaned
    truncated = cleaned[:allowed].rstrip()
    sentence_cut = max(truncated.rfind(". "), truncated.rfind("! "), truncated.rfind("? "))
    clause_cut = max(truncated.rfind("; "), truncated.rfind(": "))
    chosen_cut = max(sentence_cut, clause_cut)
    if chosen_cut > max(allowed - 80, 40):
        truncated = truncated[: chosen_cut + 1].rstrip()
    else:
        word_cut = truncated.rfind(" ")
        if word_cut > max(allowed - 40, 30):
            truncated = truncated[:word_cut].rstrip()
    truncated = truncated.rstrip(" ,;:-")
    words = truncated.split()
    while words and words[-1].lower().rstrip(".") in _DANGLING_ENDINGS:
        words.pop()
    truncated = " ".join(words).rstrip(" ,;:-")
    if truncated and truncated[-1] not in ".!?":
        truncated += "."
    return truncated or cleaned[:allowed].rstrip(" ,;:-") + "."


def _is_valid_publish_text(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned or len(cleaned) > _MAX_POST_LENGTH:
        return False
    body = cleaned.split("\n\n", 1)[0].strip()
    if len(body) < 25:
        return False
    lowered = body.lower()
    if lowered.endswith("..."):
        return False
    if any(lowered.endswith(f" {ending}") for ending in _DANGLING_ENDINGS):
        return False
    blocked_endings = (
        "the real message is...",
        "what matters now is...",
        "watch this...",
    )
    return not any(lowered.endswith(ending) for ending in blocked_endings)


def _publish_due_jobs(db, profile, now: datetime | None = None) -> dict[str, int]:
    if now is None:
        now = profile
        customer_repo = CustomerProfileRepository(db)
        profile = customer_repo.get_active_autopost_customer()
    job_repo = WireJobRepository(db)
    if profile is None:
        logger.info("No active autopost customer with X tokens; skipping wire publish")
        return {"posted": 0, "failed": 0}

    def _save_tokens(access_token: str, refresh_token: str) -> None:
        store = dict(profile.token_store or {})
        store["x_access_token"] = access_token
        if refresh_token:
            store["x_refresh_token"] = refresh_token
        profile.token_store = store
        db.flush()

    publisher = XPublisher(token_store=dict(profile.token_store or {}), on_token_refresh=_save_tokens)
    # Only publish one due wire job per cycle so late resume/backlog states
    # do not flush multiple overdue posts at once.
    customer_profile_id = getattr(profile, "id", None)
    try:
        jobs = job_repo.claim_ready(now=now, limit=1, customer_profile_id=customer_profile_id)
    except TypeError:
        jobs = job_repo.claim_ready(now=now, limit=1)
    posted = 0
    failed = 0
    for job in jobs:
        candidate = db.get(WireCandidate, job.candidate_id)
        if candidate is None:
            job.status = "failed"
            job.last_error = "missing_candidate"
            failed += 1
            continue
        try:
            has_duplicate = job_repo.has_active_duplicate(candidate.dedupe_key, exclude_job_id=job.id, customer_profile_id=customer_profile_id)
        except TypeError:
            has_duplicate = job_repo.has_active_duplicate(candidate.dedupe_key, exclude_job_id=job.id)
        if has_duplicate:
            job.status = "skipped"
            job.result_message = "duplicate_active_job"
            job.last_error = None
            continue
        if not _is_valid_publish_text(candidate.draft_text):
            job.status = "skipped"
            job.result_message = "invalid_final_text"
            job.last_error = None
            continue
        try:
            response = publisher.publish(candidate.draft_text, idempotency_key=job.idempotency_key)
            status = response.get("status")
            if status == "posted":
                job.status = "posted"
                job.last_error = None
                job.result_message = None
                job_repo.add_log(job.id, response, platform_post_id=response.get("data", {}).get("id"))
                posted += 1
            elif status == "rate_limited":
                retry_after = int(response.get("retry_after_seconds", 900))
                job.status = "queued"
                job.scheduled_for = now + timedelta(seconds=retry_after)
                job.result_message = "rate_limited"
                job.last_error = None
            else:
                job.status = "skipped"
                job.result_message = str(response.get("reason") or status or "skipped")
                job.last_error = None
        except RuntimeError as exc:
            job.last_error = str(exc)
            if job.attempt_count >= _WIRE_MAX_ATTEMPTS:
                job.status = "failed"
                failed += 1
            else:
                job.status = "queued"
                job.scheduled_for = now + timedelta(minutes=15)
                job.result_message = "retry_scheduled"
    db.commit()
    return {"posted": posted, "failed": failed}
