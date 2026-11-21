import logging
import uuid
from typing import Any, BinaryIO, Literal, Sequence

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.exceptions import DependencyUnavailable, DomainError, NotFoundError, ValidationError
from app.models import (
    Location,
    LocationKind,
    Project,
    ProjectDocument,
    ProjectParticipant,
    ProjectReview,
    ProjectStatus,
    Subtag,
)
from app.repos.location_repo import LocationRepo
from app.repos.tag_repo import TagRepo
from app.schemas.default import ItemList
from app.schemas.geojson import Feature, FeatureCollection, point
from app.schemas.project import (
    ParticipantInput,
    ParticipantModel,
    ParticipantProperties,
    ParticipantsByLocation,
    ParticipantsSummary,
    ProjectCreate,
    ProjectDetail,
    ProjectDocumentModel,
    ProjectModel,
    ProjectProperties,
    ProjectUpdate,
)
from app.services.files import FileStorage
from app.utils.crud_repo import CRUDRepo

logger = logging.getLogger(__name__)

PDF_CONTENT_TYPE = "application/pdf"
PDF_MAGIC = b"%PDF-"

#: `?level=` of the participants endpoints: None keeps the stored locations,
#: "county" sums municipalities into their county (powiat).
ParticipantsLevel = Literal["county"] | None


async def delete_stored_files(storage: FileStorage, keys: Sequence[str]) -> None:
    """Removes stored files after their rows are gone (committed). Best effort: a storage
    failure only leaves orphaned objects in the bucket, so it is logged, not raised."""
    for key in keys:
        try:
            await storage.delete(key)
        except DependencyUnavailable:
            logger.warning("Could not delete stored file %s; it is left orphaned.", key)


async def average_rating(db: AsyncSession, project_id: int) -> float | None:
    """The project's average review rating rounded to 2 decimals; None without reviews."""
    avg = await db.scalar(select(func.avg(ProjectReview.rating)).where(ProjectReview.project_id == project_id))
    return None if avg is None else round(float(avg), 2)


class FileTooLargeError(DomainError):
    status_code = 413
    type = "file_too_large"


