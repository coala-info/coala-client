"""Fetch and cache coala tools index; search tools."""

import json
from pathlib import Path
from urllib.request import Request, urlopen

# coala-mp tools index (private repo: use GITHUB_TOKEN or COALA_REPO_TOKEN)
TOOLS_INDEX_RAW_URL = "https://raw.githubusercontent.com/coala-info/coala-mp/master/web/public/tools-index.json"
TOOLS_INDEX_API_URL = "https://api.github.com/repos/coala-info/coala-mp/contents/web/public/tools-index.json?ref=master"
CACHE_DIR = Path("~/.config/coala/cache").expanduser()
CACHE_FILENAME = "tools-index.json"


def _cache_path() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / CACHE_FILENAME


def _fetch_index_with_token(token: str) -> str:
    """Fetch file content via GitHub Contents API (for private repo).

    Uses raw media type so we get the file body directly (works for large files and
    avoids base64 decode issues).
    """
    req = Request(
        TOOLS_INDEX_API_URL,
        headers={
            "Accept": "application/vnd.github.v3.raw",
            "Authorization": f"token {token}",
        },
    )
    with urlopen(req) as resp:
        body = resp.read()
    # 404 or API error may still return JSON with message
    if body.lstrip().startswith(b"{"):
        try:
            data = json.loads(body.decode("utf-8"))
            if isinstance(data, dict) and data.get("message"):
                raise FileNotFoundError(
                    f"{data.get('message')} ({TOOLS_INDEX_API_URL})"
                )
        except json.JSONDecodeError:
            pass
    return body.decode("utf-8")


def get_tools_index(*, force_refresh: bool = False) -> list[dict]:
    """Load tools index: use cache if present and not force_refresh, else fetch and cache.

    Uses GITHUB_TOKEN or COALA_REPO_TOKEN for private coala-mp repo.
    Returns a list of tool objects (structure defined by coala-mp tools-index.json).
    """
    from ._repo import _get_token

    cache_path = _cache_path()
    if not force_refresh and cache_path.is_file():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    token = _get_token()
    if token:
        data = _fetch_index_with_token(token)
    else:
        req = Request(TOOLS_INDEX_RAW_URL, headers={"User-Agent": "coala-client"})
        with urlopen(req) as resp:
            data = resp.read().decode("utf-8")

    raw = json.loads(data)
    if isinstance(raw, list):
        index = raw
    elif isinstance(raw, dict) and "tools" in raw:
        index = raw["tools"] if isinstance(raw["tools"], list) else []
    elif isinstance(raw, dict):
        index = [raw]
    else:
        index = []
    cache_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index


def _tool_name(t: dict) -> str:
    """Primary display name for a tool (for ordering)."""
    return (t.get("name") or t.get("id") or t.get("toolset") or "").strip().lower()


def _tool_text(t: dict) -> str:
    """All searchable string content (for matching), lowercased."""
    parts = []
    for k, v in t.items():
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, dict):
            parts.append(_tool_text(v))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(_tool_text(item))
    return " ".join(parts).lower()


def _search_rank(tool: dict, query: str) -> tuple[int, str]:
    """Return (priority, sort_key). Lower priority = better match. Exact name first."""
    name = _tool_name(tool)
    q = query.strip().lower()
    if name == q:
        return (0, name)
    if name.startswith(q):
        return (1, name)
    if q in name:
        return (2, name)
    return (3, name)  # match in description/other only


def _tool_category(t: dict) -> str:
    return (t.get("category") or "").strip()


def list_categories(index: list[dict]) -> list[str]:
    return sorted({c for t in index if isinstance(t, dict) for c in [_tool_category(t)] if c})


def search_tools(
    index: list[dict],
    query: str,
    *,
    category: str | None = None,
) -> list[dict]:
    """Return tools matching query (case-insensitive), ordered: exact name first, then name start, then name contains, then description."""
    if category:
        cat = category.strip().lower()
        index = [
            t for t in index
            if isinstance(t, dict) and _tool_category(t).lower() == cat
        ]

    q = query.strip().lower()
    if not q:
        return list(index)

    matched = [t for t in index if isinstance(t, dict) and q in _tool_text(t)]
    return sorted(matched, key=lambda t: _search_rank(t, q))
