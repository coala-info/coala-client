"""Import skills from URL or zip into ~/.config/coala/skills."""

import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import urlopen

from ._repo import (
    COALA_REPO,
    COALA_REPO_BRANCH,
    COALA_REPO_DATA_PREFIX,
    download_coala_repo_file_to,
    download_coala_repo_folder_to,
    download_github_folder_to,
    is_rate_limited,
    _get_token as _repo_token,
)

SKILLS_DIR = Path("~/.config/coala/skills").expanduser()
GLOBAL_SKILLS_DIR = Path("~/.agents/skills").expanduser()


def get_local_skills_dir() -> Path:
    """Return the project-local skills dir (cwd/.agents/skills)."""
    return Path.cwd() / ".agents" / "skills"


def list_skills() -> list[str]:
    """Return names of installed skills (subfolders under config, local .agents, and ~/.agents)."""
    names: set[str] = set()
    for base in (SKILLS_DIR, get_local_skills_dir(), GLOBAL_SKILLS_DIR):
        if base.exists():
            names.update(
                p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")
            )
    return sorted(names)


def get_skill_content(name: str) -> str | None:
    """Load skill content from skills dirs (<name>/). Reads SKILL.md if present.

    Looks in local .agents/skills, then ~/.config/coala/skills, then ~/.agents/skills.
    Returns the skill text, or None if the skill folder or SKILL.md is missing.
    """
    for base in (get_local_skills_dir(), SKILLS_DIR, GLOBAL_SKILLS_DIR):
        skill_dir = base / name
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if skill_md.is_file():
            return skill_md.read_text(encoding="utf-8", errors="replace")
        # Fallback: first .md file in the folder
        for p in sorted(skill_dir.iterdir()):
            if p.suffix.lower() == ".md":
                return p.read_text(encoding="utf-8", errors="replace")
        return None
    return None


# GitHub tree URL: https://github.com/owner/repo/tree/branch/path
_GITHUB_TREE_RE = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+)/tree/([^/]+)(?:/(.*))?$",
    re.IGNORECASE,
)


def _folder_name_for_source(source: str | Path) -> str:
    """Return a subfolder name under skills/ for this source (e.g. bedtools)."""
    src_str = str(source).strip()
    if src_str.startswith("http://") or src_str.startswith("https://"):
        parsed = urlparse(src_str)
        path = (parsed.path or "").strip("/")
        segments = [s for s in path.split("/") if s]
        if len(segments) >= 2:
            # e.g. files/bedtools/bedtools-skills.zip -> bedtools
            return segments[-2]
        if segments:
            # e.g. bar.zip -> bar
            name = segments[-1]
            return Path(name).stem if "." in name else name
        return "skills"
    path = Path(source).resolve()
    if path.is_dir():
        return path.name
    return path.stem


def _is_url(source: str | Path) -> bool:
    if not isinstance(source, str):
        return False
    return source.startswith("http://") or source.startswith("https://")


def _parse_github_tree_url(url: str) -> tuple[str, str, str, str] | None:
    """Return (owner, repo, branch, path) or None if not a GitHub tree URL."""
    m = _GITHUB_TREE_RE.match(url.strip())
    if not m:
        return None
    owner, repo, branch, path = m.groups()
    path = (path or "").strip("/")
    return (owner, repo, branch, path)


def _download_github_folder(
    owner: str, repo: str, branch: str, folder: str, dest_dir: Path
) -> None:
    """Download only the specified folder via GitHub Contents API (no full repo)."""
    if not folder:
        raise ValueError("Folder path is required for GitHub tree URL")
    try:
        download_github_folder_to(
            owner, repo, branch, folder, dest_dir, token=_repo_token()
        )
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Folder '{folder}' not found in {owner}/{repo} (branch {branch})"
        ) from e


