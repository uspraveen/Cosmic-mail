from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import dns.resolver

from cosmic_mail.core.config import Settings
from cosmic_mail.domain.models import Domain
from cosmic_mail.domain.schemas import DNSRecord, DomainVerificationCheck


@dataclass(frozen=True)
class DkimKeyPair:
    public_key: str
    private_key_pem: str


class DNSVerifier(Protocol):
    def lookup(self, record_type: str, host: str) -> list[str]:
        ...


class DnsPythonVerifier:
    def lookup(self, record_type: str, host: str) -> list[str]:
        try:
            answers = dns.resolver.resolve(host, record_type)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.LifetimeTimeout):
            return []

        if record_type == "TXT":
            values: list[str] = []
            for record in answers:
                if hasattr(record, "strings"):
                    parts = [part.decode("utf-8") for part in record.strings]
                    values.append("".join(parts))
                else:
                    values.append(str(record).strip('"'))
            return values

        if record_type == "MX":
            return [
                f"{record.preference} {record.exchange.to_text().rstrip('.')}"
                for record in answers
            ]

        return [str(record) for record in answers]


class ExternalDnsVerifier:
    """DNS verifier that queries via a public resolver (default: 8.8.8.8).

    Use this for deliverability checks that need to validate records as the
    outside world would see them, bypassing any local resolver caching.
    """

    def __init__(self, nameserver: str = "8.8.8.8") -> None:
        self._nameserver = nameserver

    def lookup(self, record_type: str, host: str) -> list[str]:
        try:
            resolver = dns.resolver.Resolver(configure=False)
            resolver.nameservers = [self._nameserver]
            resolver.lifetime = 8.0
            answers = resolver.resolve(host, record_type)
        except (
            dns.resolver.NXDOMAIN,
            dns.resolver.NoAnswer,
            dns.resolver.LifetimeTimeout,
            dns.resolver.NoNameservers,
        ):
            return []

        if record_type == "TXT":
            values: list[str] = []
            for record in answers:
                if hasattr(record, "strings"):
                    parts = [part.decode("utf-8") for part in record.strings]
                    values.append("".join(parts))
                else:
                    values.append(str(record).strip('"'))
            return values

        if record_type == "MX":
            return [
                f"{record.preference} {record.exchange.to_text().rstrip('.')}"
                for record in answers
            ]

        return [str(record) for record in answers]


# Well-known DNSBL zones ordered by coverage
DNSBL_ZONES: list[str] = [
    "zen.spamhaus.org",
    "bl.spamcop.net",
    "dnsbl.sorbs.net",
]


def resolve_mx_ip(mx_hostname: str, nameserver: str = "8.8.8.8") -> str | None:
    """Resolve a mail-server hostname to its first IPv4 address via a public resolver."""
    try:
        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = [nameserver]
        resolver.lifetime = 5.0
        answers = resolver.resolve(mx_hostname, "A")
        return str(answers[0])
    except Exception:
        return None


def check_ip_blacklists(
    ip: str,
    *,
    zones: list[str] | None = None,
    nameserver: str = "8.8.8.8",
) -> list[tuple[str, bool]]:
    """Check an IPv4 address against DNSBL zones.

    Returns a list of (zone, listed) tuples.  A network timeout or other error
    on a specific zone is treated as not-listed for that zone so it does not
    block the full check.
    """
    parts = ip.split(".")
    if len(parts) != 4:
        return []
    reversed_ip = ".".join(reversed(parts))
    zones_to_check = zones if zones is not None else DNSBL_ZONES
    results: list[tuple[str, bool]] = []
    for zone in zones_to_check:
        lookup_host = f"{reversed_ip}.{zone}"
        try:
            resolver = dns.resolver.Resolver(configure=False)
            resolver.nameservers = [nameserver]
            resolver.lifetime = 5.0
            resolver.resolve(lookup_host, "A")
            results.append((zone, True))
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            results.append((zone, False))
        except Exception:
            # Timeout or nameserver error — skip without failing
            results.append((zone, False))
    return results


def build_dns_records(domain: Domain, settings: Settings) -> list[DNSRecord]:
    return [
        DNSRecord(
            type="MX",
            host=domain.name,
            value=domain.mx_target,
            priority=domain.mx_priority,
            ttl=settings.default_dns_ttl,
        ),
        DNSRecord(
            type="TXT",
            host=domain.name,
            value=domain.spf_value,
            ttl=settings.default_dns_ttl,
        ),
        DNSRecord(
            type="TXT",
            host=f"{domain.dkim_selector}._domainkey.{domain.name}",
            value=f"v=DKIM1; k=rsa; p={domain.dkim_public_key}",
            ttl=settings.default_dns_ttl,
        ),
        DNSRecord(
            type="TXT",
            host=f"_dmarc.{domain.name}",
            value=domain.dmarc_value,
            ttl=settings.default_dns_ttl,
        ),
    ]


def verify_dns_records(
    records: Sequence[DNSRecord],
    verifier: DNSVerifier,
) -> list[DomainVerificationCheck]:
    checks: list[DomainVerificationCheck] = []
    for record in records:
        observed = verifier.lookup(record.type, record.host)
        expected = format_record_value(record)
        checks.append(
            DomainVerificationCheck(
                type=record.type,
                host=record.host,
                expected=expected,
                observed=observed,
                matched=any(
                    _normalize_value(record.type, value) == _normalize_value(record.type, expected)
                    for value in observed
                ),
            )
        )
    return checks


def format_record_value(record: DNSRecord) -> str:
    if record.type == "MX" and record.priority is not None:
        return f"{record.priority} {record.value}"
    return record.value


def _normalize_value(record_type: str, value: str) -> str:
    normalized = value.strip().strip('"').rstrip(".")
    if record_type == "TXT":
        return " ".join(normalized.split())
    return normalized.lower()

