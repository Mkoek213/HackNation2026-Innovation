import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.schemas.tagging import AssignedLabel, Classification
from .taxonomy import Audience, Category, DevelopmentPath, InnovationType, InstitutionType, Maturity

DocType = Literal[
    "card",
    "patent",
    "publikacja",
    "raport",
    "prezentacja",
    "instrukcja",
    "material",
]

# "summary": the short overview of an innovation (e.g. a one-page leaflet) -- ranks innovations.
# "full": complete materials (patent text, publication, reports, manuals) -- supplies evidence.
DocumentRole = Literal["summary", "full"]

INNOVATION_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
InnovationArea = Literal["technologia", "edukacja", "administracja"]
Verification = Literal["zgloszone", "kandydat", "potwierdzona"]  # zgloszone: user submission, not yet reviewed


class AssessmentNote(BaseModel):
    basis: Literal["potwierdzone", "szacunek"]
    rationale: str = Field(min_length=1, max_length=1200)
    source_url: HttpUrl | None = None
    score: int | None = Field(default=None, ge=1, le=5, description="1-5 on the criterion's scale; null when not scored")

    @model_validator(mode="after")
    def _confirmed_has_source(self):
        if self.basis == "potwierdzone" and self.source_url is None:
            raise ValueError("Confirmed assessments require a source URL")
        return self


class Recipient(BaseModel):
    audience: Audience
    why: str = Field(min_length=1, max_length=400)


class InnovationAssessment(BaseModel):
    implementation: AssessmentNote | None = None
    novelty: AssessmentNote | None = None
    transfer: AssessmentNote | None = None
    credibility: AssessmentNote | None = None
    trl: int | None = Field(default=None, ge=1, le=9)
    trl_basis: AssessmentNote | None = None
    next_step: str = Field(default="", max_length=1200)
    summary: str = Field(default="", max_length=1200, description="Plain Polish summary of what the solution is")
    recipients: list[Recipient] = Field(default_factory=list, max_length=4)
    path: DevelopmentPath | None = None
    path_rationale: str = Field(default="", max_length=1200)
    measures: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(default_factory=list, max_length=4)
    criteria_version: str = Field(default="", max_length=40, description="Set by the automatic assessment")
    assessed_at: dt.date | None = None


class InnovationCard(BaseModel):
    """Short, curated description of an innovation.
    This is the primary matching target; long documents only substantiate it."""

    problem: str = Field(default="", max_length=4000, description="Jaki problem rozwiązuje?")
    solution: str = Field(default="", max_length=4000, description="Na czym polega rozwiązanie?")
    novelty: str = Field(default="", max_length=4000, description="Co jest nowego w porównaniu z istniejącymi rozwiązaniami?")
    target_users: str = Field(default="", max_length=4000, description="Kto może z niej skorzystać lub ją wdrożyć?")
    evidence: str = Field(default="", max_length=4000, description="Stan zaawansowania i dowody działania")

    model_config = ConfigDict(extra="forbid")


class Author(BaseModel):
    """A creator named in a public source (registry, publication) or a consenting submitter."""

    name: str = Field(min_length=1, max_length=200)
    affiliation: str | None = Field(default=None, max_length=300)

    model_config = ConfigDict(extra="forbid")


class InnovationDraft(BaseModel):
    """Unstored proposal for the admin upload form. Categories are a GLiDE decision;
    the Polish card is generated text and may be empty when that model is unavailable."""

    title: str = Field(default="", max_length=300)
    source_url: str | None = Field(default=None, max_length=2000)
    card: InnovationCard = Field(default_factory=InnovationCard)
    primary_category: Category | None = None
    categories: list[Category] = Field(default_factory=list)
    innovation_type: InnovationType | None = None
    institution_type: InstitutionType | None = None
    institution: str | None = Field(default=None, max_length=300)
    maturity: Maturity | None = None
    category_status: Literal["completed", "uncertain", "unavailable"]
    card_status: Literal["completed", "unavailable"]
    files: list[str] = Field(default_factory=list)
    skipped_files: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _primary_in_categories(self):
        if self.primary_category is None:
            self.categories = []
            return self
        self.categories = list(dict.fromkeys(self.categories))
        if self.primary_category not in self.categories:
            self.categories.insert(0, self.primary_category)
        return self


