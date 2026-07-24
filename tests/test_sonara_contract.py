from __future__ import annotations

import inspect
from dataclasses import replace

import pytest

from dj_track_similarity.analysis_contracts import ContractIdentityError
from dj_track_similarity.analysis_models import validate_production_contract
from dj_track_similarity.sonara_contract import (
    SONARA_ANALYSIS_HOP_SAMPLES,
    SONARA_EMBEDDING_DIM,
    SONARA_EXPECTED_SCHEMA_VERSION,
    SONARA_EXPECTED_VERSION,
    SONARA_FINGERPRINT_VERSION,
    SONARA_OUTPUT_KINDS,
    SONARA_PROJECT_FEATURE_REVISION,
    SONARA_UNIT_INTERVAL_CLAMP_EPSILON,
    SONARA_UNIT_INTERVAL_CLAMP_FIELDS,
    SONARA_UNIT_INTERVAL_CLAMP_POLICY,
    SonaraRuntimeIdentityError,
    build_sonara_contracts,
    normalize_sonara_outputs,
    resolve_sonara_runtime_identity,
    sonara_requested_features,
    sonara_runtime_contracts,
)


_BUILD_A = "sha256:" + "1" * 64
_BUILD_B = "sha256:" + "2" * 64
_VOCAL_BUILD_A = "sha256:" + "3" * 64
_VOCAL_BUILD_B = "sha256:" + "4" * 64


class FakeSonara:
    __version__ = SONARA_EXPECTED_VERSION
    SIMILARITY_VERSION = 2
    __sonara_build_id__ = _BUILD_A
    __sonara_vocalness_model_id__ = "sonara-vocalness-v2"
    __sonara_vocalness_model_build_id__ = _VOCAL_BUILD_A


def test_runtime_factory_returns_complete_four_output_release() -> None:
    contracts = sonara_runtime_contracts(FakeSonara)

    assert contracts.release_hash.startswith("sha256:")
    assert tuple(
        (identity.analysis_family, identity.output_kind)
        for identity in contracts.identities
    ) == (
        ("sonara", "core"),
        ("sonara", "timeline"),
        ("sonara", "embedding"),
        ("sonara", "fingerprint"),
    )
    assert {identity.release_hash for identity in contracts.identities} == {
        contracts.release_hash
    }
    assert contracts.runtime.schema_version == SONARA_EXPECTED_SCHEMA_VERSION
    assert contracts.runtime.analysis_hop_samples == SONARA_ANALYSIS_HOP_SAMPLES
    assert contracts.runtime.project_feature_revision == 6
    assert (
        contracts.runtime.unit_interval_clamp_policy
        == SONARA_UNIT_INTERVAL_CLAMP_POLICY
    )
    assert (
        contracts.runtime.unit_interval_clamp_epsilon
        == SONARA_UNIT_INTERVAL_CLAMP_EPSILON
    )
    assert (
        contracts.runtime.unit_interval_clamp_fields
        == SONARA_UNIT_INTERVAL_CLAMP_FIELDS
    )
    assert contracts.embedding.dim == SONARA_EMBEDDING_DIM
    assert contracts.embedding.encoding == "float32-le"
    assert contracts.embedding.normalization == "none"
    assert (
        dict(contracts.fingerprint.parameters)["fingerprint_version"]
        == SONARA_FINGERPRINT_VERSION
    )
    assert dict(contracts.fingerprint.parameters)["fingerprint_encoding"] == "uint32-le"
    assert dict(contracts.fingerprint.parameters)["fingerprint_byte_order"] == "little"


