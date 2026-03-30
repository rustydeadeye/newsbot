from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.creator import CreatorSettings


class CreatorSettingsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_primary(self) -> CreatorSettings | None:
        stmt = select(CreatorSettings).order_by(CreatorSettings.id).limit(1)
        return self.db.scalar(stmt)

    def get_or_create_default(self) -> CreatorSettings:
        settings = self.get_primary()
        if settings:
            return settings
        settings = CreatorSettings(display_name="Default Creator")
        self.db.add(settings)
        self.db.flush()
        return settings

    def update(self, settings: CreatorSettings, payload: dict) -> CreatorSettings:
        for key, value in payload.items():
            setattr(settings, key, value)
        self.db.flush()
        return settings
