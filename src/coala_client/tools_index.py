"""Fetch and cache coala tools index; search tools."""

import json
import math
import re
from collections import Counter
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


# A command name shared by more than this many packages (``merge``, ``index``, ``filter``,
# ``view``) names an action, not a tool: its matches rank after description matches.
GENERIC_COMMAND_PACKAGES = 10


def _tool_commands(t: dict) -> dict[str, str]:
    """``{lowercase: as written}`` for the subcommands the index lists for a package."""
    cmds = t.get("commands")
    if not isinstance(cmds, list):
        return {}
    return {c.strip().lower(): c.strip() for c in cmds if isinstance(c, str) and c.strip()}


def matched_command(t: dict, query: str) -> str | None:
    """The package's subcommand that is exactly ``query`` (case-insensitive), as written."""
    return _tool_commands(t).get(query.strip().lower())


def _tool_text(t: dict) -> str:
    """All searchable string content (for matching), lowercased.

    Subcommand names are left out: they match whole, never as substrings, so ``count`` does
    not find every package with a ``featureCounts`` command.
    """
    parts = []
    for k, v in t.items():
        if k == "commands":
            continue
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


def _search_rank(
    tool: dict, query: str, *, generic_command: bool = False
) -> tuple[int, int, str]:
    """Return (priority, position, name). Lower sorts first.

    Exact package name, then a package with a subcommand of exactly that name
    (``featurecounts`` -> ``subread``), then name prefix, name substring, description (the
    earlier the query appears in it, the better), any other field, and last a subcommand
    name shared by many packages.
    """
    name = _tool_name(tool)
    q = query.strip().lower()
    if name == q:
        return (0, 0, name)
    if not generic_command and q in _tool_commands(tool):
        return (1, 0, name)
    if name.startswith(q):
        return (2, 0, name)
    if q in name:
        return (3, 0, name)
    at = (tool.get("description") or "").lower().find(q)
    if at >= 0:
        return (4, at, name)
    if q in _tool_text(tool):
        return (5, 0, name)  # match in another field only
    return (6, 0, name)  # only a common subcommand name


def _tool_category(t: dict) -> str:
    return (t.get("category") or "").strip()


def _tool_category_group(t: dict) -> str:
    return (t.get("category_group") or "").strip()


# Short labels used by older versions of the index, mapped to the current
# category (or category group) names. Keys are lowercase.
CATEGORY_ALIASES = {
    "cli": "Command-line tool",
    "python": "Python library",
    "r": "R package",
    "bioconductor": "Bioconductor package",
    "perl": "Perl module",
    "library": "Libraries",
    "galaxy": "Galaxy workflow",
    "nextflow": "Nextflow workflow",
    "cwl": "CWL workflow",
}


def list_categories(index: list[dict]) -> list[str]:
    return sorted({c for t in index if isinstance(t, dict) for c in [_tool_category(t)] if c})


def list_category_groups(index: list[dict]) -> list[str]:
    return sorted({g for t in index if isinstance(t, dict) for g in [_tool_category_group(t)] if g})


def resolve_category(index: list[dict], category: str) -> set[str]:
    """Return the lowercase category names that CATEGORY selects in INDEX.

    CATEGORY may be a category name ("Python library"), a group name
    ("Libraries"), or an old short label ("python", "library"). Matching is
    case-insensitive. Returns an empty set if nothing matches.
    """
    key = category.strip().lower()
    names = {c.lower() for c in list_categories(index)}
    if key in names:
        return {key}
    by_group = {
        _tool_category(t).lower()
        for t in index
        if isinstance(t, dict) and _tool_category_group(t).lower() == key and _tool_category(t)
    }
    if by_group:
        return by_group
    if key in CATEGORY_ALIASES:
        return resolve_category(index, CATEGORY_ALIASES[key])
    return set()


_WORD = re.compile(r"[a-z0-9]+")
# A word in more than this share of names and descriptions ("and", "data", "analysis") still
# counts toward a tool's score but does not by itself make a tool a match.
_COMMON_WORD_SHARE = 0.05
_BM25_K1 = 1.2
_BM25_B = 0.75