def test_fake_runtime_has_golden_release_and_contract_hashes() -> None:
    contracts = sonara_runtime_contracts(FakeSonara)

    assert contracts.release_hash == (
        "sha256:c8e479af204bc7a39d931f3719c4a720868b8859cbfdeff9f9bd4a0c5a86881e"
    )
    assert {
        identity.output_kind: identity.contract_hash
        for identity in contracts.identities
    } == {
        "core": "sha256:549df36a051f8c96b07c795b4c15a0143693ee7e649677b8aef388ccd677dcd2",
        "timeline": "sha256:055b14b5b9024bb039d1221ac461c90eb188ce8c9b810c2a91c78c37bc74f8e1",
        "embedding": "sha256:b2fe36a33da0e7fb214f3d5b3d4f97a87f9c956b2fc58aa610ba02751ffc2e9a",
        "fingerprint": "sha256:2f3803c483ade1676ece0ecd89ef078212a43ff9fbd7ad9b9f8d9ab5557a8155",
    }


def test_every_contract_has_strict_production_identity() -> None:
    contracts = sonara_runtime_contracts(FakeSonara)

    for identity in contracts.identities:
        validate_production_contract(identity)
        parameters = dict(identity.parameters)
        assert identity.model_name == "sonara-playlist"
        assert identity.model_version == SONARA_EXPECTED_VERSION
        assert identity.checkpoint_id == _BUILD_A
        assert identity.preprocessing
        assert parameters["identity_factory"] == "sonara-runtime-v1"
        assert parameters["package_build_id"] == _BUILD_A
        assert parameters["vocalness_model_id"] == "sonara-vocalness-v2"
        assert parameters["vocalness_model_build_id"] == _VOCAL_BUILD_A
        assert tuple(parameters["requested_features"])


def test_release_hash_cannot_be_supplied_by_factory_caller() -> None:
    assert "release_hash" not in inspect.signature(sonara_runtime_contracts).parameters
    assert "release_hash" not in inspect.signature(build_sonara_contracts).parameters


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("package_version", "0.2.9+different-build"),
        ("package_build_id", _BUILD_B),
        ("schema_version", 5),
        ("mode", "full"),
        ("sample_rate_hz", 44_100),
        ("bpm_min", 69),
        ("bpm_max", 181),
        ("project_feature_revision", SONARA_PROJECT_FEATURE_REVISION + 1),
        ("decoder_backend", "another-decoder"),
        ("execution_path", "analyze_file"),
        ("analysis_hop_samples", 256),
        ("unit_interval_clamp_policy", "another-clamp-policy"),
        ("unit_interval_clamp_epsilon", 0.002),
        ("vocalness_model_id", "another-vocalness-model"),
        ("vocalness_model_build_id", _VOCAL_BUILD_B),
        ("embedding_version", 3),
        ("embedding_dim", 49),
        ("embedding_normalization", "l2"),
        ("fingerprint_version", 2),
        ("fingerprint_encoding", "uint64-le"),
        ("fingerprint_byte_order", "big"),
    ],
)
def test_every_runtime_field_changes_release_and_contract_hashes(
    field_name: str,
    replacement: object,
) -> None:
    runtime = resolve_sonara_runtime_identity(FakeSonara)
    baseline = build_sonara_contracts(runtime)
    changed = build_sonara_contracts(replace(runtime, **{field_name: replacement}))

    assert changed.release_hash != baseline.release_hash
    assert {identity.contract_hash for identity in changed.identities}.isdisjoint(
        identity.contract_hash for identity in baseline.identities
    )


def test_clamp_field_list_changes_release_and_every_output_contract() -> None:
    runtime = resolve_sonara_runtime_identity(FakeSonara)
    baseline = build_sonara_contracts(runtime)
    changed = build_sonara_contracts(
        replace(
            runtime,
            unit_interval_clamp_fields=(
                *runtime.unit_interval_clamp_fields,
                "another_unit_interval_field",
            ),
        )
    )

    assert changed.release_hash != baseline.release_hash
    assert {identity.contract_hash for identity in changed.identities}.isdisjoint(
        identity.contract_hash for identity in baseline.identities
    )


def test_unsupported_embedding_encoding_changes_release_but_is_not_activatable() -> (
    None
):
    runtime = resolve_sonara_runtime_identity(FakeSonara)
    changed = replace(runtime, embedding_encoding="float64-le")

    assert changed.release_hash != runtime.release_hash
    with pytest.raises(ContractIdentityError, match="embedding encoding"):
        build_sonara_contracts(changed)


