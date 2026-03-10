from __future__ import annotations

from app.database.engine import engine
from app.database.models import Base


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()