class ProjectRepo(CRUDRepo[Project, ProjectModel]):
    # Documents and participants are removed with the project (ON DELETE CASCADE);
    # a project recommended in conversations is kept for the statistics (unpublish it instead).
    protect_on_delete = ("matches",)

    @staticmethod
    def _filtered(
            query: Select,
            *,
            include_drafts: bool,
            status: ProjectStatus | None = None,
            tag_id: int | None = None,
            subtag_id: int | None = None,
            location_id: int | None = None,
            q: str | None = None,
    ) -> Select:
        if not include_drafts:
            query = query.where(Project.status == ProjectStatus.published)
        elif status is not None:
            query = query.where(Project.status == status)
        if tag_id is not None:
            query = query.where(Project.tag_id == tag_id)
        if subtag_id is not None:
            query = query.where(Project.subtag_id == subtag_id)
        if location_id is not None:
            # The location itself and the units inside it (county -> municipalities,
            # voivodeship -> counties -> municipalities).
            child, grandchild = aliased(Location), aliased(Location)
            children = select(child.id).where(child.parent_id == location_id)
            grandchildren = (
                select(grandchild.id)
                .join(child, grandchild.parent_id == child.id)
                .where(child.parent_id == location_id)
            )
            query = query.where(or_(
                Project.location_id == location_id,
                Project.location_id.in_(children),
                Project.location_id.in_(grandchildren),
            ))
        if q:
            query = query.where(or_(
                Project.title.icontains(q, autoescape=True),
                Project.summary.icontains(q, autoescape=True),
            ))
        return query

    async def search(
            self,
            *,
            include_drafts: bool = False,
            status: ProjectStatus | None = None,
            tag_id: int | None = None,
            subtag_id: int | None = None,
            location_id: int | None = None,
            q: str | None = None,
            limit: int | None = None,
            offset: int = 0,
    ) -> ItemList[ProjectModel]:
        """Projects, newest first. Only published ones unless `include_drafts` (admin),
        which also enables the `status` filter. `location_id` includes the units inside
        that location; `q` matches a title or summary fragment (case-insensitive)."""
        filters = dict(
            include_drafts=include_drafts, status=status, tag_id=tag_id,
            subtag_id=subtag_id, location_id=location_id, q=q,
        )
        query = self._filtered(select(Project), **filters).order_by(Project.id.desc())
        query = query.offset(offset).limit(limit)
        total = await self.db.scalar(self._filtered(select(func.count()).select_from(Project), **filters))
        items = (await self.db.scalars(query)).all()
        return ItemList[ProjectModel](total=total, items=[*items])

    async def get_visible(self, project_id: int, *, include_drafts: bool) -> Project:
        """The project, hidden (404) while it is a draft unless `include_drafts` (admin).
        :raises NotFoundError: missing or hidden."""
        project = await self.get_one(id=project_id, key_loc="path")
        if project.status != ProjectStatus.published and not include_drafts:
            raise NotFoundError(resource="Project", key={"id": project_id}, loc=("path", "id"))
        return project

    async def detail(self, project: Project) -> ProjectDetail:
        documents = (await self.db.scalars(
            select(ProjectDocument).where(ProjectDocument.project_id == project.id).order_by(ProjectDocument.id)
        )).all()
        total = await self.db.scalar(
            select(func.coalesce(func.sum(ProjectParticipant.participants_count), 0))
            .where(ProjectParticipant.project_id == project.id)
        )
        return ProjectDetail(
            **ProjectModel.model_validate(project).model_dump(),
            description=project.description,
            documents=[ProjectDocumentModel.model_validate(d) for d in documents],
            participants_total=total,
            rating_avg=await average_rating(self.db, project.id),
        )

    async def _validate(self, data: dict[str, Any]) -> None:
        """Checks references and invariants of the full (merged) project data."""
        await TagRepo(self.db).get_one(id=data["tag_id"], key_loc="body")
        if data.get("subtag_id") is not None:
            subtag = await self.db.get(Subtag, data["subtag_id"])
            if subtag is None:
                raise NotFoundError(resource="Subtag", key={"id": data["subtag_id"]}, loc=("body", "subtag_id"))
            if subtag.tag_id != data["tag_id"]:
                raise ValidationError(
                    msg=f"Subtag {subtag.id} does not belong to tag {data['tag_id']}.",
                    loc=("body", "subtag_id"),
                    input_=subtag.id,
                )
        if data.get("location_id") is not None:
            await LocationRepo(self.db).get_one(id=data["location_id"], key_loc="body")
        if (data.get("latitude") is None) != (data.get("longitude") is None):
            raise ValidationError(
                msg="Set both latitude and longitude, or neither.",
                loc=("body", "latitude" if data.get("latitude") is None else "longitude"),
            )

    async def create_project(self, project: ProjectCreate, *, autocommit: bool = True) -> Project:
        """Creates a draft project.
        :raises NotFoundError: unknown tag, subtag or location.
        :raises ValidationError: subtag of another tag, or only one coordinate."""
        await self._validate(project.model_dump())
        obj = await self.create(project, status=ProjectStatus.draft, autocommit=autocommit)
        await self.db.refresh(obj)
        return obj

    async def update_project(self, changes: ProjectUpdate, *, autocommit: bool = True, **kwargs) -> Project:
        """Applies a partial update, validating the resulting project as a whole.
        :raises NotFoundError: missing project, or unknown tag, subtag or location.
        :raises ValidationError: see create_project."""
        data = changes.model_dump_null()
        project = await self.get_one(key_loc="path", **kwargs)
        await self._validate(project.to_dict() | data)
        return await self.update(data, key_loc="path", autocommit=autocommit, **kwargs)

    async def delete_project(self, project_id: int, storage: FileStorage) -> None:
        """Deletes the project with its documents, participants and stored PDF files."""
        await self.get_one(id=project_id, key_loc="path")
        keys = (await self.db.scalars(
            select(ProjectDocument.file_path).where(ProjectDocument.project_id == project_id)
        )).all()
        await self.delete_one(id=project_id, key_loc="path")
        await delete_stored_files(storage, keys)

    async def geojson(
            self,
            *,
            tag_id: int | None = None,
            subtag_id: int | None = None,
    ) -> FeatureCollection[ProjectProperties]:
        """Published projects as Point features at their own coordinates, or their
        location's centroid; projects with neither are left out."""
        query = (
            self._filtered(
                select(Project, Location.latitude, Location.longitude),
                include_drafts=False, tag_id=tag_id, subtag_id=subtag_id,
            )
            .outerjoin(Location, Project.location_id == Location.id)
            .order_by(Project.id)
        )
        features = []
        for project, location_lat, location_lon in (await self.db.execute(query)).all():
            if project.latitude is not None and project.longitude is not None:
                geometry = point(project.longitude, project.latitude)
            elif location_lat is not None:
                geometry = point(location_lon, location_lat)
            else:
                continue
            features.append(Feature[ProjectProperties](
                geometry=geometry,
                properties=ProjectProperties.model_validate(project),
            ))
        return FeatureCollection[ProjectProperties](features=features)


