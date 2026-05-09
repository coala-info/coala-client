"""Import CWL toolsets and register them as MCP servers."""

import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

import yaml

from ._repo import (
    COALA_REPO,
    COALA_REPO_BRANCH,
    COALA_REPO_DATA_PREFIX,
    download_coala_repo_folder_to,
)


def _is_url(source: str | Path) -> bool:
    if not isinstance(source, str):
        return False
    return source.startswith("http://") or source.startswith("https://")


def _filename_from_url(url: str) -> str:
    path = urlparse(url).path or ""
    name = path.rsplit("/", 1)[-1] if path else ""
    return name or "download"


def _resolve_sources(sources: list[str | Path]) -> tuple[list[Path], tempfile.TemporaryDirectory | None]:
    """Resolve sources to local paths; download URLs to a temp dir. Returns (paths, temp_dir or None)."""
    resolved: list[Path] = []
    temp_dir: tempfile.TemporaryDirectory | None = None
    for src in sources:
        if _is_url(src):
            url = str(src)
            name = _filename_from_url(url)
            if not name.lower().endswith((".cwl", ".zip")):
                name += ".cwl"  # default for URLs with no extension
            if temp_dir is None:
                temp_dir = tempfile.TemporaryDirectory()
            dest = Path(temp_dir.name) / name
            with urlopen(url) as resp:
                dest.write_bytes(resp.read())
            resolved.append(dest)
        else:
            resolved.append(Path(src).resolve())
    return resolved, temp_dir


def _mcps_dir_from_config(mcp_config_file: str) -> Path:
    """Return MCP root dir (parent of mcp_servers.json); create if needed."""
    config_path = Path(mcp_config_file).expanduser()
    mcps_dir = config_path.parent
    mcps_dir.mkdir(parents=True, exist_ok=True)
    return mcps_dir


# WorkflowHub-style report line: **Main workflow (WorkflowHub):** `path/to/workflow.cwl` (Main Workflow)
_MAIN_WORKFLOW_REPORT_RE = re.compile(
    r"\*\*Main workflow \(WorkflowHub\):\*\*\s*`([^`]+)`",
    re.MULTILINE,
)


def _main_workflow_cwl_from_report(toolset_dir: Path) -> Path:
    """Resolve the single main workflow .cwl path declared in report.md (cwl-* toolsets)."""
    report_md = toolset_dir / "report.md"
    if not report_md.is_file():
        raise ValueError(
            f"cwl-* toolsets require report.md in {toolset_dir} to locate the main workflow CWL."
        )
    text = report_md.read_text(encoding="utf-8", errors="replace")
    m = _MAIN_WORKFLOW_REPORT_RE.search(text)
    if not m:
        raise ValueError(
            f"Could not find **Main workflow (WorkflowHub):** `...` entry in {report_md}"
        )
    rel = m.group(1).strip()
    base = toolset_dir.resolve()
    candidate = (toolset_dir / rel).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as e:
        raise ValueError(
            f"Main workflow path must stay inside the toolset directory; got {rel!r}"
        ) from e
    if not candidate.is_file():
        raise ValueError(f"Main workflow CWL not found: {candidate}")
    if candidate.suffix.lower() != ".cwl":
        raise ValueError(f"Main workflow path must be a .cwl file: {candidate}")
    return candidate


def _collect_cwl_paths_after_import(toolset_dir: Path, toolset: str) -> list[Path]:
    """List .cwl files to register. cwl-* toolsets: only the main workflow from report.md."""
    if toolset.startswith("cwl-"):
        return [_main_workflow_cwl_from_report(toolset_dir)]
    _strip_non_cwl_artifacts(toolset_dir)
    cwl_paths = sorted(
        p for p in toolset_dir.rglob("*")
        if p.is_file() and p.suffix.lower() == ".cwl"
    )
    if not cwl_paths:
        raise ValueError(
            f"No .cwl files under {toolset_dir}."
        )
    return cwl_paths


