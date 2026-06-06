from app.database.base import Base
from app.database.connection import engine

from app.models.client import Client


def init_db():
    Base.metadata.create_all(bind=engine)