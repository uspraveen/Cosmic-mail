from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cosmic_mail.domain.models import Organization
from cosmic_mail.domain.repositories import OrganizationRepository
from cosmic_mail.domain.schemas import OrganizationCreate
from cosmic_mail.domain.validation import slugify


class OrganizationConflictError(ValueError):
    pass


class OrganizationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._organizations = OrganizationRepository(session)

    def create(self, payload: OrganizationCreate) -> Organization:
        slug = payload.slug or slugify(payload.name)
        organization = Organization(name=payload.name.strip(), slug=slug)
        try:
            self._organizations.add(organization)
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise OrganizationConflictError("organization slug already exists") from exc
        self._session.refresh(organization)
        return organization

    def list(self) -> list[Organization]:
        return self._organizations.list()