def _strip_non_cwl_artifacts(toolset_dir: Path) -> None:
    """Remove report.md and skills/ from toolset dir so only CWL and run_mcp.py remain."""
    report_md = toolset_dir / "report.md"
    if report_md.is_file():
        report_md.unlink()
    skills_dir = toolset_dir / "skills"
    if skills_dir.is_dir():
        shutil.rmtree(skills_dir)


def _download_coala_repo_folder_to(toolset: str, toolset_dir: Path) -> list[Path]:
    """Download data/<toolset> from coala-repo GitHub (folder only) into toolset_dir. Returns .cwl paths."""
    folder_path = f"{COALA_REPO_DATA_PREFIX}/{toolset}"
    try:
        download_coala_repo_folder_to(folder_path, toolset_dir)
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Folder '{folder_path}' not found in {COALA_REPO}. "
            f"Check the toolset name (e.g. 'bwa') at {COALA_REPO}/tree/{COALA_REPO_BRANCH}/{COALA_REPO_DATA_PREFIX}."
        ) from e
    cwl_paths = _collect_cwl_paths_after_import(toolset_dir, toolset)
    _strip_non_cwl_artifacts(toolset_dir)
    return cwl_paths


def _copy_cwl_sources(sources: list[Path], dest_dir: Path, toolset: str) -> list[Path]:
    """Copy CWL files into dest_dir. Returns paths to copied .cwl files in dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in sources:
        src = src.resolve()
        if not src.exists():
            raise FileNotFoundError(f"CWL file or archive not found: {src}")
        if src.suffix.lower() == ".zip":
            with zipfile.ZipFile(src) as zf:
                zf.extractall(dest_dir)
        else:
            if src.suffix.lower() != ".cwl":
                raise ValueError(f"Not a CWL file: {src}")
            shutil.copy2(src, dest_dir / src.name)
    cwl_paths = _collect_cwl_paths_after_import(dest_dir, toolset)
    _strip_non_cwl_artifacts(dest_dir)
    return cwl_paths


def _cwl_declares_stdout(cwl_path: Path) -> bool:
    """True if the CWL defines a stdout redirect (root or ``$graph`` entry)."""
    try:
        raw = cwl_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    try:
        for doc in yaml.safe_load_all(raw):
            if doc is None or not isinstance(doc, dict):
                continue
            if doc.get("stdout") is not None:
                return True
            graph = doc.get("$graph")
            if isinstance(graph, list):
                for node in graph:
                    if isinstance(node, dict) and node.get("stdout") is not None:
                        return True
    except yaml.YAMLError:
        return False
    return False


def _generate_mcp_py(
    toolset_dir: Path,
    cwl_paths: list[Path],
    *,
    container_runner: str | None = None,
) -> str:
    """Generate run_mcp.py script content that loads all CWL tools and serves via stdio."""
    # Use paths relative to toolset_dir so nested dirs (e.g. from zip) work
    add_lines = []
    for p in sorted(cwl_paths):
        rel = p.relative_to(toolset_dir).as_posix()
        path_arg = f"os.path.join(base_dir, {repr(rel)})"
        if _cwl_declares_stdout(p):
            add_lines.append(f"mcp.add_tool({path_arg}, read_outs=True)")
        else:
            add_lines.append(f"mcp.add_tool({path_arg})")
    add_lines = "\n".join(add_lines)
    if container_runner:
        ctor = f"mcp_api(container_runner={container_runner!r})"
    else:
        ctor = "mcp_api()"
    return f'''from coala.mcp_api import mcp_api
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
mcp = {ctor}
{add_lines}
mcp.serve()
'''


def _load_mcp_servers_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {"mcpServers": {}}
    with open(config_path) as f:
        return json.load(f)


def _save_mcp_servers_config(config_path: Path, data: dict[str, Any]) -> None:
    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)


def import_cwl_toolset(
    toolset: str,
    sources: list[str | Path],
    *,
    mcp_config_file: str = "~/.config/coala/mcps/mcp_servers.json",
    container_runner: str | None = None,
) -> dict[str, Any]:
    """Import CWL files or a zip of CWL files into a named toolset and register as MCP server.

    Sources can be local paths or http(s) URLs to .cwl files or a .zip archive.

    If ``toolset`` starts with ``cwl-``, the archive or directory must include ``report.md``
    with a WorkflowHub ``Main workflow (WorkflowHub)`` bullet; only that main ``.cwl`` file
    is registered in ``run_mcp.py``.

    - Copies or unzips sources into ~/.config/coala/<toolset>/
    - Creates run_mcp.py there (uses coala.mcp_api)
    - Adds or updates the toolset entry in mcp_servers.json
    - Returns the MCP server entry that was added (for display).

    Raises:
        FileNotFoundError: If any local source path does not exist.
        ValueError: If a non-zip source is not a .cwl file.
    """
    mcps_dir = _mcps_dir_from_config(mcp_config_file)
    toolset_dir = mcps_dir / toolset

    resolved, temp_dir = _resolve_sources(sources)
    try:
        # Single zip: treat as archive; otherwise treat as list of CWL files
        if len(resolved) == 1 and resolved[0].suffix.lower() == ".zip":
            # Remove existing content so unzip replaces cleanly
            if toolset_dir.exists():
                shutil.rmtree(toolset_dir)
            cwl_paths = _copy_cwl_sources(resolved, toolset_dir, toolset)
        else:
            # Ensure only .cwl files; replace existing .cwl in toolset dir
            for s in resolved:
                if s.suffix.lower() != ".cwl":
                    raise ValueError(f"Expected .cwl file or single .zip archive: {s}")
            if toolset_dir.exists():
                for f in toolset_dir.glob("*.cwl"):
                    f.unlink()
            cwl_paths = _copy_cwl_sources(resolved, toolset_dir, toolset)
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    if not cwl_paths:
        raise ValueError(
            "No .cwl files found. Provide .cwl files or a .zip containing .cwl files."
        )

    return _register_toolset(
        toolset_dir,
        cwl_paths,
        toolset,
        mcp_config_file,
        container_runner=container_runner,
    )


def _register_toolset(
    toolset_dir: Path,
    cwl_paths: list[Path],
    toolset: str,
    mcp_config_file: str,
    *,
    container_runner: str | None = None,
) -> dict[str, Any]:
    """Write run_mcp.py and add toolset to mcp_servers.json. Returns the server entry."""
    # Use run_mcp.py to avoid shadowing the 'mcp' package (from mcp.server.fastmcp)
    mcp_py_path = toolset_dir / "run_mcp.py"
    mcp_py_path.write_text(
        _generate_mcp_py(toolset_dir, cwl_paths, container_runner=container_runner)
    )

    config_path = Path(mcp_config_file).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_mcp_servers_config(config_path)
    servers = data.setdefault("mcpServers", {})

    mcp_py_abs = str(mcp_py_path.resolve())
    server_entry = {
        "command": "python",
        "args": [mcp_py_abs],
        "env": {},
    }
    servers[toolset] = server_entry
    _save_mcp_servers_config(config_path, data)
    return server_entry


def import_cwl_toolset_from_coala_repo(
    toolset: str,
    *,
    mcp_config_file: str = "~/.config/coala/mcps/mcp_servers.json",
    container_runner: str | None = None,
) -> dict[str, Any]:
    """Import CWL files from coala-repo GitHub (data/<toolset>) and register as MCP server.

    Downloads from https://github.com/coala-info/coala-repo tree main, folder data/<toolset>.

    Toolsets whose name starts with ``cwl-`` are WorkflowHub workflow bundles: only the
    main workflow path from ``report.md`` (the ``Main workflow (WorkflowHub)`` bullet with a
    backtick-enclosed path) is registered as an MCP tool; other ``.cwl`` files in the folder
    are not added.
    """
    mcps_dir = _mcps_dir_from_config(mcp_config_file)
    toolset_dir = mcps_dir / toolset
    if toolset_dir.exists():
        shutil.rmtree(toolset_dir)
    cwl_paths = _download_coala_repo_folder_to(toolset, toolset_dir)
    return _register_toolset(
        toolset_dir,
        cwl_paths,
        toolset,
        mcp_config_file,
        container_runner=container_runner,
    )
