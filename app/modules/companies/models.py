from __future__ import annotations

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Company(BaseModel):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(Text, nullable=False)

    # relationships
    users: Mapped[list["User"]] = relationship(back_populates="company", cascade="all, delete-orphan")  # noqa: F821
    jobs: Mapped[list["Job"]] = relationship(back_populates="company", cascade="all, delete-orphan")  # noqa: F821
    form_templates: Mapped[list["FormTemplate"]] = relationship(back_populates="company", cascade="all, delete-orphan")  # noqa: F821
    tags: Mapped[list["Tag"]] = relationship(back_populates="company", cascade="all, delete-orphan")  # noqa: F821
