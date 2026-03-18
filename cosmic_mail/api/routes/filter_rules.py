from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from cosmic_mail.api.auth import AuthContext, authorize_agent, authorize_mailbox
from cosmic_mail.api.deps import get_auth_context, get_session
from cosmic_mail.domain.schemas import (
    FilterCheckRequest,
    FilterCheckResult,
    FilterCheckViolation,
    FilterRuleBulkCreate,
    FilterRuleBulkResult,
    FilterRuleCreate,
    FilterRuleRead,
)
from cosmic_mail.services.filter_rules import (
    FilterRuleNotFoundError,
    FilterRuleService,
    FilterScopeNotFoundError,
)

# ── Agent-scoped filter rules ─────────────────────────────────────────────────

agent_filter_router = APIRouter(prefix="/agents", tags=["filter-rules"])


@agent_filter_router.get("/{agent_id}/filter-rules", response_model=list[FilterRuleRead])
def list_agent_filter_rules(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[FilterRuleRead]:
    authorize_agent(session, auth, agent_id)
    service = FilterRuleService(session)
    rules = service.list(scope_type="agent", scope_id=agent_id)
    return [FilterRuleRead.model_validate(r) for r in rules]


@agent_filter_router.post("/{agent_id}/filter-rules", response_model=FilterRuleRead, status_code=status.HTTP_201_CREATED)
def create_agent_filter_rule(
    agent_id: str,
    payload: FilterRuleCreate,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> FilterRuleRead:
    agent = authorize_agent(session, auth, agent_id)
    service = FilterRuleService(session)
    try:
        rule = service.create(
            organization_id=agent.organization_id,
            scope_type="agent",
            scope_id=agent_id,
            payload=payload,
        )
    except FilterScopeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return FilterRuleRead.model_validate(rule)


@agent_filter_router.post("/{agent_id}/filter-rules/bulk", response_model=FilterRuleBulkResult, status_code=status.HTTP_201_CREATED)
def bulk_create_agent_filter_rules(
    agent_id: str,
    payload: FilterRuleBulkCreate,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> FilterRuleBulkResult:
    agent = authorize_agent(session, auth, agent_id)
    service = FilterRuleService(session)
    try:
        rules = service.create_bulk(
            organization_id=agent.organization_id,
            scope_type="agent",
            scope_id=agent_id,
            rules=payload.rules,
        )
    except FilterScopeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return FilterRuleBulkResult(
        created=[FilterRuleRead.model_validate(r) for r in rules],
        count=len(rules),
    )


@agent_filter_router.get("/{agent_id}/filter-rules/{rule_id}", response_model=FilterRuleRead)
def get_agent_filter_rule(
    agent_id: str,
    rule_id: str,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> FilterRuleRead:
    agent = authorize_agent(session, auth, agent_id)
    service = FilterRuleService(session)
    try:
        rule = service.get(rule_id, organization_id=agent.organization_id)
    except FilterRuleNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if rule.scope_type != "agent" or rule.scope_id != agent_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="filter rule not found")
    return FilterRuleRead.model_validate(rule)


@agent_filter_router.delete("/{agent_id}/filter-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_agent_filter_rule(
    agent_id: str,
    rule_id: str,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> None:
    agent = authorize_agent(session, auth, agent_id)
    service = FilterRuleService(session)
    try:
        rule = service.get(rule_id, organization_id=agent.organization_id)
    except FilterRuleNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if rule.scope_type != "agent" or rule.scope_id != agent_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="filter rule not found")
    service.delete(rule_id, organization_id=agent.organization_id)


# ── Inbox-scoped filter rules ─────────────────────────────────────────────────

inbox_filter_router = APIRouter(prefix="/mailboxes", tags=["filter-rules"])


@inbox_filter_router.get("/{mailbox_id}/filter-rules", response_model=list[FilterRuleRead])
def list_inbox_filter_rules(
    mailbox_id: str,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[FilterRuleRead]:
    authorize_mailbox(session, auth, mailbox_id)
    service = FilterRuleService(session)
    rules = service.list(scope_type="inbox", scope_id=mailbox_id)
    return [FilterRuleRead.model_validate(r) for r in rules]


@inbox_filter_router.post("/{mailbox_id}/filter-rules", response_model=FilterRuleRead, status_code=status.HTTP_201_CREATED)
def create_inbox_filter_rule(
    mailbox_id: str,
    payload: FilterRuleCreate,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> FilterRuleRead:
    mailbox = authorize_mailbox(session, auth, mailbox_id)
    service = FilterRuleService(session)
    try:
        rule = service.create(
            organization_id=mailbox.organization_id,
            scope_type="inbox",
            scope_id=mailbox_id,
            payload=payload,
        )
    except FilterScopeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return FilterRuleRead.model_validate(rule)


@inbox_filter_router.post("/{mailbox_id}/filter-rules/bulk", response_model=FilterRuleBulkResult, status_code=status.HTTP_201_CREATED)
def bulk_create_inbox_filter_rules(
    mailbox_id: str,
    payload: FilterRuleBulkCreate,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> FilterRuleBulkResult:
    mailbox = authorize_mailbox(session, auth, mailbox_id)
    service = FilterRuleService(session)
    try:
        rules = service.create_bulk(
            organization_id=mailbox.organization_id,
            scope_type="inbox",
            scope_id=mailbox_id,
            rules=payload.rules,
        )
    except FilterScopeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return FilterRuleBulkResult(
        created=[FilterRuleRead.model_validate(r) for r in rules],
        count=len(rules),
    )


@inbox_filter_router.get("/{mailbox_id}/filter-rules/{rule_id}", response_model=FilterRuleRead)
def get_inbox_filter_rule(
    mailbox_id: str,
    rule_id: str,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> FilterRuleRead:
    mailbox = authorize_mailbox(session, auth, mailbox_id)
    service = FilterRuleService(session)
    try:
        rule = service.get(rule_id, organization_id=mailbox.organization_id)
    except FilterRuleNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if rule.scope_type != "inbox" or rule.scope_id != mailbox_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="filter rule not found")
    return FilterRuleRead.model_validate(rule)


@inbox_filter_router.delete("/{mailbox_id}/filter-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_inbox_filter_rule(
    mailbox_id: str,
    rule_id: str,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> None:
    mailbox = authorize_mailbox(session, auth, mailbox_id)
    service = FilterRuleService(session)
    try:
        rule = service.get(rule_id, organization_id=mailbox.organization_id)
    except FilterRuleNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if rule.scope_type != "inbox" or rule.scope_id != mailbox_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="filter rule not found")
    service.delete(rule_id, organization_id=mailbox.organization_id)


# ── Utility: test check ───────────────────────────────────────────────────────

filter_check_router = APIRouter(prefix="/filter-rules", tags=["filter-rules"])


@filter_check_router.post("/check", response_model=FilterCheckResult)
def check_filter_rules(
    payload: FilterCheckRequest,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> FilterCheckResult:
    """Test whether a set of recipients would be blocked by current filter rules.

    Useful for pre-flight checks before creating a draft.
    """
    # Authorise access to the mailbox
    authorize_mailbox(session, auth, payload.mailbox_id)

    all_recipients = [c.email for c in payload.to_recipients + payload.cc_recipients + payload.bcc_recipients]
    service = FilterRuleService(session)
    violations = service.check_recipients(
        agent_id=payload.agent_id,
        mailbox_id=payload.mailbox_id,
        recipients=all_recipients,
    )
    return FilterCheckResult(
        passed=len(violations) == 0,
        blocked=[
            FilterCheckViolation(
                email=v.email,
                reason=v.reason,
                scope=v.scope,
                rule_id=v.rule_id,
            )
            for v in violations
        ],
    )
