from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class FetchedItem:
    external_id: str
    url: str
    title: str
    published_at: datetime | None
    raw_payload: dict
