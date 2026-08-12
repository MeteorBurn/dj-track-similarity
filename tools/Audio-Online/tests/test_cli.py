from __future__ import annotations

from pathlib import Path

import metadata_enrichment_cli as cli


def test_authorize_beatport_uses_local_config_without_printing_secret(monkeypatch, tmp_path: Path, capsys) -> None:
    """CLI authorization forwards only the config path and keeps secrets out of output."""

    config_path = tmp_path / "config.toml"
    config_path.write_text("[sources.beatport]\nclient_id = 'id'\nclient_secret = 'secret'\n", encoding="utf-8")
    calls: list[Path] = []
    monkeypatch.setattr(cli, "authorize_beatport", lambda path, *_args, **_kwargs: calls.append(path) or "Beatport authorization saved.")

    assert cli.main(["authorize", "beatport", "--config", str(config_path)]) == 0

    assert calls == [config_path]
    output = capsys.readouterr().out
    assert output == "Beatport authorization saved.\n"
    assert "secret" not in output


def test_check_auth_beatport_reports_only_non_secret_status(monkeypatch, tmp_path: Path, capsys) -> None:
    """Token check reports the response status but never an access token."""

    config_path = tmp_path / "config.toml"
    config_path.write_text("[sources.beatport.auth]\naccess_token = 'secret-token'\n", encoding="utf-8")
    monkeypatch.setattr(cli, "check_beatport_auth", lambda *_args, **_kwargs: {"active": True, "scope": "catalog"})

    assert cli.main(["check-auth", "beatport", "--config", str(config_path)]) == 0

    output = capsys.readouterr().out
    assert output == "Beatport authorization is valid. scope=catalog\n"
    assert "secret-token" not in output
