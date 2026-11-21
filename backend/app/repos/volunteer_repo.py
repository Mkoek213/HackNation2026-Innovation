from sqlalchemy import String, cast, delete, func, select, update

from app.models import Tag, User
from app.models.volunteer import VolunteerProfile, VolunteerTag
from app.repos.tag_repo import TagRepo
from app.schemas.default import Delete, ItemList
from app.schemas.volunteer import VolunteerInput, VolunteerLabel, VolunteerModel
from app.services.chat_engine import TagOption
from app.services.tagging import classify
from app.utils.crud_repo import CRUDRepo


class VolunteerRepo(CRUDRepo[VolunteerProfile, VolunteerModel]):
    async def model(self, profile: VolunteerProfile) -> VolunteerModel:
        tags = (await self.db.execute(
            select(Tag.id, Tag.name).join(VolunteerTag, VolunteerTag.tag_id == Tag.id)
            .where(VolunteerTag.user_id == profile.user_id).order_by(Tag.name)
        )).all()
        return VolunteerModel(
            **profile.to_dict(exclude={"classification", "consented_at"}),
            tags=[VolunteerLabel(id=id, name=name) for id, name in tags],
            tagging_status=(profile.classification or {}).get("status", "unavailable"),
        )

    async def mine(self, user_id: int) -> VolunteerModel | None:
        profile = await self.get_one(user_id=user_id, quiet=True)
        return await self.model(profile) if profile else None

    async def put_mine(self, user_id: int, data: VolunteerInput) -> VolunteerModel:
        tags = await TagRepo(self.db).get_all_nested()
        options = [TagOption(t.id, t.name, t.description) for t in tags]
        await self.db.commit()  # Do not hold a database transaction during inference.
        result = await classify(data.description, options, purpose=(
            "volunteer's explicitly stated interests and experience; do not infer age, health or other personal traits"
        ))
        # Serialize profile writes/withdrawal for this account, including first creation.
        await self.db.execute(update(User).where(User.id == user_id).values(username=User.username))
        profile = await self.get_one(user_id=user_id, quiet=True)
        changed = profile is None or profile.description != data.description
        if profile is None:
            profile = VolunteerProfile(user_id=user_id)
            self.db.add(profile)
        profile.email, profile.phone, profile.description = data.email, data.phone, data.description
        profile.roles, profile.interests = [str(r) for r in data.roles], [str(i) for i in data.interests]
        profile.classification = result.model_dump(mode="json")
        await self.db.flush()
        if changed or result.status == "completed":
            # Changed descriptions must not keep obsolete labels when inference fails.
            await self.db.execute(delete(VolunteerTag).where(VolunteerTag.user_id == user_id))
            if result.status == "completed":
                valid = set(await self.db.scalars(select(Tag.id)))
                self.db.add_all([VolunteerTag(user_id=user_id, tag_id=d.tag_id)
                                 for d in result.decisions if d.selected and d.tag_id in valid])
        await self.db.commit()
        await self.db.refresh(profile)
        return await self.model(profile)

    async def withdraw(self, user_id: int) -> Delete:
        await self.db.execute(update(User).where(User.id == user_id).values(username=User.username))
        # Explicit removal works even in SQLite sessions without FK pragmas.
        await self.db.execute(delete(VolunteerTag).where(VolunteerTag.user_id == user_id))
        result = await self.db.execute(delete(VolunteerProfile).where(VolunteerProfile.user_id == user_id))
        await self.db.commit()
        return Delete(deleted=result.rowcount, detail="Removed volunteer profile.")

    async def list_pool(self, *, query: str, tag_id: int | None, role: str | None = None, interest: str | None = None,
                        limit: int, offset: int) -> ItemList[VolunteerModel]:
        filters = []
        # Slugs are validated enum values ([a-z-]), so a quoted text match on the JSON list is exact and portable.
        if role:
            filters.append(cast(VolunteerProfile.roles, String).contains(f'"{role}"'))
        if interest:
            filters.append(cast(VolunteerProfile.interests, String).contains(f'"{interest}"'))
        if query:
            filters.append(VolunteerProfile.description.icontains(query, autoescape=True))
        if tag_id is not None:
            filters.append(VolunteerProfile.user_id.in_(
                select(VolunteerTag.user_id).where(VolunteerTag.tag_id == tag_id)
            ))
        total = await self.db.scalar(select(func.count()).select_from(VolunteerProfile).where(*filters))
        profiles = await self.db.scalars(select(VolunteerProfile).where(*filters)
            .order_by(VolunteerProfile.created_at.desc(), VolunteerProfile.user_id.desc()).limit(limit).offset(offset))
        return ItemList[VolunteerModel](total=total, items=[await self.model(p) for p in profiles])
