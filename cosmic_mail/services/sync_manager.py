from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Event, Lock, Thread
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from cosmic_mail.core.config import Settings
from cosmic_mail.domain.models import MailboxIdentity
from cosmic_mail.domain.repositories import MailboxRepository
from cosmic_mail.domain.schemas import MailboxSyncResult
from cosmic_mail.services.conversations import ConversationService, MailboxNotFoundError
from cosmic_mail.services.inbound import InboundMailboxClient
from cosmic_mail.services.outbound import NoopOutboundMailSender
from cosmic_mail.services.message_utils import utcnow
from cosmic_mail.services import webhooks as webhook_service
from cosmic_mail.domain.repositories import MessageRepository, ThreadRepository, WebhookRepository
from cosmic_mail.domain.models import MessageDirection

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker


@dataclass(frozen=True)
class SyncRunReport:
    organization_id: str | None
    mailbox_count: int
    synced_mailboxes: int
    failed_mailboxes: int
    imported_count: int
    skipped_count: int
    completed_at: datetime
    errors: list[str]


@dataclass(frozen=True)
class SyncWorkerStatusSnapshot:
    enabled: bool
    running: bool
    interval_seconds: int
    last_started_at: datetime | None
    last_completed_at: datetime | None
    last_run_mailbox_count: int
    last_run_imported_count: int
    last_run_failed_count: int
    last_error: str | None


@dataclass
class _MutableSyncWorkerStatus:
    enabled: bool
    running: bool = False
    interval_seconds: int = 60
    last_started_at: datetime | None = None
    last_completed_at: datetime | None = None
    last_run_mailbox_count: int = 0
    last_run_imported_count: int = 0
    last_run_failed_count: int = 0
    last_error: str | None = None


class MailboxSyncService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        inbound_client: InboundMailboxClient,
    ) -> None:
        self._session = session
        self._settings = settings
        self._inbound_client = inbound_client
        self._mailboxes = MailboxRepository(session)

    def get_policy(self, mailbox_id: str) -> MailboxIdentity:
        return self._require_mailbox(mailbox_id)

    def update_policy(self, mailbox_id: str, *, enabled: bool) -> MailboxIdentity:
        mailbox = self._require_mailbox(mailbox_id)
        mailbox.inbound_sync_enabled = enabled
        self._session.add(mailbox)
        self._session.commit()
        self._session.refresh(mailbox)
        return mailbox

    def sync_mailbox(self, mailbox_id: str) -> MailboxSyncResult:
        mailbox = self._require_mailbox(mailbox_id)
        service = ConversationService(
            self._session,
            self._settings,
            outbound_sender=NoopOutboundMailSender(),
            inbound_client=self._inbound_client,
        )
        try:
            result = service.sync_inbox(mailbox.id)
        except Exception as exc:
            self._record_sync_error(mailbox.id, str(exc))
            raise

        if result.imported_count > 0:
            self._dispatch_inbound_webhooks(mailbox.id, mailbox.organization_id)

        return result

    def _dispatch_inbound_webhooks(self, mailbox_id: str, organization_id: str) -> None:
        try:
            msg_repo = MessageRepository(self._session)
            thread_repo = ThreadRepository(self._session)
            wh_repo = WebhookRepository(self._session)
            recent = msg_repo.list_for_mailbox(mailbox_id, limit=20)
            for msg in recent:
                if msg.direction == MessageDirection.inbound.value:
                    thread = thread_repo.get(msg.thread_id)
                    if thread:
                        webhook_service.dispatch_webhooks(wh_repo, msg, thread, "message.received")
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Webhook dispatch error: %s", exc)

    def run_organization_sync(self, organization_id: str) -> SyncRunReport:
        mailbox_ids = [
            mailbox.id
            for mailbox in self._mailboxes.list_sync_enabled(
                organization_id=organization_id,
                limit=self._settings.sync_worker_batch_size,
            )
        ]
        return self._run_mailbox_ids(mailbox_ids, organization_id=organization_id)

    def _run_mailbox_ids(
        self,
        mailbox_ids: list[str],
        *,
        organization_id: str | None,
    ) -> SyncRunReport:
        synced_mailboxes = 0
        failed_mailboxes = 0
        imported_count = 0
        skipped_count = 0
        errors: list[str] = []

        for mailbox_id in mailbox_ids:
            try:
                result = self.sync_mailbox(mailbox_id)
            except Exception as exc:
                failed_mailboxes += 1
                errors.append(f"{mailbox_id}: {exc}")
                self._session.expire_all()
                continue
            synced_mailboxes += 1
            imported_count += result.imported_count
            skipped_count += result.skipped_count

        return SyncRunReport(
            organization_id=organization_id,
            mailbox_count=len(mailbox_ids),
            synced_mailboxes=synced_mailboxes,
            failed_mailboxes=failed_mailboxes,
            imported_count=imported_count,
            skipped_count=skipped_count,
            completed_at=utcnow(),
            errors=errors,
        )

    def _record_sync_error(self, mailbox_id: str, message: str) -> None:
        mailbox = self._mailboxes.get(mailbox_id)
        if mailbox is None:
            return
        mailbox.last_sync_error = message
        self._session.add(mailbox)
        self._session.commit()
        self._session.refresh(mailbox)

    def _require_mailbox(self, mailbox_id: str) -> MailboxIdentity:
        mailbox = self._mailboxes.get(mailbox_id)
        if mailbox is None:
            raise MailboxNotFoundError("mailbox not found")
        return mailbox


