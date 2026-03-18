from __future__ import annotations

import fnmatch
from dataclasses import dataclass

from sqlalchemy.orm import Session

from cosmic_mail.domain.models import AgentProfile, MailboxIdentity, OutboundFilterRule
from cosmic_mail.domain.repositories import (
    AgentMailboxLinkRepository,
    AgentRepository,
    FilterRuleRepository,
    MailboxRepository,
    OrganizationRepository,
)
from cosmic_mail.domain.schemas import FilterRuleCreate


class FilterRuleNotFoundError(ValueError):
    pass


class FilterScopeNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class FilterViolation:
    email: str
    reason: str
    scope: str      # "agent" | "inbox"
    rule_id: str    # empty string if violation is from whitelist (no matching rule)


def _matches(email: str, rule: OutboundFilterRule) -> bool:
    """Return True if the email address matches this rule's pattern."""
    pattern = rule.pattern.lower()
    pt = rule.pattern_type

    if pt == "exact":
        return email == pattern

    if pt == "domain":
        parts = email.rsplit("@", 1)
        return len(parts) == 2 and parts[1] == pattern

    if pt == "subdomain":
        parts = email.rsplit("@", 1)
        if len(parts) != 2:
            return False
        d = parts[1]
        return d == pattern or d.endswith("." + pattern)

    if pt == "wildcard":
        return fnmatch.fnmatch(email, pattern)

    return False


class FilterRuleService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._rules = FilterRuleRepository(session)
        self._agents = AgentRepository(session)
        self._mailboxes = MailboxRepository(session)
        self._organizations = OrganizationRepository(session)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        organization_id: str,
        scope_type: str,
        scope_id: str,
        payload: FilterRuleCreate,
    ) -> OutboundFilterRule:
        self._validate_scope(organization_id, scope_type, scope_id)
        rule = OutboundFilterRule(
            organization_id=organization_id,
            scope_type=scope_type,
            scope_id=scope_id,
            rule_type=payload.rule_type,
            pattern_type=payload.pattern_type,
            pattern=payload.pattern,
            label=payload.label,
            notes=payload.notes,
        )
        self._rules.add(rule)
        self._session.commit()
        self._session.refresh(rule)
        return rule

    def create_bulk(
        self,
        *,
        organization_id: str,
        scope_type: str,
        scope_id: str,
        rules: list[FilterRuleCreate],
    ) -> list[OutboundFilterRule]:
        self._validate_scope(organization_id, scope_type, scope_id)
        created: list[OutboundFilterRule] = []
        for payload in rules:
            rule = OutboundFilterRule(
                organization_id=organization_id,
                scope_type=scope_type,
                scope_id=scope_id,
                rule_type=payload.rule_type,
                pattern_type=payload.pattern_type,
                pattern=payload.pattern,
                label=payload.label,
                notes=payload.notes,
            )
            self._rules.add(rule)
            created.append(rule)
        self._session.commit()
        for rule in created:
            self._session.refresh(rule)
        return created

    def list(self, *, scope_type: str, scope_id: str) -> list[OutboundFilterRule]:
        return self._rules.list_for_scope(scope_type, scope_id)

    def get(self, rule_id: str, *, organization_id: str) -> OutboundFilterRule:
        rule = self._rules.get(rule_id)
        if rule is None or rule.organization_id != organization_id:
            raise FilterRuleNotFoundError("filter rule not found")
        return rule

    def delete(self, rule_id: str, *, organization_id: str) -> None:
        rule = self._rules.get(rule_id)
        if rule is None or rule.organization_id != organization_id:
            raise FilterRuleNotFoundError("filter rule not found")
        self._rules.delete(rule)
        self._session.commit()

    # ── Enforcement ───────────────────────────────────────────────────────────

    def check_recipients(
        self,
        *,
        agent_id: str | None,
        mailbox_id: str,
        recipients: list[str],
    ) -> list[FilterViolation]:
        """Return violations for any blocked recipients.

        Precedence:
        1. Blacklists (agent + inbox, first match wins)
        2. Agent whitelists — if any exist, recipient must match at least one
        3. Inbox whitelists — if any exist, recipient must match at least one
        """
        agent_rules = self._rules.list_for_scope("agent", agent_id) if agent_id else []
        inbox_rules = self._rules.list_for_scope("inbox", mailbox_id)

        all_blacklist = [(s, r) for s, rules in (("agent", agent_rules), ("inbox", inbox_rules)) for r in rules if r.rule_type == "blacklist"]
        agent_whitelist = [r for r in agent_rules if r.rule_type == "whitelist"]
        inbox_whitelist = [r for r in inbox_rules if r.rule_type == "whitelist"]

        violations: list[FilterViolation] = []

        for email in recipients:
            el = email.lower()

            # 1. Blacklists
            blocked = False
            for scope, rule in all_blacklist:
                if _matches(el, rule):
                    violations.append(FilterViolation(
                        email=email,
                        reason=f"blocked by {scope} blacklist rule: {rule.pattern}",
                        scope=scope,
                        rule_id=rule.id,
                    ))
                    blocked = True
                    break
            if blocked:
                continue

            # 2. Agent whitelist gate
            if agent_whitelist and not any(_matches(el, r) for r in agent_whitelist):
                violations.append(FilterViolation(
                    email=email,
                    reason="not permitted by agent whitelist",
                    scope="agent",
                    rule_id="",
                ))
                continue

            # 3. Inbox whitelist gate
            if inbox_whitelist and not any(_matches(el, r) for r in inbox_whitelist):
                violations.append(FilterViolation(
                    email=email,
                    reason="not permitted by inbox whitelist",
                    scope="inbox",
                    rule_id="",
                ))

        return violations

    # ── Private ───────────────────────────────────────────────────────────────

    def _validate_scope(self, organization_id: str, scope_type: str, scope_id: str) -> None:
        if scope_type == "agent":
            agent = self._agents.get(scope_id)
            if agent is None or agent.organization_id != organization_id:
                raise FilterScopeNotFoundError("agent not found")
        elif scope_type == "inbox":
            mailbox = self._mailboxes.get(scope_id)
            if mailbox is None or mailbox.organization_id != organization_id:
                raise FilterScopeNotFoundError("inbox not found")
        else:
            raise ValueError(f"invalid scope_type: {scope_type!r}")
