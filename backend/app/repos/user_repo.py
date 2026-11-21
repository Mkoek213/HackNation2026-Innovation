from sqlalchemy import select

from app.exceptions import DuplicateError
from app.models import User
from app.schemas.user import UserCreate, UserModel, UserRegister, UserUpdate
from app.utils.auth import hash_password
from app.utils.crud_repo import CRUDRepo


class UserRepo(CRUDRepo[User, UserModel]):

    async def get_by_username(self, username: str) -> User | None:
        query = select(User).where(User.username == username)
        return await self.db.scalar(query)

    async def get_by_email(self, email: str) -> User | None:
        query = select(User).where(User.email == email.lower())
        return await self.db.scalar(query)

    async def _assert_username_free(self, username: str, *, exclude_id: int | None = None) -> None:
        existing = await self.get_by_username(username)
        if existing is not None and existing.id != exclude_id:
            raise DuplicateError(resource="User", field="username", value=username)

    async def _assert_email_free(self, email: str | None, *, exclude_id: int | None = None) -> None:
        if email is None:
            return
        existing = await self.get_by_email(email)
        if existing is not None and existing.id != exclude_id:
            raise DuplicateError(resource="User", field="email", value=email)

    async def create_user(self, user: UserCreate, *, autocommit: bool = True) -> User:
        """Hashes the password -- the input field (password) doesn't match
        the column (hashed_password), so it is excluded from the generic create()."""
        await self._assert_username_free(user.username)
        await self._assert_email_free(user.email)
        return await self.create(
            user,
            exclude={"password"},
            hashed_password=hash_password(user.password),
            autocommit=autocommit,
        )

    async def register(self, data: UserRegister, *, autocommit: bool = True) -> User:
        """Self-registration with the role chosen by the caller (demo only)."""
        return await self.create_user(
            UserCreate(username=data.username, email=data.email, password=data.password, role=data.role),
            autocommit=autocommit,
        )

    async def update_user(self, user: UserUpdate, *, autocommit: bool = True, **kwargs) -> User:
        data = user.model_dump_null()
        if "username" in data:
            await self._assert_username_free(data["username"], exclude_id=kwargs.get("id"))
        if "email" in data:
            await self._assert_email_free(data["email"], exclude_id=kwargs.get("id"))
        if "password" in data:
            data["hashed_password"] = hash_password(data.pop("password"))
        return await self.update(data, key_loc="path", autocommit=autocommit, **kwargs)

    async def set_password(self, user: User, password: str, *, autocommit: bool = True) -> User:
        user.hashed_password = hash_password(password)
        await (self.db.commit() if autocommit else self.db.flush())
        return user
