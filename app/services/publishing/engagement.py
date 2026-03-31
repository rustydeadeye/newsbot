from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.repositories.creators import CreatorSettingsRepository
from app.repositories.jobs import PublishLogRepository
from app.services.publishing.x_client import XPublisher

logger = logging.getLogger(__name__)


def fetch_pending_engagement(db: Session) -> int:
    """Fetch X engagement metrics for posts older than 24 hours that haven't been fetched yet."""
    creator_settings = CreatorSettingsRepository(db).get_primary()
    token_store = creator_settings.token_store if creator_settings else {}

    publisher = XPublisher(token_store=token_store)
    log_repo = PublishLogRepository(db)

    logs = log_repo.list_needing_engagement_fetch()
    if not logs:
        return 0

    fetched = 0
    for log in logs:
        if not log.platform_post_id:
            continue
        metrics = publisher.fetch_tweet_metrics(log.platform_post_id)
        log.engagement_fetched_at = datetime.now(timezone.utc)
        if metrics:
            log.engagement_stats = metrics
            logger.info(
                "post_id=%s engagement: likes=%s retweets=%s impressions=%s",
                log.platform_post_id,
                metrics.get("like_count", 0),
                metrics.get("retweet_count", 0),
                metrics.get("impression_count", 0),
            )
        else:
            log.engagement_stats = {}
            logger.debug("post_id=%s no metrics returned", log.platform_post_id)
        fetched += 1

    db.commit()
    logger.info("fetch_pending_engagement fetched=%d", fetched)
    return fetched
