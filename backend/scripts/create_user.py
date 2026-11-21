"""
Creates a user, or resets an existing one's password. Useful for creating
the first admin without ADMIN_USERNAME / ADMIN_PASSWORD -- run this directly
on the server / inside the container:

    python scripts/create_user.py [--admin]
"""
import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError  # noqa: E402

from app.database.database import sessionmanager  # noqa: E402
from app.repos.user_repo import UserRepo  # noqa: E402
from app.models import UserRole  # noqa: E402
from app.schemas.user import UserCreate  # noqa: E402


async def main() -> None:
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Confirm password: "):
        print("Passwords do not match.", file=sys.stderr)
        sys.exit(1)

    try:
        role = UserRole.admin if "--admin" in sys.argv[1:] else UserRole.user
        creds = UserCreate(username=username, password=password, role=role)
    except ValidationError as e:
        print(f"Invalid input: {e}", file=sys.stderr)
        sys.exit(1)

    await sessionmanager.init_db()
    try:
        # Create-if-missing, non-destructive -- so this script works before
        # the app has ever been started.
        await sessionmanager.create_db()

        async with sessionmanager.session_maker() as db:
            repo = UserRepo(db)
            existing = await repo.get_by_username(creds.username)
            if existing is not None:
                answer = input(f"User {creds.username!r} already exists. Reset password? [y/N] ").strip().lower()
                if answer != "y":
                    print("Aborted.")
                    return
                await repo.set_password(existing, creds.password)
                print(f"Password reset for {existing.username!r}.")
                return

            user = await repo.create_user(creds)
            print(f"Created {user.role} {user.username!r} (id={user.id}).")
    finally:
        await sessionmanager.close()


if __name__ == "__main__":
    asyncio.run(main())