def _extract_zip_to_dir(zip_path: Path, dest_dir: Path) -> None:
    """Extract zip into dest_dir (strip one top-level dir if single)."""
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    if not names:
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    top_dirs = {n.split("/")[0].split("\\")[0] for n in names if n}
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    if len(top_dirs) == 1 and names:
        single_top = list(top_dirs)[0]
        top_path = dest_dir / single_top
        if top_path.is_dir():
            for p in top_path.iterdir():
                shutil.move(str(p), str(dest_dir / p.name))
            top_path.rmdir()


def _download_coala_repo_skills_to(toolset: str, dest_dir: Path) -> None:
    """Download data/<toolset>/skills from coala-repo GitHub (folder only) into dest_dir."""
    folder_in_repo = f"{COALA_REPO_DATA_PREFIX}/{toolset}/skills"
    try:
        try:
            download_coala_repo_folder_to(folder_in_repo, dest_dir)
        except HTTPError as e:
            if not is_rate_limited(e):
                raise
            # The folder listing uses the GitHub API (60 calls an hour per address without a
            # token). The skill text itself is a plain file, so fetch SKILL.md directly.
            download_coala_repo_file_to(f"{folder_in_repo}/SKILL.md", dest_dir / "SKILL.md")
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Folder '{folder_in_repo}' not found in {COALA_REPO}. "
            f"Check the toolset name (e.g. 'bwa') at {COALA_REPO}/tree/{COALA_REPO_BRANCH}/{COALA_REPO_DATA_PREFIX}."
        ) from e


def import_skills_from_coala_repo(toolset: str, skills_dir: Path | None = None) -> Path:
    """Import skills from coala-repo GitHub (data/<toolset>/skills) into skills_dir/<toolset>."""
    base = skills_dir if skills_dir is not None else SKILLS_DIR
    base.mkdir(parents=True, exist_ok=True)
    dest_dir = base / toolset
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    _download_coala_repo_skills_to(toolset, dest_dir)
    return dest_dir


def import_skills(sources: list[str | Path], skills_dir: Path | None = None) -> Path:
    """Import skills from GitHub tree URLs or zip URLs/paths into the skills directory.

    Each source is placed in its own subfolder (e.g. skills/bedtools/, skills/agent-skills/).
    Default directory is ~/.config/coala/skills; pass skills_dir for e.g. ~/.agent/skills.

    - GitHub tree URL: downloads only that folder via GitHub API (no full repo), into skills/<repo>/.
    - Zip URL or local zip: extracts into skills/<folder_name>/ (folder from URL path or zip stem).
    - Local directory: copies into skills/<dir_name>/.

    Returns the skills directory path.
    """
    base = skills_dir if skills_dir is not None else SKILLS_DIR
    base.mkdir(parents=True, exist_ok=True)

    for src in sources:
        src_str = str(src).strip()
        if _is_url(src_str):
            parsed = _parse_github_tree_url(src_str)
            if parsed:
                owner, repo, branch, folder = parsed
                dest_dir = base / repo
                _download_github_folder(owner, repo, branch, folder, dest_dir)
            else:
                folder_name = _folder_name_for_source(src_str)
                dest_dir = base / folder_name
                with urlopen(src_str) as resp:
                    data = resp.read()
                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
                    f.write(data)
                    f.flush()
                    try:
                        _extract_zip_to_dir(Path(f.name), dest_dir)
                    finally:
                        Path(f.name).unlink(missing_ok=True)
        else:
            path = Path(src).resolve()
            if not path.exists():
                raise FileNotFoundError(f"Source not found: {path}")
            folder_name = _folder_name_for_source(path)
            dest_dir = base / folder_name
            dest_dir.mkdir(parents=True, exist_ok=True)
            if path.suffix.lower() == ".zip":
                _extract_zip_to_dir(path, dest_dir)
            elif path.is_dir():
                for p in path.iterdir():
                    shutil.copy2(p, dest_dir / p.name)
            else:
                raise ValueError(f"Expected a zip file or directory: {path}")

    return base
