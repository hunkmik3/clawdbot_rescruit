from typing import Any

from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=lambda: ["artstation"])
    location: str | None = None
    max_items_per_platform: int = 20
    exclude_previously_scanned: bool = True
    actor_overrides: dict[str, str] = Field(
        default_factory=dict,
        description="Optional mapping platform -> Apify actor id, used to override default actors",
    )
    actor_inputs: dict[str, dict] = Field(
        default_factory=dict,
        description="Optional mapping platform -> raw Apify actor input payload",
    )


class WorkSample(BaseModel):
    """A single portfolio work item with metadata."""

    title: str | None = None
    url: str | None = None
    thumbnail_url: str | None = None
    description: str | None = None
    likes_count: int | None = None
    views_count: int | None = None


class Candidate(BaseModel):
    full_name: str | None = None
    title: str | None = None
    bio: str | None = None
    location: str | None = None
    email: str | None = None

    # Social links
    linkedin_url: str | None = None
    x_url: str | None = None
    instagram_url: str | None = None
    portfolio_url: str | None = None
    artstation_url: str | None = None
    behance_url: str | None = None

    # Portfolio content
    top_works: list[str] = Field(default_factory=list, description="Legacy: list of URLs")
    work_samples: list[WorkSample] = Field(
        default_factory=list,
        description="Structured work samples with thumbnails, descriptions, and engagement metrics",
    )

    # Experience highlights
    current_company: str | None = None
    previous_companies: list[str] = Field(default_factory=list)
    notable_projects: list[str] = Field(default_factory=list)
    experience_summary: str | None = None
    years_exp_estimate: float | None = None

    # Skills & tools
    skills: list[str] = Field(default_factory=list)
    software: list[str] = Field(default_factory=list)

    # Engagement metrics
    followers_count: int | None = None

    # Source tracking
    source_platform: str
    source_url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class JobCreateResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    error: str | None = None
    candidate_count: int = 0
