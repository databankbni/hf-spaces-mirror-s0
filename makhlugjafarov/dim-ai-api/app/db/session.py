from dataclasses import dataclass

import psycopg

from app.core.config import Settings


@dataclass(frozen=True)
class DatabaseHealth:
    status: str
    detail: str | None = None


class Database:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def healthcheck(self) -> DatabaseHealth:
        if not self._settings.database_url:
            return DatabaseHealth(status="not_configured")

        try:
            with psycopg.connect(self._settings.database_url, connect_timeout=3) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("select 1")
                    cursor.fetchone()
            return DatabaseHealth(status="ok")
        except psycopg.Error as exc:
            return DatabaseHealth(status="error", detail=exc.__class__.__name__)


def get_database(settings: Settings) -> Database:
    return Database(settings)
