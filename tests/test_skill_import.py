"""Tests for fetching a toolset's skills from coala-repo."""

import io
from urllib.error import HTTPError

import pytest

from coala_client import skill_import


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(url: str, code: int, body: bytes) -> HTTPError:
    return HTTPError(url, code, "error", {}, io.BytesIO(body))


def _fake_urlopen(api_error: HTTPError | None, raw: dict[str, bytes], seen: list[str]):
    def urlopen(req, *args, **kwargs):
        url = req if isinstance(req, str) else req.full_url
        seen.append(url)
        if "api.github.com" in url:
            if api_error is not None:
                raise api_error
            raise AssertionError("API listing should have failed in this test")
        if url in raw:
            return _Resp(raw[url])
        raise _http_error(url, 404, b"404: Not Found")

    return urlopen


RAW = (
    "https://raw.githubusercontent.com/coala-info/coala-repo/main/data/neurocombat/skills/SKILL.md"
)


@pytest.mark.parametrize(
    ("code", "body"),
    [
        (403, b'{"message": "API rate limit exceeded for 1.2.3.4."}'),
        (429, b"Too Many Requests"),
    ],
)
def test_rate_limited_listing_falls_back_to_raw_skill_md(tmp_path, monkeypatch, code, body):
    seen: list[str] = []
    err = _http_error("https://api.github.com/repos/x", code, body)
    fake = _fake_urlopen(err, {RAW: b"# neurocombat skill\n"}, seen)
    monkeypatch.setattr("coala_client._repo.urlopen", fake)
    monkeypatch.setattr("coala_client.skill_import.urlopen", fake)
    monkeypatch.delenv("COALA_REPO_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    dest = skill_import.import_skills_from_coala_repo("neurocombat", skills_dir=tmp_path)

    assert (dest / "SKILL.md").read_text() == "# neurocombat skill\n"
    assert seen[-1] == RAW


def test_rate_limited_listing_and_missing_raw_file_is_not_found(tmp_path, monkeypatch):
    seen: list[str] = []
    err = _http_error("https://api.github.com/repos/x", 403, b"API rate limit exceeded")
    fake = _fake_urlopen(err, {}, seen)
    monkeypatch.setattr("coala_client._repo.urlopen", fake)
    monkeypatch.setattr("coala_client.skill_import.urlopen", fake)

    with pytest.raises(FileNotFoundError):
        skill_import.import_skills_from_coala_repo("neurocombat", skills_dir=tmp_path)


def test_other_forbidden_errors_are_not_swallowed(tmp_path, monkeypatch):
    seen: list[str] = []
    err = _http_error("https://api.github.com/repos/x", 403, b'{"message": "Resource not accessible"}')
    fake = _fake_urlopen(err, {RAW: b"x"}, seen)
    monkeypatch.setattr("coala_client._repo.urlopen", fake)
    monkeypatch.setattr("coala_client.skill_import.urlopen", fake)

    with pytest.raises(HTTPError):
        skill_import.import_skills_from_coala_repo("neurocombat", skills_dir=tmp_path)
    assert not any("raw.githubusercontent.com" in u for u in seen)
