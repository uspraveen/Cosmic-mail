from __future__ import annotations

from sqlalchemy.orm import Session

from cosmic_mail.core.config import Settings
from cosmic_mail.core.security import SecretBox
from cosmic_mail.domain.models import (
    AgentMailboxLink,
    AgentProfile,
    ApprovalStatus,
    DraftStatus,
    MailDraft,
    MailMessage,
    MailThread,
    MailboxIdentity,
    MessageDirection,
    OutboundApproval,
)
from cosmic_mail.domain.repositories import AgentMailboxLinkRepository, AgentRepository, AttachmentRepository, DomainRepository, DraftRepository, MailboxRepository, MessageRepository, OutboundApprovalRepository, ThreadRepository
from cosmic_mail.domain.schemas import MailDraftCreate, MailboxSyncResult, ThreadReplyCreate
from cosmic_mail.services.inbound import InboundMailboxClient, InboundMessageEnvelope
from cosmic_mail.services.attachments import AttachmentService, AttachmentTooLargeError
from cosmic_mail.services.message_utils import (
    ensure_utc_datetime,
    extract_preview,
    normalize_contacts,
    normalize_subject,
    unique_preserve_order,
    utcnow,
)
from cosmic_mail.services.outbound import OutboundAttachment, OutboundInlineImage, OutboundMailError, OutboundMailSender, OutboundSendRequest


class MailboxNotFoundError(ValueError):
    pass


class ThreadNotFoundError(ValueError):
    pass


class DraftNotFoundError(ValueError):
    pass


class DraftStateError(ValueError):
    pass


class DraftThreadMismatchError(ValueError):
    pass


class ApprovalNotFoundError(ValueError):
    pass


class ApprovalStateError(ValueError):
    pass


class MailTransportError(RuntimeError):
    pass


class MailboxCredentialsError(RuntimeError):
    pass


