from __future__ import annotations

import re


DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
LOCAL_PART_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._+-]{0,63})$")


def normalize_domain_name(value: str) -> str:
    domain = value.strip().rstrip(".").lower()
    labels = domain.split(".")
    if len(domain) > 253 or len(labels) < 2:
        raise ValueError("invalid domain name")
    if any(not DOMAIN_LABEL_RE.match(label) for label in labels):
        raise ValueError("invalid domain name")
    return domain


def normalize_local_part(value: str) -> str:
    local_part = value.strip().lower()
    if not LOCAL_PART_RE.match(local_part):
        raise ValueError("invalid local part")
    return local_part


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("unable to derive a slug")
    return slug[:120]

