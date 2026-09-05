"""Walk-forward protocol contracts; this module never loads research data."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Window:
    name: str
    start: str
    end: str


@dataclass(frozen=True)
class FreezeRecord:
    research_version: str
    validation_complete: bool
    frozen: bool


@dataclass(frozen=True)
class OOSAuthorization:
    token: str
    explicitly_authorized: bool = False


class OOSSealedError(PermissionError):
    pass


def build_protocol(*, train: Window, validation: Window, next_period: Window, freeze: FreezeRecord, oos_authorization: OOSAuthorization | None = None) -> tuple[Window, ...]:
    """Validate order and freeze state; returns metadata only, never executes."""
    if not freeze.validation_complete or not freeze.frozen:
        raise ValueError("walk-forward next period requires completed validation and a frozen record")
    if not (train.end < validation.start <= validation.end < next_period.start <= next_period.end):
        raise ValueError("walk-forward windows must be strictly ordered and non-overlapping")
    if next_period.name.upper() == "OOS":
        if oos_authorization is None or not oos_authorization.explicitly_authorized or not oos_authorization.token:
            raise OOSSealedError("OOS is sealed: explicit authorization is required before protocol construction")
    return (train, validation, next_period)
