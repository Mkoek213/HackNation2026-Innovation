from enum import StrEnum

from sqlalchemy import Enum
from sqlalchemy.orm import mapped_column, Mapped

from app.database.database import Base, BigIntPK


class UserRole(StrEnum):
    admin = "admin"
    user = "user"


class User(Base):
    """
    Application login accounts.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    username: Mapped[str] = mapped_column(unique=True)
    hashed_password: Mapped[str] = mapped_column()
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False, length=16, create_constraint=True),
        default=UserRole.user,
    )
    # Stored lowercased (see schemas.user); NULL for accounts created without one.
    email: Mapped[str | None] = mapped_column(unique=True, default=None)

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.admin