class InnovationUpdate(BaseModel):
    """Editable card fields: everything in InnovationMeta except the identifier."""

    title: str = Field(min_length=1, max_length=300, examples=["Inteligentny system monitorowania jakości powietrza w szkołach"])
    categories: list[Category] = Field(min_length=1, examples=[["jakosc-zycia", "ict"]])
    primary_category: Category = Field(examples=["jakosc-zycia"])
    innovation_type: InnovationType | None = Field(default=None, examples=["technologiczna"])
    institution_type: InstitutionType | None = Field(default=None, examples=["uczelnia"])
    institution: str | None = Field(default=None, max_length=300, examples=["Politechnika Rzeszowska"])
    authors: list[Author] = Field(default_factory=list, max_length=50)
    maturity: Maturity | None = Field(default=None, examples=["prototyp"])
    source_name: str | None = Field(default=None, max_length=200, examples=["Urząd Patentowy RP"],
                                    description="Registry or database the record was taken from")
    source_url: str | None = Field(default=None, max_length=2000, examples=["https://ewyszukiwarka.pue.uprp.gov.pl/..."])
    imported_at: dt.date | None = Field(default=None, description="When the record was taken from source_name")
    checked_at: dt.date | None = None
    region: str | None = Field(default=None, max_length=60)
    area: InnovationArea | None = None
    verification: Verification = "kandydat"
    assessment: InnovationAssessment = Field(default_factory=InnovationAssessment)
    video_url: str | None = Field(default=None, max_length=2000, examples=["https://www.youtube.com/watch?v=..."])
    card: InnovationCard = Field(default_factory=InnovationCard)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _primary_in_categories(self):
        self.categories = list(dict.fromkeys(self.categories))  # dedupe, keep order
        if self.primary_category not in self.categories:
            self.categories.insert(0, self.primary_category)
        if self.verification == "potwierdzona" and (
            self.maturity not in {Maturity.PILOT, Maturity.IN_USE}
            or not self.assessment.implementation
            or self.assessment.implementation.basis != "potwierdzone"
        ):
            raise ValueError("A confirmed innovation requires documented real-world use")
        if self.assessment.trl is not None and (self.area != "technologia" or self.assessment.trl_basis is None):
            raise ValueError("TRL requires the technology area and an assessment basis")
        return self


class InnovationMeta(InnovationUpdate):
    id: str = Field(pattern=INNOVATION_ID_PATTERN, max_length=120, examples=["uprp-p-441234"])


class StoredDocument(BaseModel):
    classification: Classification | None = None
    tags: list[AssignedLabel] = Field(default_factory=list)
    content_sha256: str | None = None
    id: str
    role: DocumentRole = "full"
    filename: str
    content_type: str
    size_bytes: int
    download_url: str
    # Persisted in Qdrant, omitted from public responses.
    object_key: str = Field(default="", exclude=True)


class InnovationSummary(InnovationMeta):
    documents: list[StoredDocument] = Field(default_factory=list)
    chunk_count: int = Field(default=0, examples=[42])
    files: list[str] = Field(default_factory=list, examples=[["opis-patentowy.pdf"]])
    import_baseline: dict = Field(default_factory=dict, exclude=True)
    assessment_baseline: dict = Field(default_factory=dict, exclude=True)  # last automatic proposal


class CatalogPage(BaseModel):
    items: list[InnovationSummary]
    total: int
    regions: list[str]


class CategoriesUpdate(BaseModel):
    categories: list[Category] = Field(min_length=1)
    primary_category: Category

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _primary_in_categories(self):
        if self.primary_category not in self.categories:
            raise ValueError("primary_category must be one of categories")
        return self


class IngestResult(BaseModel):
    documents: list[StoredDocument] = Field(default_factory=list)
    innovation_id: str
    summary_file: str | None = Field(default=None, description="Indexed summary document, if one was uploaded")
    chunks: int
    files: list[str] = Field(description="Files whose text was indexed")
    skipped_files: list[str] = Field(
        default_factory=list,
        description="Unsupported files and files without a text layer (scans; OCR is not configured)",
    )


class Evidence(BaseModel):
    role: DocumentRole = "full"
    document_id: str | None = None
    document_url: str | None = None
    page_url: str | None = Field(default=None, description="document_url opening the PDF at page_start (#page=N)")
    content_type: str | None = None
    text: str
    doc_type: DocType
    section: str | None = None
    source_file: str | None = None
    page_start: int | None = None
    page_end: int | None = None


class RetrievedInnovation(BaseModel):
    """Retrieval result handed to matchmaking: no relevance judgment yet."""

    innovation: InnovationMeta
    retrieval_score: float = Field(description="Weighted reciprocal-rank fusion of card, summary and full-material rankings")
    summary_document: StoredDocument | None = Field(default=None, description="Short overview to open first")
    evidence: list[Evidence] = Field(description="Passages from full materials; from the summary when there are none")


class Deleted(BaseModel):
    deleted: str