class ConversationService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        outbound_sender: OutboundMailSender,
        inbound_client: InboundMailboxClient,
    ) -> None:
        self._session = session
        self._settings = settings
        self._mailboxes = MailboxRepository(session)
        self._domains = DomainRepository(session)
        self._threads = ThreadRepository(session)
        self._drafts = DraftRepository(session)
        self._messages = MessageRepository(session)
        self._attachments = AttachmentRepository(session)
        self._agents = AgentRepository(session)
        self._agent_mailbox_links = AgentMailboxLinkRepository(session)
        self._approvals = OutboundApprovalRepository(session)
        self._outbound_sender = outbound_sender
        self._inbound_client = inbound_client
        self._secret_box = SecretBox(settings.secret_key)

    def create_draft(self, payload: MailDraftCreate) -> MailDraft:
        mailbox = self._require_mailbox(payload.mailbox_id)
        selected_thread = None
        if payload.thread_id:
            selected_thread = self._threads.get(payload.thread_id)
            if selected_thread is None or selected_thread.mailbox_id != mailbox.id:
                raise ThreadNotFoundError("thread not found")

        draft = MailDraft(
            organization_id=mailbox.organization_id,
            mailbox_id=mailbox.id,
            thread_id=selected_thread.id if selected_thread else None,
            reply_to_message_id=payload.reply_to_message_id,
            subject=payload.subject.strip(),
            text_body=payload.text_body,
            html_body=payload.html_body,
            to_recipients=normalize_contacts([contact.model_dump() for contact in payload.to_recipients]),
            cc_recipients=normalize_contacts([contact.model_dump() for contact in payload.cc_recipients]),
            bcc_recipients=normalize_contacts([contact.model_dump() for contact in payload.bcc_recipients]),
            status=DraftStatus.draft.value,
        )
        self._drafts.add(draft)
        self._session.commit()
        self._session.refresh(draft)
        return draft

    def list_drafts(self, mailbox_id: str) -> list[MailDraft]:
        self._require_mailbox(mailbox_id)
        return self._drafts.list_for_mailbox(mailbox_id)

    def send_draft(
        self, draft_id: str
    ) -> tuple[MailDraft, MailThread | None, MailMessage | None, OutboundApproval | None]:
        draft = self._require_draft(draft_id)
        if draft.status == DraftStatus.sent.value:
            raise DraftStateError("draft has already been sent")
        if draft.status == DraftStatus.pending_approval.value:
            raise DraftStateError("draft is already awaiting approval")

        mailbox = self._require_mailbox(draft.mailbox_id)
        agent = self._resolve_agent_for_mailbox(mailbox.id)

        if agent and agent.approval_required:
            draft.status = DraftStatus.pending_approval.value
            approval = OutboundApproval(
                organization_id=draft.organization_id,
                agent_id=agent.id,
                mailbox_id=mailbox.id,
                draft_id=draft.id,
                status=ApprovalStatus.pending.value,
            )
            self._approvals.add(approval)
            self._session.add(draft)
            self._session.commit()
            self._session.refresh(draft)
            self._session.refresh(approval)
            return draft, None, None, approval

        draft, thread, message = self._execute_send(draft, mailbox, agent)
        return draft, thread, message, None

    def approve_outbound(
        self, approval_id: str
    ) -> tuple[OutboundApproval, MailDraft, MailThread, MailMessage]:
        approval = self._require_approval(approval_id)
        if approval.status != ApprovalStatus.pending.value:
            raise ApprovalStateError("approval is not in pending state")

        draft = self._require_draft(approval.draft_id)
        mailbox = self._require_mailbox(draft.mailbox_id)
        agent = self._resolve_agent_for_mailbox(mailbox.id)

        # Reset to draft so _execute_send can proceed
        draft.status = DraftStatus.draft.value
        draft, thread, message = self._execute_send(draft, mailbox, agent)

        approval.status = ApprovalStatus.approved.value
        approval.reviewed_at = utcnow()
        self._session.add(approval)
        self._session.commit()
        self._session.refresh(approval)
        return approval, draft, thread, message

    def reject_outbound(
        self, approval_id: str, note: str | None = None
    ) -> tuple[OutboundApproval, MailDraft]:
        approval = self._require_approval(approval_id)
        if approval.status != ApprovalStatus.pending.value:
            raise ApprovalStateError("approval is not in pending state")

        draft = self._require_draft(approval.draft_id)

        approval.status = ApprovalStatus.rejected.value
        approval.reviewed_at = utcnow()
        approval.reviewer_note = note
        draft.status = DraftStatus.draft.value

        self._session.add_all([approval, draft])
        self._session.commit()
        self._session.refresh(approval)
        self._session.refresh(draft)
        return approval, draft

    def edit_approval_draft(
        self,
        approval_id: str,
        *,
        subject: str | None = None,
        text_body: str | None = None,
        html_body: str | None = None,
        to_recipients: list[dict] | None = None,
        cc_recipients: list[dict] | None = None,
    ) -> tuple[OutboundApproval, MailDraft]:
        approval = self._require_approval(approval_id)
        if approval.status != ApprovalStatus.pending.value:
            raise ApprovalStateError("can only edit a pending approval")

        draft = self._require_draft(approval.draft_id)
        if subject is not None:
            draft.subject = subject.strip()
        if text_body is not None:
            draft.text_body = text_body
        if html_body is not None:
            draft.html_body = html_body
        if to_recipients is not None:
            draft.to_recipients = normalize_contacts(to_recipients)
        if cc_recipients is not None:
            draft.cc_recipients = normalize_contacts(cc_recipients)

        self._session.add(draft)
        self._session.commit()
        self._session.refresh(approval)
        self._session.refresh(draft)
        return approval, draft

    def _execute_send(
        self, draft: MailDraft, mailbox: MailboxIdentity, agent: AgentProfile | None
    ) -> tuple[MailDraft, MailThread, MailMessage]:
        password = self._decrypt_mailbox_password(mailbox)
        dkim_private_key_pem, dkim_selector, dkim_domain = self._resolve_dkim(mailbox.domain_id)
        outbound_attachments = self._load_draft_attachments(draft.id)
        reply_message = None
        if draft.reply_to_message_id:
            reply_message = self._messages.get_by_mailbox_and_internet_id(mailbox.id, draft.reply_to_message_id)

        explicit_thread = None
        if draft.thread_id:
            explicit_thread = self._threads.get(draft.thread_id)
            if explicit_thread is None or explicit_thread.mailbox_id != mailbox.id:
                raise ThreadNotFoundError("thread not found")
        if explicit_thread is not None and reply_message is not None and reply_message.thread_id != explicit_thread.id:
            raise DraftThreadMismatchError("reply target does not belong to the selected thread")

        references = self._build_references(draft.reply_to_message_id, reply_message)

        text_body = draft.text_body
        html_body = draft.html_body
        inline_images: list[OutboundInlineImage] = []
        if agent and (agent.signature or agent.signature_graphic_url or agent.avatar_url):
            text_body, html_body, inline_images = _inject_signature(
                text_body, html_body, agent, self._settings.attachment_storage_path,
            )

        try:
            send_result = self._outbound_sender.send(
                OutboundSendRequest(
                    from_address=mailbox.address,
                    from_name=mailbox.display_name,
                    subject=draft.subject,
                    to_recipients=draft.to_recipients,
                    cc_recipients=draft.cc_recipients,
                    bcc_recipients=draft.bcc_recipients,
                    text_body=text_body,
                    html_body=html_body,
                    in_reply_to=draft.reply_to_message_id,
                    references=references,
                    attachments=outbound_attachments,
                    inline_images=inline_images,
                    dkim_private_key_pem=dkim_private_key_pem,
                    dkim_selector=dkim_selector,
                    dkim_domain=dkim_domain,
                ),
                password=password,
            )
        except OutboundMailError as exc:
            draft.status = DraftStatus.failed.value
            draft.last_error = str(exc)
            self._session.add(draft)
            self._session.commit()
            self._session.refresh(draft)
            raise MailTransportError(str(exc)) from exc

        event_at = ensure_utc_datetime(send_result.sent_at)
        thread = explicit_thread or (self._threads.get(reply_message.thread_id) if reply_message else None)
        if thread is None:
            thread = self._create_thread(mailbox, draft.subject, event_at)

        message = MailMessage(
            organization_id=mailbox.organization_id,
            mailbox_id=mailbox.id,
            thread_id=thread.id,
            draft_id=draft.id,
            internet_message_id=send_result.internet_message_id,
            source_uid=None,
            direction=MessageDirection.outbound.value,
            folder_name="Sent",
            subject=draft.subject,
            normalized_subject=normalize_subject(draft.subject),
            in_reply_to=draft.reply_to_message_id,
            references=references,
            from_name=mailbox.display_name,
            from_address=mailbox.address,
            to_recipients=draft.to_recipients,
            cc_recipients=draft.cc_recipients,
            bcc_recipients=draft.bcc_recipients,
            reply_to_recipients=[],
            text_body=draft.text_body,
            html_body=draft.html_body,
            preview_text=extract_preview(draft.text_body, draft.html_body),
            sent_at=event_at,
            received_at=None,
        )
        self._messages.add(message)
        self._session.flush()

        for att in self._attachments.list_for_draft(draft.id):
            att.message_id = message.id
            self._session.add(att)

        self._update_thread(thread, message.preview_text, event_at)

        draft.thread_id = thread.id
        draft.status = DraftStatus.sent.value
        draft.sent_message_id = send_result.internet_message_id
        draft.last_error = None
        draft.sent_at = event_at

        self._session.add_all([draft, thread])
        self._session.commit()
        self._session.refresh(draft)
        self._session.refresh(thread)
        self._session.refresh(message)
        return draft, thread, message

    def reply_to_thread(
        self, thread_id: str, payload: ThreadReplyCreate
    ) -> tuple[MailDraft, MailThread | None, MailMessage | None, OutboundApproval | None]:
        thread = self._threads.get(thread_id)
        if thread is None:
            raise ThreadNotFoundError("thread not found")
        mailbox = self._require_mailbox(payload.mailbox_id)
        if thread.mailbox_id != mailbox.id:
            raise ThreadNotFoundError("thread not found for this mailbox")

        messages = self._messages.list_for_thread(thread_id)
        last_message = messages[-1] if messages else None

        if payload.to_recipients is not None:
            to_recipients = [contact.model_dump() for contact in payload.to_recipients]
        elif last_message:
            reply_to = last_message.reply_to_recipients or last_message.to_recipients
            if last_message.from_address != mailbox.address:
                to_recipients = [{"email": last_message.from_address, "name": last_message.from_name}]
            else:
                to_recipients = reply_to or [{"email": last_message.from_address, "name": last_message.from_name}]
        else:
            raise ThreadNotFoundError("cannot determine reply recipient")

        reply_to_message_id = last_message.internet_message_id if last_message else None
        subject = thread.subject if thread.subject.lower().startswith("re:") else f"Re: {thread.subject}"

        draft_payload = MailDraftCreate(
            mailbox_id=mailbox.id,
            thread_id=thread_id,
            reply_to_message_id=reply_to_message_id,
            subject=subject,
            to_recipients=[{"email": r["email"], "name": r.get("name")} for r in to_recipients],
            cc_recipients=[contact.model_dump() for contact in payload.cc_recipients],
            text_body=payload.text_body,
            html_body=payload.html_body,
        )

        # Build draft manually to avoid schema re-validation issues
        references = self._build_references(reply_to_message_id, last_message)
        draft = MailDraft(
            organization_id=mailbox.organization_id,
            mailbox_id=mailbox.id,
            thread_id=thread_id,
            reply_to_message_id=reply_to_message_id,
            subject=subject,
            text_body=payload.text_body,
            html_body=payload.html_body,
            to_recipients=normalize_contacts(to_recipients),
            cc_recipients=normalize_contacts([contact.model_dump() for contact in payload.cc_recipients]),
            bcc_recipients=[],
            status=DraftStatus.draft.value,
        )
        self._drafts.add(draft)
        self._session.flush()
        return self.send_draft(draft.id)

    def mark_message_read(self, message_id: str) -> MailMessage:
        message = self._messages.get(message_id)
        if message is None:
            raise ValueError("message not found")
        if not message.is_read:
            message.is_read = True
            self._session.add(message)
            self._session.commit()
            self._session.refresh(message)
        return message

    def list_threads(self, mailbox_id: str) -> list[MailThread]:
        self._require_mailbox(mailbox_id)
        return self._threads.list_for_mailbox(mailbox_id)

    def list_thread_messages(self, thread_id: str) -> list[MailMessage]:
        thread = self._threads.get(thread_id)
        if thread is None:
            raise ThreadNotFoundError("thread not found")
        messages = self._messages.list_for_thread(thread_id)
        messages.sort(key=lambda item: ensure_utc_datetime(item.sent_at or item.received_at or item.created_at))
        return messages

    def sync_inbox(self, mailbox_id: str) -> MailboxSyncResult:
        mailbox = self._require_mailbox(mailbox_id)
        password = self._decrypt_mailbox_password(mailbox)

        envelopes = self._inbound_client.fetch_messages(
            address=mailbox.address,
            password=password,
            last_uid=mailbox.last_inbound_uid,
            folder_name=self._settings.imap_inbox_folder,
        )

        imported_count = 0
        skipped_count = 0
        max_uid = mailbox.last_inbound_uid

        for envelope in sorted(envelopes, key=lambda item: item.source_uid):
            max_uid = max(max_uid, envelope.source_uid)
            if self._messages.get_by_mailbox_and_source_uid(mailbox.id, envelope.source_uid):
                skipped_count += 1
                continue
            if self._messages.get_by_mailbox_and_internet_id(mailbox.id, envelope.internet_message_id):
                skipped_count += 1
                continue

            thread = self._resolve_thread_for_inbound(mailbox, envelope)
            event_at = ensure_utc_datetime(envelope.received_at or envelope.sent_at or utcnow())
            message = MailMessage(
                organization_id=mailbox.organization_id,
                mailbox_id=mailbox.id,
                thread_id=thread.id,
                draft_id=None,
                internet_message_id=envelope.internet_message_id,
                source_uid=envelope.source_uid,
                direction=MessageDirection.inbound.value,
                folder_name=envelope.folder_name,
                subject=envelope.subject,
                normalized_subject=envelope.normalized_subject,
                in_reply_to=envelope.in_reply_to,
                references=envelope.references,
                from_name=envelope.from_name,
                from_address=envelope.from_address,
                to_recipients=envelope.to_recipients,
                cc_recipients=envelope.cc_recipients,
                bcc_recipients=envelope.bcc_recipients,
                reply_to_recipients=envelope.reply_to_recipients,
                text_body=envelope.text_body,
                html_body=envelope.html_body,
                preview_text=extract_preview(envelope.text_body, envelope.html_body),
                is_bounce=envelope.is_bounce,
                bounce_type=envelope.bounce_type,
                sent_at=ensure_utc_datetime(envelope.sent_at) if envelope.sent_at else None,
                received_at=ensure_utc_datetime(envelope.received_at),
            )
            self._messages.add(message)
            self._session.flush()
            self._save_inbound_attachments(envelope, message, mailbox)
            self._update_thread(thread, message.preview_text, event_at)
            imported_count += 1

        mailbox.last_inbound_uid = max_uid
        mailbox.last_synced_at = utcnow()
        mailbox.last_sync_error = None
        self._session.add(mailbox)
        self._session.commit()
        self._session.refresh(mailbox)

        return MailboxSyncResult(
            mailbox_id=mailbox.id,
            imported_count=imported_count,
            skipped_count=skipped_count,
            last_inbound_uid=mailbox.last_inbound_uid,
            synced_at=mailbox.last_synced_at,
        )

    def _require_mailbox(self, mailbox_id: str) -> MailboxIdentity:
        mailbox = self._mailboxes.get(mailbox_id)
        if mailbox is None:
            raise MailboxNotFoundError("mailbox not found")
        return mailbox

    def _require_draft(self, draft_id: str | None) -> MailDraft:
        if draft_id is None:
            raise DraftNotFoundError("draft not found")
        draft = self._drafts.get(draft_id)
        if draft is None:
            raise DraftNotFoundError("draft not found")
        return draft

    def _require_approval(self, approval_id: str) -> OutboundApproval:
        approval = self._approvals.get(approval_id)
        if approval is None:
            raise ApprovalNotFoundError("approval not found")
        return approval

    def _decrypt_mailbox_password(self, mailbox: MailboxIdentity) -> str:
        if not mailbox.password_ciphertext:
            raise MailboxCredentialsError("mailbox credentials are unavailable")
        return self._secret_box.decrypt_text(mailbox.password_ciphertext)

    def _build_references(
        self,
        reply_to_message_id: str | None,
        reply_message: MailMessage | None,
    ) -> list[str]:
        if reply_message is not None:
            return unique_preserve_order([*reply_message.references, reply_message.internet_message_id])
        if reply_to_message_id:
            return [reply_to_message_id]
        return []

    def _create_thread(
        self,
        mailbox: MailboxIdentity,
        subject: str,
        event_at,
    ) -> MailThread:
        normalized_event_at = ensure_utc_datetime(event_at)
        thread = MailThread(
            organization_id=mailbox.organization_id,
            mailbox_id=mailbox.id,
            subject=subject.strip() or "(no subject)",
            normalized_subject=normalize_subject(subject),
            snippet=None,
            message_count=0,
            last_message_at=normalized_event_at,
        )
        self._threads.add(thread)
        return thread

    def _update_thread(
        self,
        thread: MailThread,
        preview_text: str | None,
        event_at,
    ) -> None:
        normalized_event_at = ensure_utc_datetime(event_at)
        current_last_message_at = ensure_utc_datetime(thread.last_message_at)
        thread.message_count += 1
        if normalized_event_at >= current_last_message_at:
            thread.last_message_at = normalized_event_at
            thread.snippet = preview_text
        self._session.add(thread)

    def _resolve_dkim(self, domain_id: str) -> tuple[str | None, str | None, str | None]:
        domain = self._domains.get(domain_id)
        if domain is None or not domain.dkim_private_key_ciphertext:
            return None, None, None
        try:
            private_key_pem = self._secret_box.decrypt_text(domain.dkim_private_key_ciphertext)
            return private_key_pem, domain.dkim_selector, domain.name
        except Exception:
            import logging
            logging.getLogger(__name__).warning("Failed to decrypt DKIM key for domain %s", domain_id)
            return None, None, None

    def _resolve_agent_for_mailbox(self, mailbox_id: str) -> AgentProfile | None:
        links = self._agent_mailbox_links.list_for_mailbox(mailbox_id)
        if not links:
            return None
        primary = next((l for l in links if l.is_primary), links[0])
        return self._agents.get(primary.agent_id)

    def _load_draft_attachments(self, draft_id: str) -> list[OutboundAttachment]:
        import logging
        logger = logging.getLogger(__name__)
        attachments = self._attachments.list_for_draft(draft_id)
        result: list[OutboundAttachment] = []
        for att in attachments:
            try:
                with open(att.storage_path, "rb") as fh:
                    data = fh.read()
                result.append(OutboundAttachment(
                    filename=att.filename,
                    content_type=att.content_type,
                    data=data,
                ))
            except Exception as exc:
                logger.warning("Skipping unreadable draft attachment %s: %s", att.filename, exc)
        return result

    def _save_inbound_attachments(self, envelope: InboundMessageEnvelope, message, mailbox) -> None:
        if not envelope.attachments:
            return
        import logging
        logger = logging.getLogger(__name__)
        storage_path = self._settings.attachment_storage_path
        max_mb = self._settings.max_attachment_size_mb
        attachment_service = AttachmentService(storage_path, max_mb)
        for inbound_att in envelope.attachments:
            try:
                att = attachment_service.save_inbound(
                    filename=inbound_att.filename,
                    content_type=inbound_att.content_type,
                    data=inbound_att.data,
                    organization_id=mailbox.organization_id,
                    mailbox_id=mailbox.id,
                    message_id=message.id,
                )
                self._attachments.add(att)
            except AttachmentTooLargeError as exc:
                logger.warning("Skipping oversized inbound attachment %s: %s", inbound_att.filename, exc)
            except Exception as exc:
                logger.warning("Failed to save inbound attachment %s: %s", inbound_att.filename, exc)

    def _resolve_thread_for_inbound(
        self,
        mailbox: MailboxIdentity,
        envelope: InboundMessageEnvelope,
    ) -> MailThread:
        message = None
        if envelope.in_reply_to:
            message = self._messages.get_by_mailbox_and_internet_id(mailbox.id, envelope.in_reply_to)
        if message is None and envelope.references:
            matches = self._messages.list_by_mailbox_and_internet_ids(mailbox.id, envelope.references)
            if matches:
                ordered_matches = {item.internet_message_id: item for item in matches}
                for reference in reversed(envelope.references):
                    message = ordered_matches.get(reference)
                    if message is not None:
                        break
        if message is not None:
            thread = self._threads.get(message.thread_id)
            if thread is not None:
                return thread
        return self._create_thread(
            mailbox,
            envelope.subject,
            ensure_utc_datetime(envelope.received_at or envelope.sent_at or utcnow()),
        )


