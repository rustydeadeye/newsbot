from contextlib import asynccontextmanager
import logging
import logging.config

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


def _run_pipeline() -> None:
    from app.workers.runner import run_cycle
    try:
        result = run_cycle()
        logging.getLogger(__name__).info("pipeline cycle complete: %s", result)
    except Exception:
        logging.getLogger(__name__).exception("pipeline cycle failed")


def _run_engagement_fetch() -> None:
    from app.workers.runner import run_engagement_fetch
    try:
        count = run_engagement_fetch()
        if count:
            logging.getLogger(__name__).info("engagement fetch complete: fetched=%d", count)
    except Exception:
        logging.getLogger(__name__).exception("engagement fetch failed")


def _run_wire_feed() -> None:
    from app.wire_feed.runner import run_wire_cycle

    try:
        result = run_wire_cycle()
        logging.getLogger(__name__).info("wire feed cycle complete: %s", result)
    except Exception:
        logging.getLogger(__name__).exception("wire feed cycle failed")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = get_settings()
    scheduler = BackgroundScheduler(daemon=True)
    if settings.pipeline_enabled:
        scheduler.add_job(
            _run_pipeline,
            trigger="interval",
            seconds=settings.pipeline_interval_sec,
            id="pipeline_cycle",
            max_instances=1,
            coalesce=True,
        )
    if settings.engagement_fetch_enabled:
        scheduler.add_job(
            _run_engagement_fetch,
            trigger="interval",
            hours=1,
            id="engagement_fetch",
            max_instances=1,
            coalesce=True,
        )
    if settings.wire_feed_enabled:
        scheduler.add_job(
            _run_wire_feed,
            trigger="interval",
            seconds=settings.wire_feed_interval_sec,
            id="wire_feed_cycle",
            max_instances=1,
            coalesce=True,
        )
    scheduler.start()
    logging.getLogger(__name__).info(
        "Scheduler started — pipeline enabled=%s interval=%ds, engagement enabled=%s every 1h, wire feed enabled=%s interval=%ds",
        settings.pipeline_enabled,
        settings.pipeline_interval_sec,
        settings.engagement_fetch_enabled,
        settings.wire_feed_enabled,
        settings.wire_feed_interval_sec,
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