def _words(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def _summary_words(t: dict) -> list[str]:
    """The words of a tool's name and description, the text its one-line summary shows."""
    name = re.sub(r"[-_.]", " ", _tool_name(t))
    return _words(f"{name} {t.get('description') or ''}")


class _WordStats:
    """Word counts over every tool's name and description, for BM25 scoring."""

    def __init__(self, index: list[dict]) -> None:
        self.docs = {id(t): Counter(_summary_words(t)) for t in index if isinstance(t, dict)}
        self.lengths = {k: sum(c.values()) for k, c in self.docs.items()}
        self.n = max(1, len(self.docs))
        self.avg = max(1.0, sum(self.lengths.values()) / self.n)
        self.df: Counter = Counter()
        for c in self.docs.values():
            self.df.update(c.keys())

    def idf(self, w: str) -> float:
        df = self.df.get(w, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def common(self, w: str) -> bool:
        return self.df.get(w, 0) > _COMMON_WORD_SHARE * self.n

    def score(self, t: dict, words: list[str]) -> float:
        tf = self.docs.get(id(t))
        if not tf:
            return 0.0
        norm = _BM25_K1 * (1 - _BM25_B + _BM25_B * self.lengths[id(t)] / self.avg)
        return sum(self.idf(w) * f * (_BM25_K1 + 1) / (f + norm)
                   for w in words if (f := tf.get(w, 0)))


_STATS: tuple[int, int, _WordStats] | None = None


def _word_stats(index: list[dict]) -> _WordStats:
    global _STATS
    if _STATS is None or _STATS[0] != id(index) or _STATS[1] != len(index):
        _STATS = (id(index), len(index), _WordStats(index))
    return _STATS[2]


def search_tools(
    index: list[dict],
    query: str,
    *,
    category: str | None = None,
) -> list[dict]:
    """Return tools matching query (case-insensitive).

    Ordered: exact name, exact subcommand name, name start, name contains, then the rest by
    how well the name and description fit, then a match in another field only, then a
    subcommand name shared by more than ``GENERIC_COMMAND_PACKAGES`` packages.

    A one-word query matches as a substring and ranks description matches by how early the
    word appears. A query of several words also matches a tool whose name or description holds
    any of its uncommon words, and ranks those by BM25 over names and descriptions, so
    ``ambient RNA removal`` finds a tool described as removing "ambient RNA" and a method
    phrase finds the tool whose summary shares most of its rare words.
    """
    q = query.strip().lower()
    full_index = index
    shared = sum(1 for t in index if isinstance(t, dict) and q and q in _tool_commands(t))
    generic_command = shared > GENERIC_COMMAND_PACKAGES
    if category:
        cats = resolve_category(index, category)
        index = [
            t for t in index
            if isinstance(t, dict) and _tool_category(t).lower() in cats
        ]

    if not q:
        return list(index)

    words = list(dict.fromkeys(_words(q)))
    if len(words) < 2:
        matched = [
            t for t in index
            if isinstance(t, dict) and (q in _tool_text(t) or q in _tool_commands(t))
        ]
        return sorted(matched, key=lambda t: _search_rank(t, q, generic_command=generic_command))

    stats = _word_stats(full_index)
    rare = {w for w in words if not stats.common(w)}
    ranked: list[tuple[tuple, dict]] = []
    for t in index:
        if not isinstance(t, dict):
            continue
        phrase = q in _tool_text(t) or q in _tool_commands(t)
        if not phrase and not rare & set(_summary_words(t)):
            continue
        tier, at, name = _search_rank(t, q, generic_command=generic_command)
        if tier <= 3:
            ranked.append(((tier, 0.0, at, name), t))
            continue
        fit = stats.score(t, words)
        if fit > 0:
            ranked.append(((4, -fit, at, name), t))
        else:
            ranked.append(((tier + 1, 0.0, at, name), t))
    ranked.sort(key=lambda x: x[0])
    return [t for _, t in ranked]
