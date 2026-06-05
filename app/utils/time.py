from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def to_local(dt: datetime) -> datetime:
    settings = get_settings()
    zone = ZoneInfo(settings.timezone)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone)
    return dt.astimezone(zone)
