from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator

from app.models.user import UserRole


class UserCreate(BaseModel):
    """Criação de usuário dentro da empresa (por OWNER/ADMIN)."""

    nome: str
    email: EmailStr
    senha: str
    role: str = UserRole.ATTENDANT.value

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        valid = {r.value for r in UserRole}
        if v not in valid:
            raise ValueError(f"Papel inválido. Use um de: {', '.join(sorted(valid))}")
        return v


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    nome: str
    email: EmailStr
    role: str
    ativo: bool
    created_at: datetime
