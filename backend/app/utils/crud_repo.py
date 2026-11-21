from typing import Type, Any, TypeVar, Literal, overload, Generic, Sequence, get_origin, get_args, Optional

from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import Base
from app.exceptions import NotFoundError, ValidationError, ConflictError, DomainError, DomainErrorGroup
from app.schemas.default import ItemList, Delete, BatchResult
from app.utils.schemas_decorators import UpdateModel


BaseT = TypeVar("BaseT", bound=Base)
BaseModelT = TypeVar("BaseModelT", bound=BaseModel)


class CRUDRepo(Generic[BaseT, BaseModelT]):
    """
    Generic CRUD repository bound to a single SQLAlchemy model.

    Subclasses only need to parametrize the generic; the remaining class
    attributes are derived in ``__init_subclass__``::

        class CourseRepo(CRUDRepo[Course, CourseRead]):
            protect_on_delete = ("class_types",)

    One instance per session — repositories are cheap, do not cache them
    across requests.
    """

    #: SQLAlchemy model this repository operates on. Resolved from the
    #: generic parameter unless set explicitly.
    db_type: Type[BaseT]

    #: Pydantic schema used to serialize rows in list/batch responses.
    #: Resolved from the generic parameter unless set explicitly.
    py_type: Type[BaseModelT]

    #: ``ItemList[py_type]``, parametrized once at class creation so
    #: ``get_all`` does not rebuild the alias on every call.
    item_list_type: Type[ItemList]

    #: ``BatchResult[py_type]``, parametrized once at class creation and
    #: returned by :meth:`sync` and :meth:`upsert`.
    batch_result_type: Type[BatchResult]

    #: Names of relationships that block deletion of a parent row. When a
    #: relationship listed here has any children, :meth:`delete_one` raises
    #: ``ConflictError`` instead of letting the database reject the DELETE,
    #: which yields a far better message than SQLite's bare
    #: "FOREIGN KEY constraint failed". Bypass with ``force=True``.
    protect_on_delete: tuple[str, ...] = ()

    #: Primary key column names in mapper order. Used to validate the
    #: keyword arguments accepted by :meth:`get_one` and friends.
    _primary_keys: tuple[str, ...]

    #: How many samples to show when delete is blocked by FK constraint
    blocker_samples: int = 3

    #: Session bound to the current request. Set per instance, never shared.
    db: AsyncSession

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._resolve_types()

        py_type = cls.__dict__.get("py_type")
        if py_type is None:
            return
        cls.item_list_type = ItemList[py_type]  # type: ignore[arg-type]
        cls.batch_result_type = BatchResult[py_type]  # type: ignore[arg-type]
        cls._primary_keys = tuple(c.name for c in cls.db_type.__mapper__.primary_key)  # type: ignore[misc]
        cls._needs_reload = any(
            c.server_default is not None or c.computed is not None
            for c in cls.db_type.__mapper__.columns  # type: ignore[misc]
        )

    @classmethod
    def _resolve_types(cls) -> None:
        """Takes db_type and py_type from Generic (CRUDRepo[X, Y]), if not specified"""
        if "py_type" in cls.__dict__ and "db_type" in cls.__dict__:
            return
        for base in getattr(cls, "__orig_bases__", ()):
            origin = get_origin(base)
            if not (isinstance(origin, type) and issubclass(origin, CRUDRepo)):
                continue
            args = get_args(base)
            if len(args) == 2 and not any(isinstance(a, TypeVar) for a in args):
                cls.db_type, cls.py_type = args  # type: ignore[misc]
            return

    def __init__(self, db: AsyncSession):
        self.db = db
        assert issubclass(self.db_type, Base), "Expected db_type to be a subclass of Base"
        assert issubclass(self.py_type, BaseModel), "Expected py_type to be a subclass of BaseModel"
        for relationship_name in self.protect_on_delete:
            assert relationship_name in self.db_type.__mapper__.relationships, "Expected protect_on_delete to be a valid relationship name"

    @overload
    async def get_one(self, *, quiet: Literal[False] = False, **kwargs) -> BaseT: ...

    @overload
    async def get_one(self, *, quiet: Literal[True], **kwargs) -> BaseT | None: ...

    async def get_one(self, *, key_loc: Optional[Literal["path", "body"]] = None, quiet: bool = False, **kwargs) -> BaseT | None:
        """
        Gets one object from database.
        :raises NotFoundError: When no element with given keys has been found.
        :param key_loc: Place where the key ids are located.
        :param quiet: If True suppresses the error and can return None, defaults to False.
        :param kwargs: They must be a dictionary of the primary keys in the initialized db_type.
        :returns: Object from database.
        """
        assert kwargs.keys() == set(
            self._primary_keys), f"You need to provide only and all primary keys: {self._primary_keys}, you provided: {kwargs}"
        query = select(self.db_type)
        for key in self._primary_keys:
            query = query.where(self.db_type.__mapper__.c[key] == kwargs[key])
        result = await self.db.scalar(query)
        if result is None:
            if not quiet:
                raise NotFoundError(
                    resource=self.db_type.__name__,
                    key=kwargs,
                    loc=(key_loc, *kwargs.keys()) if key_loc else tuple(kwargs.keys()),
                )
        return result

    async def get_multiple(self, *args, **kwargs) -> Sequence[BaseT]:
        """
        Gets objects from database.
        Does not raise an error when nothing has been found.
        :param kwargs: Optional keys by which the query will be filtering.
        :return: List of the objects
        """
        query = select(self.db_type)
        for key, value in kwargs.items():
            query = query.where(self.db_type.__mapper__.c[key] == value)
        objs = await self.db.execute(query)
        objs = objs.scalars().all()
        return objs

    async def get_all(
            self,
            *args,
            limit: int | None = None,
            offset: int = 0,
            **kwargs
    ) -> ItemList[BaseModelT]:
        """
        Gets a specified number of objects from database, ordered by primary key.
        Does not raise an error when nothing has been found.
        :param limit: Maximum number of items to return. None returns all of them.
        :param offset: Number of items to skip.
        :param kwargs: Optional keys by which the query will be filtering.
        :returns: ItemList with items of the requested page and the unpaginated total count.
        """
        query = select(self.db_type).order_by(*self.db_type.__mapper__.primary_key)
        count_query = select(func.count()).select_from(self.db_type)

        for key, value in kwargs.items():
            query = query.where(self.db_type.__mapper__.c[key] == value)
            count_query = count_query.where(self.db_type.__mapper__.c[key] == value)

        if offset:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)

        results = await self.db.execute(query)
        results = results.scalars().all()

        total_count = await self.db.scalar(count_query)

        return ItemList[self.py_type](  # type: ignore[arg-type]
            total=total_count,
            items=[*results],
        )

    async def check_exists(self, *, key_loc: Optional[Literal["path", "body"]] = None, **kwargs) -> None:
        """
        Checks if any object exists in the database.
        Useful for checking if any object exists regardless of the version.

        :raises NotFoundError: When no element with given keys has been found.
        :param key_loc: Place where the key ids are located.
        :param kwargs: Optional keys by which the query will be filtering.
        :returns: None
        """
        query = select(self.db_type)

        for key, value in kwargs.items():
            query = query.where(getattr(self.db_type, key) == value)

        result = await self.db.scalar(query)

        if result is None:
            raise NotFoundError(
                resource=self.db_type.__name__,
                key=kwargs,
                loc=(key_loc, *kwargs.keys()) if key_loc else tuple(kwargs.keys()),
            )
        return None

    async def create(
            self,
            obj: BaseModel,
            *,
            exclude: set[str] | None = None,
            autocommit: bool = True,
            **kwargs
    ) -> BaseT:
        """
        Creates new object in the database.
        :param obj: New object to add to database.
        :param exclude: Fields of obj that are not columns (e.g. a raw password) and must be skipped.
        :param kwargs: Additional fields that need to filled.
        :param autocommit: If true the objects will be committed to database, else the queue will be flushed
        :return: New object.
        """
        new_obj = self.db_type(**obj.model_dump(exclude=exclude), **kwargs)
        self.db.add(new_obj)
        await (self.db.commit() if autocommit else self.db.flush())
        return new_obj

    async def update(
            self,
            updated_object: UpdateModel | dict[str, Any],
            *,
            key_loc: Optional[Literal["path", "body"]] = None,
            autocommit: bool = True,
            **kwargs
    ) -> BaseT:
        """
        Alters object specified by kwargs.
        :raises NotFoundError: When no element with given keys has been found.
        :raises ValidationError: When new object has more keys than necessary.
        :param updated_object: UpdateModel or dictionary from which attributes are taken to update object from database.
        :param key_loc: Place where the key ids are located.
        :param autocommit: If true the objects will be committed to database, else the queue will be flushed
        :param kwargs: They must be a dictionary of the primary keys in the initialized db_type.
        :returns: Object from database.
        """
        obj: Base = await self.get_one(key_loc=key_loc, **kwargs)
        if isinstance(updated_object, UpdateModel):  # dump object to dict
            updated_object: dict[str, Any] = updated_object.model_dump_null()

        for k, v in updated_object.items():  # Validate keys
            if not hasattr(obj, k):
                raise ValidationError(
                    msg=f"{obj} does not have an attribute: {k}.",
                    loc=("body", k),
                    input_=updated_object,
                )

        for k, v in updated_object.items():
            setattr(obj, k, v)
        await (self.db.commit() if autocommit else self.db.flush())
        await self.db.refresh(obj)
        return obj

    async def sync(
            self,
            items: list[BaseModelT | dict],
            *,
            autocommit: bool = True,
            **kwargs
    ) -> BatchResult[BaseModelT]:
        """
        Batch creates, updates, deletes objects in database.
        :raises ValidationError: When there are duplicates, missing fields or fields conflicting with params in kwargs.
        :param items: Items to be created / updated. Missing items are deleted.
        :param autocommit: If true the objects will be committed to database, else the queue will be flushed
        :param kwargs: Optional keys by which the query will be filtering, selected fields are automatically set.
        :return: BatchResult with objects from database.
        """
        return await self._apply_batch(items, delete_missing=True, autocommit=autocommit, scope=kwargs)

    async def upsert(
            self,
            items: list[BaseModelT | dict],
            *,
            autocommit: bool = True,
            **kwargs
    ) -> BatchResult[BaseModelT]:
        """
        Batch creates, updates objects in database. DOES NOT DELETE.
        :raises ValidationError: When there are duplicates, missing fields or fields conflicting with params in kwargs.
        :param items: Items to be created / updated.
        :param autocommit: If true the objects will be committed to database, else the queue will be flushed
        :param kwargs: Optional keys by which the query will be filtering, selected fields are automatically set.
        :return: BatchResult with objects from database.
        """
        return await self._apply_batch(items, delete_missing=False, autocommit=autocommit, scope=kwargs)

    def _key_of(self, source: BaseModel | dict | Base) -> tuple | None:
        """Returns values of primary key from source. None if keys are not found."""
        if isinstance(source, BaseModel):
            data = source.model_dump()
        elif isinstance(source, dict):
            data = source
        else:
            data = {k: getattr(source, k) for k in self._primary_keys}
        values = tuple(data.get(k, None) for k in self._primary_keys)
        return None if any(v is None for v in values) else values

    async def _apply_batch(
            self,
            items: list[BaseModelT | dict],
            *,
            delete_missing: bool,
            autocommit: bool,
            scope: dict[str, Any],
    ) -> BatchResult[BaseModelT]:
        existing_rows = await self.get_multiple(**scope)
        existing = {self._key_of(o): o for o in existing_rows}

        unchanged: list[BaseT] = []
        created: list[BaseT] = []
        updated: list[BaseT] = []
        errors: list[DomainError] = []
        seen: set[tuple[Any, ...]] = set()

        for i, item in enumerate(items):
            try:
                data: dict[str, Any] = item.model_dump() if isinstance(item, BaseModel) else dict(item)

                # Data cannot escape the scope
                for k, v in scope.items():
                    if k in data and data[k] != v:
                        raise ValidationError(
                            msg=f"Field {k}={data[k]!r} is out of operation scope ({k}={v!r})",
                            loc=("body", "items", i),
                            input_=item,
                        )
                    data[k] = v

                unknown = set(data) - set(self.db_type.__mapper__.c.keys())
                if unknown:
                    raise ValidationError(
                        msg=f"{self.db_type.__name__} does not have an attributes: {sorted(unknown)}.",
                        loc=("body", "items", i),
                        input_=item,
                    )

                # Detect duplicate keys. Computed on scope-merged `data`, not
                # the raw item -- for primary keys with a component supplied
                # only via scope (e.g. ClassType's course_id), the raw item
                # alone never carries a complete key, which previously made
                # this check silently no-op and let duplicates reach the DB
                # as a raw IntegrityError instead of a clean 422.
                key = self._key_of(data)
                if key is not None:
                    if key in seen:
                        raise ValidationError(
                            msg=f"Duplicate key: {key} in request.",
                            loc=("body", "items", i),
                            input_=item,
                        )
                    seen.add(key)

                obj = existing.get(key) if key is not None else None

                if obj is None:
                    obj = self.db_type(**data)
                    self.db.add(obj)
                    created.append(obj)
                else:
                    # Compare before mutating: SQLAlchemy marks an attribute
                    # dirty on any setattr, even when the new value equals
                    # the old one, so inspect(obj).modified can't tell an
                    # actual change from a no-op re-send.
                    current = {k: getattr(obj, k) for k in data}
                    if current == data:
                        unchanged.append(obj)
                    else:
                        for k, v in data.items():
                            setattr(obj, k, v)
                        updated.append(obj)

            except DomainError as e:
                errors.append(e)

        if errors:
            raise DomainErrorGroup(errors)

        untouched = [obj for key, obj in existing.items() if key not in seen]
        to_delete = untouched if delete_missing else []

        if delete_missing:
            for obj in to_delete:
                await self.db.delete(obj)

        await (self.db.commit() if autocommit else self.db.flush())

        if self._needs_reload:
            kept = await self.get_multiple(**scope)
        else:
            kept = [*created, *updated, *unchanged] + ([] if delete_missing else untouched)

        return BatchResult[self.py_type](  # type: ignore[arg-type]
            items=kept,
            created=len(created),
            updated=len(updated),
            unchanged=len(unchanged),
            deleted=len(to_delete),
        )

    async def _assert_deletable(self, obj: BaseT, loc: tuple = ()) -> None:
        blockers: list[dict[str, Any]] = []

        for rel_name in self.protect_on_delete:
            rel = self.db_type.__mapper__.relationships[rel_name]
            child = rel.mapper.class_

            # Children whose FK columns equal this row's referenced values. (Filtering by
            # rel.primaryjoin would cross join the parent table without binding this row.)
            mapper = self.db_type.__mapper__
            stmt = select(child).where(*(
                remote == getattr(obj, mapper.get_property_by_column(local).key)
                for local, remote in rel.local_remote_pairs
            ))
            rows = (await self.db.scalars(stmt.limit(self.blocker_samples + 1))).all()
            if not rows:
                continue

            blockers.append({
                "relation": rel_name,
                "resource": child.__name__,
                "samples": [r.to_dict() for r in rows[: self.blocker_samples]],
                "more": len(rows) > self.blocker_samples,
            })

        if blockers:
            names = ", ".join(b["resource"] for b in blockers)
            raise ConflictError(
                f"Cannot delete, this resource is still used by: {names}",
                loc=loc,
                blockers=blockers,
            )

    async def delete_one(
            self,
            *,
            key_loc: Optional[Literal["path", "body"]] = None,
            autocommit: bool = True,
            force: bool = False,
            **kwargs
    ) -> Delete:
        """
        Deletes singular object from database. Checks if the object can be deleted.
        Object cannot be deleted if the field 'protect_on_delete' has relationship names,
        that would still exist after the deletion. Use 'force' flag to skip this check.
        :raises NotFoundError: When no element with given keys has been found.
        :raises ConflictError: When element cannot be deleted due to FK constraint.
        :param key_loc: Place where the key ids are located.
        :param autocommit: If true the objects will be committed to database, else the queue will be flushed
        :param force: If true skips 'protect_on_delete' check.
        :param kwargs: They must be a dictionary of the primary keys in the initialized db_type.
        :returns: Default delete message.
        """
        obj = await self.get_one(key_loc=key_loc, **kwargs)
        if not force:
            await self._assert_deletable(obj, loc=(key_loc, *kwargs.keys()) if key_loc else ())
        await self.db.delete(obj)
        await (self.db.commit() if autocommit else self.db.flush())
        return Delete(deleted=1, detail=f"Deleted {self.db_type.__name__}.")

    async def delete_all(
            self,
            *,
            autocommit: bool = True,
            **kwargs
    ) -> Delete:
        """
        Deletes multiple objects from database. DOES NOT CHECK FOR FK CONSTRAINTS.
        Does not raise error when nothing has been deleted.
        :param autocommit: If true the objects will be committed to database, else the queue will be flushed
        :param kwargs: Optional keys by which the query will be filtering.
        :returns: Default delete message.
        """
        objs = await self.get_multiple(**kwargs)
        for obj in objs:
            await self.db.delete(obj)
        await (self.db.commit() if autocommit else self.db.flush())
        return Delete(deleted=len(objs), detail=f"Deleted {self.db_type.__name__}.")