def _inject_signature(
    text_body: str | None,
    html_body: str | None,
    agent: AgentProfile,
    storage_path: str,
) -> tuple[str | None, str | None, list[OutboundInlineImage]]:
    """Append the agent's email signature to the draft bodies."""
    import html as html_mod

    sig_text = (agent.signature or "").strip()

    # Plain-text signature
    updated_text = text_body
    if sig_text:
        plain_sig = f"\n\n--\n{sig_text}"
        if agent.name:
            plain_sig = f"\n\n--\n{sig_text}\n{agent.name}"
            if agent.title:
                plain_sig = f"\n\n--\n{sig_text}\n{agent.name} | {agent.title}"
        if text_body or not html_body:
            updated_text = (text_body or "") + plain_sig

    # Load the logo: sig-graphic preferred, avatar as fallback
    # Handles both local /v1/agents/... paths (disk read) and external https:// URLs (HTTP fetch)
    inline_images: list[OutboundInlineImage] = []
    logo_html = ""
    logo_data, logo_ct = _load_agent_logo(
        agent.id, storage_path,
        sig_graphic_url=agent.signature_graphic_url,
        avatar_url=agent.avatar_url,
    )
    if logo_data:
        cid = f"sig-logo-{agent.id}"
        inline_images.append(OutboundInlineImage(cid=cid, content_type=logo_ct, data=logo_data))
        logo_html = (
            f'<img src="cid:{cid}" alt="{html_mod.escape(agent.name or "")}"'
            f' width="48" height="48"'
            f' style="width:48px;height:48px;border-radius:8px;object-fit:contain;display:block">'
        )

    name_html = ""
    if agent.name:
        name_html = f'<strong style="font-size:14px;color:#111">{html_mod.escape(agent.name)}</strong>'
        if agent.title:
            name_html += f'<br><span style="font-size:12px;color:#666">{html_mod.escape(agent.title)}</span>'

    # Build HTML signature block only if there's something to show
    if not sig_text and not logo_html and not name_html:
        return updated_text, html_body, inline_images

    sig_lines = html_mod.escape(sig_text).replace("\n", "<br>")
    html_sig = '<div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5e5e5;font-family:sans-serif">'
    if sig_lines:
        html_sig += f'<div style="font-size:13px;color:#333;line-height:1.5">{sig_lines}</div>'
    if logo_html or name_html:
        html_sig += '<table cellpadding="0" cellspacing="0" border="0" style="margin-top:12px"><tr>'
        if logo_html:
            html_sig += f'<td style="vertical-align:middle;padding-right:12px">{logo_html}</td>'
        if name_html:
            html_sig += f'<td style="vertical-align:middle">{name_html}</td>'
        html_sig += '</tr></table>'
    html_sig += '</div>'

    updated_html = html_body
    if html_body:
        # Existing HTML draft — inject sig block and embed logo as CID inline image
        if "</body>" in html_body.lower():
            idx = html_body.lower().rfind("</body>")
            updated_html = html_body[:idx] + html_sig + html_body[idx:]
        else:
            updated_html = html_body + html_sig
    else:
        # Plain-text draft — keep it plain text so Gmail delivers to Primary inbox.
        # CID inline images require an HTML part; synthesizing one triggers Gmail's
        # Promotions classifier. Drop the logo for text-only drafts.
        inline_images = []
        updated_html = None

    return updated_text, updated_html, inline_images


