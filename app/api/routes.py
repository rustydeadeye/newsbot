from fastapi import APIRouter

from app.api.views import auth, events, health, jobs, onboarding, pipeline, review, settings, sources

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(jobs.router, prefix="/publish-jobs", tags=["publish-jobs"])
api_router.include_router(review.router, prefix="/review", tags=["review"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(pipeline.router, prefix="/pipeline", tags=["pipeline"])