@pytest.mark.parametrize(
    "field_name",
    [
        "core_requested_features",
        "timeline_requested_features",
        "embedding_requested_features",
        "fingerprint_requested_features",
    ],
)
def test_each_output_feature_set_changes_release_and_contracts(
    field_name: str,
) -> None:
    runtime = resolve_sonara_runtime_identity(FakeSonara)
    baseline = build_sonara_contracts(runtime)
    changed_features = (*getattr(runtime, field_name), "future_feature")
    changed = build_sonara_contracts(replace(runtime, **{field_name: changed_features}))

    assert changed.release_hash != baseline.release_hash
    assert tuple(identity.contract_hash for identity in changed.identities) != tuple(
        identity.contract_hash for identity in baseline.identities
    )


def test_feature_order_does_not_create_a_spurious_release() -> None:
    runtime = resolve_sonara_runtime_identity(FakeSonara)
    reordered = replace(
        runtime,
        core_requested_features=tuple(reversed(runtime.core_requested_features)),
    )

    assert reordered.release_hash == runtime.release_hash


def test_runtime_factory_rejects_unpinned_package_and_embedding_versions() -> None:
    class WrongPackage(FakeSonara):
        __version__ = "0.3.0"

    class WrongEmbedding(FakeSonara):
        SIMILARITY_VERSION = 3

    with pytest.raises(SonaraRuntimeIdentityError, match="0.2.9 is required"):
        resolve_sonara_runtime_identity(WrongPackage)
    with pytest.raises(SonaraRuntimeIdentityError, match="similarity version"):
        resolve_sonara_runtime_identity(WrongEmbedding)


def test_runtime_factory_rejects_missing_or_malformed_build_identity() -> None:
    class MissingBuild:
        __version__ = SONARA_EXPECTED_VERSION
        SIMILARITY_VERSION = 2
        __sonara_vocalness_model_id__ = "sonara-vocalness-v2"
        __sonara_vocalness_model_build_id__ = _VOCAL_BUILD_A

    class MalformedBuild(MissingBuild):
        __sonara_build_id__ = "not-a-hash"

    with pytest.raises(SonaraRuntimeIdentityError, match="build_id"):
        resolve_sonara_runtime_identity(MissingBuild)
    with pytest.raises(SonaraRuntimeIdentityError, match="sha256"):
        resolve_sonara_runtime_identity(MalformedBuild)


def test_canonical_outputs_have_no_representations_alias() -> None:
    assert normalize_sonara_outputs(None) == ("core",)
    assert normalize_sonara_outputs(("fingerprint", "timeline", "embedding")) == (
        "core",
        "timeline",
        "embedding",
        "fingerprint",
    )
    with pytest.raises(ValueError, match="unsupported SONARA output"):
        normalize_sonara_outputs(("representations",))


def test_native_analysis_request_is_sorted_union_of_all_four_contracts() -> None:
    runtime = resolve_sonara_runtime_identity(FakeSonara)
    requested = sonara_requested_features(runtime=runtime)
    expected = tuple(
        sorted(
            {
                feature
                for output in SONARA_OUTPUT_KINDS
                for feature in runtime.requested_features_by_output[output]
            }
        )
    )

    assert requested == expected
    assert tuple(inspect.signature(sonara_requested_features).parameters) == (
        "runtime",
    )
    assert "embedding" in requested
    assert "fingerprint" in requested
    assert "vocalness" in requested
    assert len(requested) == len(set(requested))
    assert "instrumentalness" not in requested


def test_installed_sonara_runtime_can_be_identified_when_available() -> None:
    pytest.importorskip("sonara")

    contracts = sonara_runtime_contracts()

    assert contracts.runtime.package_version == SONARA_EXPECTED_VERSION
    assert contracts.runtime.package_build_id.startswith("sha256:")
    assert contracts.runtime.vocalness_model_id == "sonara-vocalness-v2"
    assert contracts.runtime.vocalness_model_build_id.startswith("sha256:")