_IMAGE_CT: dict[str, str] = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
}


def _load_agent_logo(
    agent_id: str,
    storage_path: str,
    *,
    sig_graphic_url: str | None,
    avatar_url: str | None,
) -> tuple[bytes | None, str]:
    """Load the agent logo bytes. Returns (data, content_type) or (None, '').

    - Local /v1/agents/... URLs → read from attachment_storage_path on disk
    - External https:// URLs → fetch via HTTP
    - Falls back: sig-graphic → avatar → disk scan
    """
    import glob as _glob
    import os

    def _read_disk(pattern: str) -> tuple[bytes | None, str]:
        matches = _glob.glob(pattern)
        if not matches:
            return None, ""
        path = matches[0]
        ext = os.path.splitext(path)[1].lower()
        ct = _IMAGE_CT.get(ext, "image/jpeg")
        try:
            with open(path, "rb") as fh:
                return fh.read(), ct
        except OSError:
            return None, ""

    def _resolve(url: str | None, disk_pattern: str) -> tuple[bytes | None, str]:
        if not url:
            return _read_disk(disk_pattern)
        if url.startswith("http://") or url.startswith("https://"):
            return _fetch_image(url)
        # local /v1/agents/... path → read from disk
        return _read_disk(disk_pattern)

    # Try signature graphic first
    data, ct = _resolve(
        sig_graphic_url,
        os.path.join(storage_path, "sig-graphics", agent_id, "signature.*"),
    )
    if data:
        return data, ct

    # Fall back to avatar
    return _resolve(
        avatar_url,
        os.path.join(storage_path, "avatars", agent_id, "avatar.*"),
    )


def _fetch_image(url: str) -> tuple[bytes | None, str]:
    """Fetch an image from an external URL. Returns (data, content_type) or (None, '')."""
    try:
        import httpx
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/"):
                return resp.content, resp.headers["content-type"].split(";")[0]
    except Exception as exc:
        logger.warning("Failed to fetch signature image %s: %s", url, exc)
    return None, ""
