from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import logging
import logging.config
from threading import Lock, Thread

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.core.config import get_settings

_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "app": {"level": "DEBUG", "propagate": True},
    },
}

_wire_feed_guard = Lock()
_wire_feed_state = {
    "active": False,
    "started_at": None,
    "run_id": 0,
}


def _complete_wire_feed_run(run_id: int) -> None:
    from app.wire_feed.runner import run_wire_cycle

    try:
        result = run_wire_cycle()
        logging.getLogger(__name__).info("wire feed cycle complete: %s", result)
    except Exception:
        logging.getLogger(__name__).exception("wire feed cycle failed")
    finally:
        with _wire_feed_guard:
            if _wire_feed_state["run_id"] == run_id:
                _wire_feed_state["active"] = False
                _wire_feed_state["started_at"] = None


def _run_wire_feed() -> None:
    settings = get_settings()
    logger = logging.getLogger(__name__)
    now = datetime.now(timezone.utc)
    timeout = timedelta(seconds=settings.wire_feed_timeout_sec)

    with _wire_feed_guard:
        started_at = _wire_feed_state["started_at"]
        if _wire_feed_state["active"] and started_at is not None:
            runtime = now - started_at
            if runtime < timeout:
                logger.warning(
                    "wire feed cycle already running; skipping this trigger runtime_seconds=%s",
                    int(runtime.total_seconds()),
                )
                return
            logger.error(
                "wire feed cycle exceeded timeout; allowing a new run runtime_seconds=%s timeout_seconds=%s",
                int(runtime.total_seconds()),
                settings.wire_feed_timeout_sec,
            )
        _wire_feed_state["active"] = True
        _wire_feed_state["started_at"] = now
        _wire_feed_state["run_id"] = int(_wire_feed_state["run_id"]) + 1
        run_id = int(_wire_feed_state["run_id"])

    worker = Thread(
        target=_complete_wire_feed_run,
        args=(run_id,),
        name=f"wire-feed-cycle-{run_id}",
        daemon=True,
    )
    worker.start()


def _run_instagram_pipeline() -> None:
    from app.instagram_pipeline.runtime import run_instagram_publish_cycle

    try:
        result = run_instagram_publish_cycle()
        logging.getLogger(__name__).info("instagram publish cycle complete: %s", result)
    except Exception:
        logging.getLogger(__name__).exception("instagram publish cycle failed")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = get_settings()
    scheduler = BackgroundScheduler(daemon=True)
    if settings.wire_feed_enabled:
        scheduler.add_job(
            _run_wire_feed,
            trigger="interval",
            seconds=settings.wire_feed_interval_sec,
            id="wire_feed_cycle",
            max_instances=1,
            coalesce=False,
        )
    if settings.instagram_pipeline_enabled:
        scheduler.add_job(
            _run_instagram_pipeline,
            trigger="interval",
            seconds=settings.instagram_pipeline_interval_sec,
            id="instagram_publish_cycle",
            max_instances=1,
            coalesce=True,
        )
    scheduler.start()
    logging.getLogger(__name__).info(
        "Scheduler started — wire enabled=%s interval=%ds instagram enabled=%s instagram_interval=%ds",
        settings.wire_feed_enabled,
        settings.wire_feed_interval_sec,
        settings.instagram_pipeline_enabled,
        settings.instagram_pipeline_interval_sec,
    )
    yield
    scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    logging.config.dictConfig(_LOG_CONFIG)
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    return app


app = create_app()
