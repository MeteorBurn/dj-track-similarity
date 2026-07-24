"""Canonical, immutable analysis-contract identities.

Every writer and reader must use :class:`ContractIdentity` rather than
constructing contract JSON or hashes independently.  The canonical payload is
fully deterministic and the registry is append-only at both the Python and
SQLite-schema layers.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping, Sequence, TypeAlias


FLOAT32_LE_ENCODING = "float32-le"
EMBEDDING_NORMALIZATIONS = frozenset({"none", "l2"})
ANALYSIS_FAMILIES = frozenset({"sonara", "maest", "mert", "muq", "clap"})
OUTPUT_KINDS_BY_FAMILY: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "sonara": frozenset({"core", "timeline", "embedding", "fingerprint"}),
        "maest": frozenset({"analysis", "embedding"}),
        "mert": frozenset({"embedding"}),
        "muq": frozenset({"embedding"}),
        "clap": frozenset({"embedding"}),
    }
)

_CANONICAL_KEYS = frozenset(
    {
        "analysis_family",
        "output_kind",
        "model_name",
        "model_version",
        "release_hash",
        "dim",
        "encoding",
        "normalization",
        "checkpoint_id",
        "preprocessing",
        "parameters",
    }
)

JsonValue: TypeAlias = Any


class ContractIdentityError(ValueError):
    """Raised when a contract identity is incomplete or non-canonical."""


class ContractRegistryError(RuntimeError):
    """Raised when the immutable Core contract registry is inconsistent."""


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ContractIdentityError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ContractIdentityError(f"{field_name} must be a non-empty string")
    return text


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _normalize_json(value: object, path: str = "parameters") -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractIdentityError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, JsonValue] = {}
        for key, child in value.items():
            if not isinstance(key, str) or not key:
                raise ContractIdentityError(f"{path} keys must be non-empty strings")
            normalized[key] = _normalize_json(child, f"{path}.{key}")
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview, str)):
        return [_normalize_json(child, f"{path}[]") for child in value]
    raise ContractIdentityError(f"{path} contains unsupported value type {type(value).__name__}")


def _freeze_json(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(child) for child in value)
    return value


def _thaw_json(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(child) for child in value]
    return value


@dataclass(frozen=True)
class ContractIdentity:
    """One canonical analysis output contract.

    Embedding contracts always carry positive ``dim``, ``float32-le`` encoding,
    and an explicit ``none`` or ``l2`` normalization.  Non-embedding contracts
    keep those three fields ``None`` and put output-specific immutable identity
    (for example SONARA feature lists and decoder details) in ``parameters``.
    """

    analysis_family: str
    output_kind: str
    model_name: str
    model_version: str | None = None
    release_hash: str | None = None
    dim: int | None = None
    encoding: str | None = None
    normalization: str | None = None
    checkpoint_id: str | None = None
    preprocessing: str | None = None
    parameters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        family = _required_text(self.analysis_family, "analysis_family").lower()
        output_kind = _required_text(self.output_kind, "output_kind").lower()
        if family not in ANALYSIS_FAMILIES:
            raise ContractIdentityError(f"unsupported analysis_family: {family!r}")
        if output_kind not in OUTPUT_KINDS_BY_FAMILY[family]:
            raise ContractIdentityError(
                f"unsupported output_kind {output_kind!r} for analysis_family {family!r}"
            )

        model_name = _required_text(self.model_name, "model_name")
        model_version = _optional_text(self.model_version, "model_version")
        release_hash = _optional_text(self.release_hash, "release_hash")
        checkpoint_id = _optional_text(self.checkpoint_id, "checkpoint_id")
        preprocessing = _optional_text(self.preprocessing, "preprocessing")

        if family == "sonara":
            if release_hash is None:
                raise ContractIdentityError("SONARA contracts require release_hash")
        elif release_hash is not None:
            raise ContractIdentityError("release_hash is reserved for SONARA contracts")

        if output_kind == "embedding":
            if isinstance(self.dim, bool) or not isinstance(self.dim, int) or self.dim <= 0:
                raise ContractIdentityError("embedding contracts require a positive integer dim")
            encoding = _required_text(self.encoding, "encoding").lower()
            if encoding != FLOAT32_LE_ENCODING:
                raise ContractIdentityError(
                    f"embedding encoding must be {FLOAT32_LE_ENCODING!r}"
                )
            normalization = _required_text(self.normalization, "normalization").lower()
            if normalization not in EMBEDDING_NORMALIZATIONS:
                raise ContractIdentityError(
                    f"embedding normalization must be one of {sorted(EMBEDDING_NORMALIZATIONS)}"
                )
            dim = self.dim
        else:
            if self.dim is not None or self.encoding is not None or self.normalization is not None:
                raise ContractIdentityError(
                    "non-embedding contracts must not define dim, encoding, or normalization"
                )
            dim = None
            encoding = None
            normalization = None

        normalized_parameters = _normalize_json(self.parameters)
        if not isinstance(normalized_parameters, dict):
            raise ContractIdentityError("parameters must be a JSON object")

        object.__setattr__(self, "analysis_family", family)
        object.__setattr__(self, "output_kind", output_kind)
        object.__setattr__(self, "model_name", model_name)
        object.__setattr__(self, "model_version", model_version)
        object.__setattr__(self, "release_hash", release_hash)
        object.__setattr__(self, "dim", dim)
        object.__setattr__(self, "encoding", encoding)
        object.__setattr__(self, "normalization", normalization)
        object.__setattr__(self, "checkpoint_id", checkpoint_id)
        object.__setattr__(self, "preprocessing", preprocessing)
        object.__setattr__(self, "parameters", _freeze_json(normalized_parameters))

    @property
    def canonical_payload(self) -> dict[str, JsonValue]:
        return {
            "analysis_family": self.analysis_family,
            "output_kind": self.output_kind,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "release_hash": self.release_hash,
            "dim": self.dim,
            "encoding": self.encoding,
            "normalization": self.normalization,
            "checkpoint_id": self.checkpoint_id,
            "preprocessing": self.preprocessing,
            "parameters": _thaw_json(self.parameters),
        }

    @property
    def canonical_payload_json(self) -> str:
        return json.dumps(
            self.canonical_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

    @property
    def contract_hash(self) -> str:
        digest = hashlib.sha256(self.canonical_payload_json.encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    @classmethod
    def from_canonical_payload_json(cls, payload_json: str) -> "ContractIdentity":
        try:
            payload = json.loads(payload_json)
        except (TypeError, json.JSONDecodeError) as error:
            raise ContractIdentityError("canonical_payload_json is not valid JSON") from error
        if not isinstance(payload, dict):
            raise ContractIdentityError("canonical_payload_json must contain a JSON object")
        actual_keys = frozenset(payload)
        if actual_keys != _CANONICAL_KEYS:
            missing = sorted(_CANONICAL_KEYS - actual_keys)
            extra = sorted(actual_keys - _CANONICAL_KEYS)
            raise ContractIdentityError(
                f"canonical payload keys mismatch; missing={missing}, extra={extra}"
            )
        identity = cls(**payload)
        if payload_json != identity.canonical_payload_json:
            raise ContractIdentityError("canonical_payload_json is not byte-canonical")
        return identity


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def read_registered_contract(
    connection: sqlite3.Connection,
    contract_hash: str,
) -> ContractIdentity | None:
    row = connection.execute(
        """
        SELECT contract_hash, analysis_family, output_kind, model_name,
               model_version, release_hash, canonical_payload_json
        FROM contracts
        WHERE contract_hash = ?
        """,
        (contract_hash,),
    ).fetchone()
    if row is None:
        return None

    values = tuple(row)
    stored_hash = str(values[0])
    try:
        identity = ContractIdentity.from_canonical_payload_json(str(values[6]))
    except ContractIdentityError as error:
        raise ContractRegistryError(f"contract {stored_hash} has invalid canonical payload") from error

    if stored_hash != identity.contract_hash:
        raise ContractRegistryError(f"contract {stored_hash} fails its self-hash")
    expected_columns = (
        identity.analysis_family,
        identity.output_kind,
        identity.model_name,
        identity.model_version,
        identity.release_hash,
    )
    stored_columns = (
        str(values[1]),
        str(values[2]),
        str(values[3]),
        None if values[4] is None else str(values[4]),
        None if values[5] is None else str(values[5]),
    )
    if stored_columns != expected_columns:
        raise ContractRegistryError(
            f"contract {stored_hash} registry columns do not match its canonical payload"
        )
    return identity


def require_registered_contract(
    connection: sqlite3.Connection,
    expected: ContractIdentity,
) -> ContractIdentity:
    registered = read_registered_contract(connection, expected.contract_hash)
    if registered is None:
        raise ContractRegistryError(
            f"unknown contract in registry: {expected.contract_hash}"
        )
    if registered.canonical_payload_json != expected.canonical_payload_json:
        raise ContractRegistryError(
            f"registered contract identity mismatch: {expected.contract_hash}"
        )
    return registered


def register_contract(
    connection: sqlite3.Connection,
    identity: ContractIdentity,
    *,
    created_at: str | None = None,
) -> str:
    """Atomically insert an immutable contract, or verify the exact row.

    When called with an idle connection this function owns a short
    ``BEGIN IMMEDIATE`` transaction and commits it.  When the caller already
    owns a transaction, that ownership is preserved: this function neither
    starts another transaction nor commits or rolls back the caller's work.
    """

    owns_transaction = not connection.in_transaction
    try:
        if owns_transaction:
            connection.execute("BEGIN IMMEDIATE")

        connection.execute(
            """
            INSERT INTO contracts (
                contract_hash, analysis_family, output_kind, model_name,
                model_version, release_hash, canonical_payload_json, created_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                COALESCE(
                    (
                        SELECT created_at
                        FROM contracts
                        WHERE contract_hash = ?
                    ),
                    ?
                )
            )
            ON CONFLICT(contract_hash) DO NOTHING
            """,
            (
                identity.contract_hash,
                identity.analysis_family,
                identity.output_kind,
                identity.model_name,
                identity.model_version,
                identity.release_hash,
                identity.canonical_payload_json,
                identity.contract_hash,
                created_at or utc_timestamp(),
            ),
        )
        registered = read_registered_contract(connection, identity.contract_hash)
        if registered is None:
            raise ContractRegistryError(
                f"contract insert was not visible: {identity.contract_hash}"
            )
        if registered.canonical_payload_json != identity.canonical_payload_json:
            raise ContractRegistryError(
                f"contract hash collision or registry mismatch: {identity.contract_hash}"
            )

        if owns_transaction:
            connection.commit()
        return identity.contract_hash
    except BaseException:
        if owns_transaction and connection.in_transaction:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
        raise
