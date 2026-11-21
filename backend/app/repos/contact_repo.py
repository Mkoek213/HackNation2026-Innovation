"""Contact form messages: stored first, then marked when they were also e-mailed to the operator."""
from sqlalchemy import func, select, update

from app.models import ContactMessage
from app.schemas.contact import ContactModel
from app.schemas.default import ItemList
from app.utils.crud_repo import CRUDRepo


class ContactRepo(CRUDRepo[ContactMessage, ContactModel]):
    async def newest(self, *, limit: int | None = None, offset: int = 0) -> ItemList[ContactModel]:
        query = (select(ContactMessage).order_by(ContactMessage.created_at.desc(), ContactMessage.id.desc())
                 .offset(offset).limit(limit))
        total = await self.db.scalar(select(func.count()).select_from(ContactMessage))
        items = (await self.db.scalars(query)).all()
        return ItemList[ContactModel](total=total, items=[*items])

    async def mark_delivered(self, message_id: int) -> None:
        await self.db.execute(update(ContactMessage).where(ContactMessage.id == message_id).values(delivered=True))
        await self.db.commit()
