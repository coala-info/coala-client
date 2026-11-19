"""Shared helpers for accessing coala-repo (GitHub). Supports optional token for private repo."""

import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

COALA_REPO = "https://github.com/coala-info/coala-repo"
COALA_REPO_BRANCH = "main"
COALA_REPO_DATA_PREFIX = "data"

# Optional: set COALA_REPO_TOKEN (or GITHUB_TOKEN) for private repo access
_TOKEN_ENV_VARS = ("COALA_REPO_TOKEN", "GITHUB_TOKEN")

# Parse owner/repo from COALA_REPO URL (e.g. https://github.com/coala-info/coala-repo)
_COALA_REPO_OWNER = "coala-info"
_COALA_REPO_NAME = "coala-repo"


def _get_token() -> str | None:
    """Return token for coala-repo if set (COALA_REPO_TOKEN or GITHUB_TOKEN)."""
    for name in _TOKEN_ENV_VARS:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


def _github_api_request(url: str, token: str | None) -> bytes:
    """GET a GitHub API URL; use token in header if provided."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    req = Request(url, headers=headers)
    with urlopen(req) as resp:
        return resp.read()


def download_github_folder_to(
    owner: str,
    repo: str,
    branch: str,
    folder_path: str,
    dest_dir: Path,
    *,
    token: str | None = None,
) -> None:
    """Download a single folder from a GitHub repo via Contents API into dest_dir (no full clone).

    folder_path: e.g. 'data/bwa' or 'data/bwa/skills'. Recurses into subdirs.
    """
    base = f"https://api.github.com/repos/{owner}/{repo}/contents"
    folder_path = folder_path.strip("/")
    if not folder_path:
        raise ValueError("folder_path must be non-empty")

    def fetch_dir(path: str) -> list:
        url = f"{base}/{path}?ref={branch}"
        raw = _github_api_request(url, token)
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, dict):
            if data.get("message") == "Not Found":
                raise FileNotFoundError(f"Folder '{path}' not found in {owner}/{repo} (ref {branch})")
            raise ValueError(data.get("message", str(data)))
        return data

    def recurse(path: str, local_dir: Path) -> None:
        items = fetch_dir(path)
        for item in items:
            name = item.get("name") or ""
            item_path = item.get("path") or f"{path}/{name}"
            item_type = item.get("type") or ""
            if item_type == "dir":
                recurse(item_path, local_dir / name)
            elif item_type == "file":
                download_url = item.get("download_url")
                if not download_url:
                    continue
                dest_file = local_dir / name
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                # download_url is a raw file URL; use token for private repo
                req = Request(download_url)
                if token:
                    req.add_header("Authorization", f"token {token}")
                with urlopen(req) as resp:
                    dest_file.write_bytes(resp.read())

    dest_dir.mkdir(parents=True, exist_ok=True)
    recurse(folder_path, dest_dir)


def download_coala_repo_folder_to(folder_path: str, dest_dir: Path) -> None:
    """Download a folder from coala-repo (e.g. 'data/bwa' or 'data/bwa/skills') into dest_dir."""
    token = _get_token()
    download_github_folder_to(
        _COALA_REPO_OWNER,
        _COALA_REPO_NAME,
        COALA_REPO_BRANCH,
        folder_path,
        dest_dir,
        token=token,
    )


def is_rate_limited(err: HTTPError) -> bool:
    """True when GitHub refused a request because the API rate limit is used up.

    GitHub answers 429, or 403 with "rate limit" in the body; other 403s (no access) are not.
    """
    if err.code == 429:
        return True
    if err.code != 403:
        return False
    try:
        body = err.read().decode("utf-8", "replace")
    except Exception:
        body = ""
    return "rate limit" in body.lower() or err.headers.get("X-RateLimit-Remaining") == "0"


def download_coala_repo_file_to(file_path: str, dest_file: Path) -> None:
    """Download one file of coala-repo from raw.githubusercontent.com (not the rate-limited API)."""
    url = (
        f"https://raw.githubusercontent.com/{_COALA_REPO_OWNER}/{_COALA_REPO_NAME}/"
        f"{COALA_REPO_BRANCH}/{file_path.strip('/')}"
    )
    req = Request(url, headers={"User-Agent": "coala-client"})
    token = _get_token()
    if token:
        req.add_header("Authorization", f"token {token}")
    try:
        with urlopen(req) as resp:
            body = resp.read()
    except HTTPError as e:
        if e.code == 404:
            raise FileNotFoundError(f"'{file_path}' not found in {COALA_REPO}") from e
        raise
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    dest_file.write_bytes(body)