class SyncWorker:
    def __init__(
        self,
        session_factory: sessionmaker,
        settings: Settings,
        inbound_client: InboundMailboxClient,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._inbound_client = inbound_client
        self._status = _MutableSyncWorkerStatus(
            enabled=settings.sync_worker_enabled,
            interval_seconds=settings.sync_worker_interval_seconds,
        )
        self._status_lock = Lock()
        self._run_lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if not self._settings.sync_worker_enabled or self._thread is not None:
            return
        self._thread = Thread(
            target=self._run_loop,
            name="cosmic-mail-sync-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            self._thread = None

    def status(self) -> SyncWorkerStatusSnapshot:
        with self._status_lock:
            return SyncWorkerStatusSnapshot(
                enabled=self._status.enabled,
                running=self._status.running,
                interval_seconds=self._status.interval_seconds,
                last_started_at=self._status.last_started_at,
                last_completed_at=self._status.last_completed_at,
                last_run_mailbox_count=self._status.last_run_mailbox_count,
                last_run_imported_count=self._status.last_run_imported_count,
                last_run_failed_count=self._status.last_run_failed_count,
                last_error=self._status.last_error,
            )

    def run_once(self, *, organization_id: str | None = None) -> SyncRunReport:
        with self._run_lock:
            started_at = utcnow()
            self._update_status(
                running=True,
                last_started_at=started_at,
                last_error=None,
            )
            try:
                report = self._run_once(organization_id=organization_id)
            except Exception as exc:
                self._update_status(
                    running=False,
                    last_completed_at=utcnow(),
                    last_error=str(exc),
                )
                raise
            self._update_status(
                running=False,
                last_completed_at=report.completed_at,
                last_run_mailbox_count=report.mailbox_count,
                last_run_imported_count=report.imported_count,
                last_run_failed_count=report.failed_mailboxes,
                last_error=None if not report.errors else "; ".join(report.errors),
            )
            return report

    def _run_once(self, *, organization_id: str | None) -> SyncRunReport:
        with self._session_factory() as session:
            mailboxes = MailboxRepository(session).list_sync_enabled(
                organization_id=organization_id,
                limit=self._settings.sync_worker_batch_size,
            )
            mailbox_ids = [mailbox.id for mailbox in mailboxes]

        synced_mailboxes = 0
        failed_mailboxes = 0
        imported_count = 0
        skipped_count = 0
        errors: list[str] = []

        for mailbox_id in mailbox_ids:
            with self._session_factory() as session:
                service = MailboxSyncService(
                    session,
                    self._settings,
                    self._inbound_client,
                )
                try:
                    result = service.sync_mailbox(mailbox_id)
                except Exception as exc:
                    failed_mailboxes += 1
                    errors.append(f"{mailbox_id}: {exc}")
                    continue
                synced_mailboxes += 1
                imported_count += result.imported_count
                skipped_count += result.skipped_count

        return SyncRunReport(
            organization_id=organization_id,
            mailbox_count=len(mailbox_ids),
            synced_mailboxes=synced_mailboxes,
            failed_mailboxes=failed_mailboxes,
            imported_count=imported_count,
            skipped_count=skipped_count,
            completed_at=utcnow(),
            errors=errors,
        )

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                pass
            if self._stop_event.wait(self._settings.sync_worker_interval_seconds):
                return

    def _update_status(self, **kwargs: object) -> None:
        with self._status_lock:
            for key, value in kwargs.items():
                setattr(self._status, key, value)
