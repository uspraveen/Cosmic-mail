from __future__ import annotations

from sqlalchemy.orm import Session

from cosmic_mail.core.config import Settings
from cosmic_mail.core.security import fingerprint_token, generate_api_key
from cosmic_mail.domain.models import OrganizationApiKey
from cosmic_mail.domain.repositories import OrganizationApiKeyRepository, OrganizationRepository
from cosmic_mail.domain.schemas import OrganizationApiKeyCreate
from cosmic_mail.services.message_utils import utcnow


class OrganizationApiKeyNotFoundError(ValueError):
    pass


class OrganizationApiKeyConflictError(ValueError):
    pass


class OrganizationApiKeyOrganizationNotFoundError(ValueError):
    pass


class OrganizationApiKeyService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._organizations = OrganizationRepository(session)
        self._api_keys = OrganizationApiKeyRepository(session)

    def create(
        self,
        organization_id: str,
        payload: OrganizationApiKeyCreate,
    ) -> tuple[OrganizationApiKey, str]:
        organization = self._organizations.get(organization_id)
        if organization is None:
            raise OrganizationApiKeyOrganizationNotFoundError("organization not found")

        plaintext_key = generate_api_key()
        api_key = OrganizationApiKey(
            organization_id=organization.id,
            name=payload.name.strip(),
            key_prefix=plaintext_key[:16],
            token_hash=fingerprint_token(self._settings.secret_key, plaintext_key),
        )
        self._api_keys.add(api_key)
        self._session.commit()
        self._session.refresh(api_key)
        return api_key, plaintext_key

    def list_for_organization(self, organization_id: str) -> list[OrganizationApiKey]:
        organization = self._organizations.get(organization_id)
        if organization is None:
            raise OrganizationApiKeyOrganizationNotFoundError("organization not found")
        return self._api_keys.list_for_organization(organization_id)

    def revoke(self, organization_id: str, api_key_id: str) -> OrganizationApiKey:
        organization = self._organizations.get(organization_id)
        if organization is None:
            raise OrganizationApiKeyOrganizationNotFoundError("organization not found")
        api_key = self._api_keys.get(api_key_id)
        if api_key is None or api_key.organization_id != organization_id:
            raise OrganizationApiKeyNotFoundError("api key not found")
        if api_key.revoked_at is None:
            api_key.revoked_at = utcnow()
            self._session.add(api_key)
            self._session.commit()
            self._session.refresh(api_key)
        return api_key

    def authenticate(self, plaintext_key: str) -> OrganizationApiKey | None:
        token_hash = fingerprint_token(self._settings.secret_key, plaintext_key)
        api_key = self._api_keys.get_active_by_token_hash(token_hash)
        if api_key is None:
            return None
        api_key.last_used_at = utcnow()
        self._session.add(api_key)
        self._session.commit()
        self._session.refresh(api_key)
        return api_key
