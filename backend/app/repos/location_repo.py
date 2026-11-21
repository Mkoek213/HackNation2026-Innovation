from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import Select, func, or_, select

from app.exceptions import ValidationError
from app.models import Location, LocationKind
from app.schemas.default import ItemList
from app.schemas.geojson import Feature, FeatureCollection, point
from app.schemas.location import LocationImport, LocationModel, LocationProperties
from app.utils.crud_repo import CRUDRepo


@dataclass(frozen=True)
class ImportResult:
    created: int
    updated: int
    unchanged: int


class LocationRepo(CRUDRepo[Location, LocationModel]):

    @staticmethod
    def _filtered(
            query: Select,
            *,
            kind: LocationKind | None = None,
            parent_id: int | None = None,
            q: str | None = None,
    ) -> Select:
        if kind is not None:
            query = query.where(Location.kind == kind)
        if parent_id is not None:
            query = query.where(Location.parent_id == parent_id)
        if q:
            query = query.where(or_(
                Location.name.icontains(q, autoescape=True),
                Location.teryt_code.startswith(q, autoescape=True),
            ))
        return query

    async def search(
            self,
            *,
            kind: LocationKind | None = None,
            parent_id: int | None = None,
            q: str | None = None,
            limit: int | None = None,
            offset: int = 0,
    ) -> ItemList[LocationModel]:
        """Locations for pickers, ordered by name; `q` matches a name fragment
        (case-insensitive) or a TERYT code prefix."""
        filters = dict(kind=kind, parent_id=parent_id, q=q)
        query = self._filtered(select(Location), **filters).order_by(Location.name, Location.id)
        query = query.offset(offset).limit(limit)
        total = await self.db.scalar(self._filtered(select(func.count()).select_from(Location), **filters))
        items = (await self.db.scalars(query)).all()
        return ItemList[LocationModel](total=total, items=[*items])

    async def geojson(
            self,
            *,
            kind: LocationKind | None = None,
            parent_id: int | None = None,
    ) -> FeatureCollection[LocationProperties]:
        """All matching locations as GeoJSON features. The geometry is the
        boundary, or the centroid as a Point when no boundary is stored."""
        query = self._filtered(select(Location), kind=kind, parent_id=parent_id).order_by(Location.teryt_code)
        rows = (await self.db.scalars(query)).all()
        return FeatureCollection[LocationProperties](features=[
            Feature[LocationProperties](
                geometry=row.boundary or point(row.longitude, row.latitude),
                properties=LocationProperties.model_validate(row),
            )
            for row in rows
        ])

    async def import_locations(self, items: Sequence[LocationImport], *, autocommit: bool = True) -> ImportResult:
        """
        Idempotent upsert keyed by `teryt_code`, used by `scripts/seed_locations.py`.
        `parent_id` is set from the TERYT prefix (gmina -> powiat -> voivodeship);
        the parent must be in `items` or already in the database.
        Rows that are not in `items` are left untouched.
        :raises ValidationError: On a duplicate code in `items` or a missing parent.
        """
        codes = [item.teryt_code for item in items]
        if len(codes) != len(set(codes)):
            duplicates = sorted({c for c in codes if codes.count(c) > 1})
            raise ValidationError(msg=f"Duplicate TERYT codes: {duplicates}.", loc=("teryt_code",))

        existing = {row.teryt_code: row for row in (await self.db.scalars(select(Location))).all()}
        created = updated = unchanged = 0

        # Shorter codes are parents of longer ones, so parents are flushed first.
        for item in sorted(items, key=lambda i: len(i.teryt_code)):
            parent_code = item.parent_teryt_code
            parent = existing.get(parent_code) if parent_code else None
            if parent_code and parent is None:
                raise ValidationError(
                    msg=f"Parent {parent_code} of {item.teryt_code} ({item.name}) is missing.",
                    loc=("teryt_code",),
                    input_=item.teryt_code,
                )
            data = item.model_dump()
            data["parent_id"] = parent.id if parent else None

            row = existing.get(item.teryt_code)
            if row is None:
                row = Location(**data)
                self.db.add(row)
                created += 1
            elif all(getattr(row, k) == v for k, v in data.items()):
                unchanged += 1
                continue
            else:
                for k, v in data.items():
                    setattr(row, k, v)
                updated += 1
            await self.db.flush()
            existing[item.teryt_code] = row

        if autocommit:
            await self.db.commit()
        return ImportResult(created=created, updated=updated, unchanged=unchanged)
