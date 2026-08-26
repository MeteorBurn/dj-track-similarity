from __future__ import annotations


from metadata_enrichment.http import post_form_json


class Response:
    def __init__(self) -> None:
        self.status = 200

    def read(self) -> bytes:
        return b'{"access_token":"token"}'

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_post_form_json_uses_urlencoded_post_body(monkeypatch) -> None:
    """OAuth token requests must send fields as a form, not URL query data."""

    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        captured["method"] = request.get_method()
        captured["body"] = request.data
        captured["content_type"] = request.get_header("Content-type")
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("metadata_enrichment.http.urlopen", fake_urlopen)

    response = post_form_json(
        "https://api.beatport.com/v4/auth/o/token/",
        headers={"Authorization": "Bearer current-token"},
        fields={"client_id": "id", "grant_type": "refresh_token", "refresh_token": "refresh"},
    )

    assert response == {"access_token": "token"}
    assert captured == {
        "method": "POST",
        "body": b"client_id=id&grant_type=refresh_token&refresh_token=refresh",
        "content_type": "application/x-www-form-urlencoded",
        "timeout": 20,
    }