class ProjectDocumentRepo(CRUDRepo[ProjectDocument, ProjectDocumentModel]):

    async def get_for_project(self, project_id: int, document_id: int) -> ProjectDocument:
        """:raises NotFoundError: missing, or attached to another project."""
        document = await self.get_one(id=document_id, quiet=True)
        if document is None or document.project_id != project_id:
            raise NotFoundError(
                resource="ProjectDocument", key={"id": document_id}, loc=("path", "document_id"),
            )
        return document

    async def upload(
            self,
            project_id: int,
            title: str,
            stream: BinaryIO,
            content_type: str | None,
            size: int | None,
            storage: FileStorage,
            *,
            max_bytes: int,
    ) -> ProjectDocument:
        """
        Stores a PDF under `projects/{project_id}/{uuid}.pdf` and records it.
        :raises NotFoundError: missing project.
        :raises ValidationError: not a PDF (content type or file signature).
        :raises FileTooLargeError: larger than `max_bytes`.
        """
        await ProjectRepo(self.db).get_one(id=project_id, key_loc="path")
        if content_type != PDF_CONTENT_TYPE:
            raise ValidationError(
                msg="Only PDF files (application/pdf) can be uploaded.",
                loc=("body", "file"),
                input_=content_type,
            )
        if size is None:
            size = stream.seek(0, 2)
        if size > max_bytes:
            raise FileTooLargeError(
                msg=f"The file is larger than the {max_bytes} byte limit.",
                loc=("body", "file"),
                max_bytes=max_bytes,
            )
        stream.seek(0)
        signature = stream.read(len(PDF_MAGIC))
        stream.seek(0)
        if signature != PDF_MAGIC:
            raise ValidationError(msg="The file is not a valid PDF.", loc=("body", "file"))

        key = f"projects/{project_id}/{uuid.uuid4()}.pdf"
        stored = await storage.save(key, stream, PDF_CONTENT_TYPE)
        try:
            document = ProjectDocument(
                project_id=project_id, title=title, file_path=stored.key, size_bytes=stored.size_bytes,
            )
            self.db.add(document)
            await self.db.commit()
            await self.db.refresh(document)
        except BaseException:
            await delete_stored_files(storage, [stored.key])
            raise
        return document

    async def delete_document(self, project_id: int, document_id: int, storage: FileStorage) -> None:
        document = await self.get_for_project(project_id, document_id)
        key = document.file_path
        await self.db.delete(document)
        await self.db.commit()
        await delete_stored_files(storage, [key])


