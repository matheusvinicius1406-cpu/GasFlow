import enum

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String

from app.database.base import Base
from app.models.mixins import TimestampMixin


class UserRole(str, enum.Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    ATTENDANT = "ATTENDANT"
    DRIVER = "DRIVER"


# Hierarquia de papéis: valores maiores incluem as permissões dos menores.
ROLE_LEVELS = {
    UserRole.DRIVER.value: 1,
    UserRole.ATTENDANT.value: 2,
    UserRole.ADMIN.value: 3,
    UserRole.OWNER.value: 4,
}


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(ForeignKey("companies.id"), index=True, nullable=False)

    nome = Column(String, nullable=False)
    # Email é a identidade de login: único globalmente (uma conta por email).
    email = Column(String, nullable=False, unique=True, index=True)
    senha_hash = Column(String, nullable=False)

    role = Column(String, default=UserRole.ATTENDANT.value, nullable=False)

    ativo = Column(Boolean, default=True, nullable=False)