class ProjectParticipantRepo(CRUDRepo[ProjectParticipant, ParticipantModel]):

    async def _aggregate(
            self, project_id: int, level: ParticipantsLevel,
    ) -> list[tuple[Location | None, int]]:
        """(location, count) pairs; `None` is the unknown origin. With `level="county"`,
        municipality rows are summed into their parent county."""
        rows = (await self.db.execute(
            select(ProjectParticipant.participants_count, Location)
            .outerjoin(Location, ProjectParticipant.location_id == Location.id)
            .where(ProjectParticipant.project_id == project_id)
        )).all()

        targets: dict[int, Location] = {}
        if level == "county":
            parent_ids = {
                loc.parent_id for _, loc in rows
                if loc is not None and loc.kind == LocationKind.municipality and loc.parent_id is not None
            }
            if parent_ids:
                parents = (await self.db.scalars(select(Location).where(Location.id.in_(parent_ids)))).all()
                targets = {p.id: p for p in parents}

        counts: dict[int | None, int] = {}
        locations: dict[int, Location] = {}
        for count, loc in rows:
            if loc is not None and level == "county" and loc.kind == LocationKind.municipality and loc.parent_id:
                loc = targets[loc.parent_id]
            key = loc.id if loc is not None else None
            if loc is not None:
                locations[loc.id] = loc
            counts[key] = counts.get(key, 0) + count

        result = [(locations[k] if k is not None else None, c) for k, c in counts.items()]
        # Largest first, then by name; the unknown origin last.
        result.sort(key=lambda lc: (lc[0] is None, -lc[1], lc[0].name if lc[0] else ""))
        return result

    async def summary(self, project_id: int, *, level: ParticipantsLevel = None) -> ParticipantsSummary:
        pairs = await self._aggregate(project_id, level)
        return ParticipantsSummary(
            total=sum(c for _, c in pairs),
            by_location=[
                ParticipantsByLocation(
                    location_id=loc.id if loc else None,
                    name=loc.name if loc else None,
                    teryt_code=loc.teryt_code if loc else None,
                    kind=loc.kind if loc else None,
                    count=count,
                )
                for loc, count in pairs
            ],
        )

    async def geojson(self, project_id: int, *, level: ParticipantsLevel = None) -> FeatureCollection[ParticipantProperties]:
        """Known locations as features (boundary, or centroid Point) with `count` in `properties`.
        The unknown origin has no geometry and is only in the JSON summary."""
        pairs = await self._aggregate(project_id, level)
        return FeatureCollection[ParticipantProperties](features=[
            Feature[ParticipantProperties](
                geometry=loc.boundary or point(loc.longitude, loc.latitude),
                properties=ParticipantProperties(
                    id=loc.id, name=loc.name, teryt_code=loc.teryt_code, kind=loc.kind, count=count,
                ),
            )
            for loc, count in pairs
            if loc is not None
        ])

    async def replace(self, project_id: int, items: Sequence[ParticipantInput], *, autocommit: bool = True) -> None:
        """
        Replaces the project's participant rows with `items` (one per location).
        :raises NotFoundError: missing project or location.
        :raises ValidationError: the same location twice.
        """
        await ProjectRepo(self.db).get_one(id=project_id, key_loc="path")

        seen: set[int | None] = set()
        for i, item in enumerate(items):
            if item.location_id in seen:
                raise ValidationError(
                    msg=f"Location {item.location_id} is listed more than once.",
                    loc=("body", i, "location_id"),
                    input_=item.location_id,
                )
            seen.add(item.location_id)

        location_ids = {i.location_id for i in items if i.location_id is not None}
        if location_ids:
            found = set((await self.db.scalars(select(Location.id).where(Location.id.in_(location_ids)))).all())
            for i, item in enumerate(items):
                if item.location_id is not None and item.location_id not in found:
                    raise NotFoundError(
                        resource="Location", key={"id": item.location_id}, loc=("body", i, "location_id"),
                    )

        existing = {row.location_id: row for row in await self.get_multiple(project_id=project_id)}
        for item in items:
            row = existing.pop(item.location_id, None)
            if row is None:
                self.db.add(ProjectParticipant(
                    project_id=project_id, location_id=item.location_id,
                    participants_count=item.participants_count,
                ))
            elif row.participants_count != item.participants_count:
                row.participants_count = item.participants_count
        for row in existing.values():
            await self.db.delete(row)
        await (self.db.commit() if autocommit else self.db.flush())
