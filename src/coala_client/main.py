"""Main entry point for Coala Client CLI."""

import asyncio
import json
from pathlib import Path

import click

from .cli import run_chat, run_single_prompt
from .config import create_default_mcp_config, load_config
from .mcp_manager import MCPManager
from .mcp_import import import_cwl_toolset, import_cwl_toolset_from_coala_repo
from .skill_import import (
    GLOBAL_SKILLS_DIR,
    get_local_skills_dir,
    import_skills,
    import_skills_from_coala_repo,
)
from .tools_index import get_tools_index, search_tools


async def _mcp_list_servers() -> None:
    """List MCP server names from config."""
    cfg = load_config()
    servers = cfg.get_mcp_servers()
    if not servers:
        click.echo("No MCP servers configured. Add one with: coala mcp <toolset> or coala mcp <toolset> <sources>")
        return
    for name in sorted(servers):
        click.echo(name)


async def _mcp_list_tools(server_name: str) -> None:
    """Connect to one server and print tool schemas."""
    cfg = load_config()
    servers = cfg.get_mcp_servers()
    if server_name not in servers:
        click.echo(f"Server not found: {server_name}", err=True)
        click.echo("Available: " + ", ".join(sorted(servers)) if servers else "none", err=True)
        raise SystemExit(1)
    async with MCPManager(cfg) as manager:
        await manager.connect_server(server_name, servers[server_name])
        conn = manager.connections.get(server_name)
        if not conn or not conn.tools:
            click.echo(f"No tools from server '{server_name}'")
            return
        for tool in conn.tools:
            schema = {
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": tool.inputSchema or {},
            }
            click.echo(json.dumps(schema, indent=2))
            click.echo("---")


async def _mcp_call_tool(server_dot_tool: str, args_json: str) -> None:
    """Connect to server and call tool with given args."""
    if "." not in server_dot_tool:
        click.echo("Expected server.tool (e.g. gene-variant.ncbi_datasets_gene)", err=True)
        raise SystemExit(1)
    server_name, tool_name = server_dot_tool.split(".", 1)
    try:
        args = json.loads(args_json)
    except json.JSONDecodeError as e:
        click.echo(f"Invalid --args JSON: {e}", err=True)
        raise SystemExit(1) from e
    cfg = load_config()
    servers = cfg.get_mcp_servers()
    if server_name not in servers:
        click.echo(f"Server not found: {server_name}", err=True)
        raise SystemExit(1)
    async with MCPManager(cfg) as manager:
        await manager.connect_server(server_name, servers[server_name])
        result = await manager.call_tool(tool_name, args)
    click.echo(result)


class _SourceType(click.ParamType):
    """Accept a local path or http(s) URL; only validate path existence for local paths."""

    name = "source"

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context) -> str:
        s = str(value).strip()
        if s.startswith("http://") or s.startswith("https://"):
            return s
        # Local path: validate existence
        path = Path(s)
        if not path.exists():
            self.fail(f"Path '{s}' does not exist.", param, ctx)
        return s


@click.group(invoke_without_command=True)
@click.option(
    "-p", "--provider",
    type=click.Choice(["openai", "gemini", "ollama", "custom"]),
    help="LLM provider to use",
)
@click.option(
    "-m", "--model",
    help="Model name to use (overrides config)",
)
@click.option(
    "--no-mcp",
    is_flag=True,
    help="Disable MCP server connections",
)
@click.option(
    "--sandbox",
    is_flag=True,
    help="Enable run_command tool so the LLM can run basic shell commands",
)
@click.option(
    "-c", "--command",
    "prompt",
    help="Run a single prompt and exit",
)
@click.pass_context
def cli(
    ctx: click.Context,
    provider: str | None,
    model: str | None,
    no_mcp: bool,
    sandbox: bool,
    prompt: str | None,
) -> None:
    """Coala Client - A simple CLI for LLM with MCP server support.

    Supports OpenAI-compatible APIs including OpenAI, Gemini, and Ollama.
    """
    if ctx.invoked_subcommand is not None:
        return

    if prompt:
        asyncio.run(run_single_prompt(prompt, provider, model, no_mcp, sandbox))
    else:
        asyncio.run(run_chat(provider, model, no_mcp, sandbox))


@cli.command()
def init() -> None:
    """Initialize configuration files."""
    create_default_mcp_config()
    click.echo("Created default configuration files:")
    click.echo("  - ~/.config/coala/mcps/mcp_servers.json")
    click.echo("  - ~/.config/coala/env")
    click.echo("\nTo get started:")
    click.echo("  1. Set your API key: export OPENAI_API_KEY=your-key")
    click.echo("  2. Edit MCP servers: ~/.config/coala/mcps/mcp_servers.json")
    click.echo("  3. Add environment variables: ~/.config/coala/env")
    click.echo("  4. Run: coala")


@cli.command()
@click.option(
    "-p", "--provider",
    type=click.Choice(["openai", "gemini", "ollama", "custom"]),
    help="LLM provider to use",
)
@click.option(
    "-m", "--model",
    help="Model name to use",
)
@click.option(
    "--no-mcp",
    is_flag=True,
    help="Disable MCP server connections",
)
@click.option(
    "--sandbox",
    is_flag=True,
    help="Enable run_command tool so the LLM can run basic shell commands",
)
def chat(provider: str | None, model: str | None, no_mcp: bool, sandbox: bool) -> None:
    """Start an interactive chat session."""
    asyncio.run(run_chat(provider, model, no_mcp, sandbox))


@cli.command()
@click.argument("prompt")
@click.option(
    "-p", "--provider",
    type=click.Choice(["openai", "gemini", "ollama", "custom"]),
    help="LLM provider to use",
)
@click.option(
    "-m", "--model",
    help="Model name to use",
)
@click.option(
    "--no-mcp",
    is_flag=True,
    help="Disable MCP server connections",
)
@click.option(
    "--sandbox",
    is_flag=True,
    help="Enable run_command tool so the LLM can run basic shell commands",
)
def ask(prompt: str, provider: str | None, model: str | None, no_mcp: bool, sandbox: bool) -> None:
    """Send a single prompt and get a response."""
    asyncio.run(run_single_prompt(prompt, provider, model, no_mcp, sandbox))


MCP_CONFIG_GLOBAL = "~/.agents/mcps/mcp_servers.json"


def _mcp_config_local() -> str:
    """Return path to project-local MCP config (cwd/.agents/mcps/mcp_servers.json)."""
    return str(Path.cwd() / ".agents" / "mcps" / "mcp_servers.json")


@cli.command(name="mcp-import")
@click.argument("toolset")
@click.argument(
    "sources",
    nargs=-1,
    type=_SourceType(),
    required=False,
)
@click.option(
    "--global",
    "global_",
    is_flag=True,
    help="Install to ~/.agents/mcps/ instead of current directory .agents/mcps/.",
)
@click.option(
    "--container-runner",
    type=str,
    default=None,
    help="Container runtime for CWL tools (e.g. docker, podman, singularity, udocker). "
    "Default: coala's default (typically docker).",
)
def mcp_import(
    toolset: str,
    sources: tuple[str, ...],
    global_: bool,
    container_runner: str | None,
) -> None:
    """Import CWL as an MCP server from coala-repo or from SOURCES.

    With no SOURCES: imports from coala-repo GitHub (data/TOOLSET), e.g. `coala mcp bwa`.
    For private repo, set COALA_REPO_TOKEN or GITHUB_TOKEN.

    With SOURCES: copies or unzips SOURCES into the MCP toolset dir, creates run_mcp.py,
    and adds the server to the MCP config.

    Default (no flag) installs to .agents/mcps/ in the current directory.
    Use --global to install to ~/.agents/mcps/ instead.

    SOURCES: local paths or http(s) URLs to .cwl files or a .zip containing .cwl.
    """
    if global_:
        mcp_config_file = MCP_CONFIG_GLOBAL
    else:
        # Default: project-local .agents/mcps/
        mcp_config_file = _mcp_config_local()
    Path(mcp_config_file).expanduser().parent.mkdir(parents=True, exist_ok=True)
    try:
        if not sources:
            entry = import_cwl_toolset_from_coala_repo(
                toolset,
                mcp_config_file=mcp_config_file,
                container_runner=container_runner,
            )
        else:
            entry = import_cwl_toolset(
                toolset,
                list(sources),
                mcp_config_file=mcp_config_file,
                container_runner=container_runner,
            )
    except (FileNotFoundError, ValueError, OSError) as e:
        click.echo(str(e), err=True)
        raise SystemExit(1) from e
    config_display = mcp_config_file.replace(str(Path.home()), "~")
    mcps_base = str(Path(mcp_config_file).expanduser().parent).replace(str(Path.home()), "~")
    click.echo(f"MCP server added to {config_display}. Entry:")
    click.echo()
    click.echo(json.dumps({"mcpServers": {toolset: entry}}, indent=2))
    click.echo()
    click.echo(f"Toolset directory: {mcps_base}/{toolset}/")
    click.echo("Script: run_mcp.py")


@cli.command(name="mcp")
@click.argument("toolset")
@click.argument(
    "sources",
    nargs=-1,
    type=_SourceType(),
    required=False,
)
@click.option(
    "--global",
    "global_",
    is_flag=True,
    help="Install to ~/.agents/mcps/ instead of current directory .agents/mcps/.",
)
@click.option(
    "--container-runner",
    type=str,
    default=None,
    help="Container runtime for CWL tools (e.g. docker, podman, singularity, udocker). "
    "Default: coala's default (typically docker).",
)
def mcp(
    toolset: str,
    sources: tuple[str, ...],
    global_: bool,
    container_runner: str | None,
) -> None:
    """Alias for mcp-import. Import from coala-repo (e.g. coala mcp bwa) or from SOURCES."""
    ctx = click.get_current_context()
    ctx.invoke(
        mcp_import,
        toolset=toolset,
        sources=sources,
        global_=global_,
        container_runner=container_runner,
    )


@cli.command(name="mcp-list")
@click.argument("server_name", required=False)
def mcp_list(server_name: str | None) -> None:
    """List MCP servers, or list tool schemas for a server.

    Without SERVER_NAME: list configured server names.
    With SERVER_NAME: connect to that server and print each tool's schema (name, description, inputSchema).
    """
    if server_name is None:
        asyncio.run(_mcp_list_servers())
    else:
        asyncio.run(_mcp_list_tools(server_name))


@cli.command(name="mcp-call")
@click.argument("server_dot_tool")
@click.option(
    "--args",
    "args_json",
    required=True,
    help='JSON object of tool arguments, e.g. \'{"data": [{"gene": "TP53", "taxon": "human"}]}\'',
)
def mcp_call(server_dot_tool: str, args_json: str) -> None:
    """Run an MCP tool with the given arguments.

    SERVER_DOT_TOOL: server name and tool name joined by a dot (e.g. gene-variant.ncbi_datasets_gene).
    """
    asyncio.run(_mcp_call_tool(server_dot_tool, args_json))


def _is_toolset_from_coala_repo(sources: tuple[str, ...]) -> str | None:
    """If a single non-URL, non-existing path is given, treat as toolset name for coala-repo."""
    if len(sources) != 1:
        return None
    s = sources[0].strip()
    if s.startswith("http://") or s.startswith("https://"):
        return None
    if Path(s).expanduser().resolve().exists():
        return None
    return s


@cli.command()
@click.argument(
    "sources",
    nargs=-1,
    type=str,
    required=False,
)
@click.option(
    "--global",
    "global_",
    is_flag=True,
    help="Install to ~/.agents/skills/ instead of current directory .agents/skills/.",
)
def skill(sources: tuple[str, ...], global_: bool) -> None:
    """Import skills from coala-repo or from SOURCES.

    With a single toolset name (e.g. bwa): imports from coala-repo data/TOOLSET/skills,
    e.g. `coala skill bwa`. For private repo, set COALA_REPO_TOKEN or GITHUB_TOKEN.

    With SOURCES: GitHub tree URL, zip URL, or local zip/directory path.

    Default (no flag) installs to .agents/skills/ in the current directory.
    Use --global to install to ~/.agents/skills/ instead.
    """
    if not sources:
        click.echo("Usage: coala skill <toolset>  or  coala skill <SOURCES...>", err=True)
        raise SystemExit(1)
    if global_:
        skills_dir = GLOBAL_SKILLS_DIR
    else:
        # Default: project-local .agents/skills/
        skills_dir = get_local_skills_dir()
    try:
        toolset = _is_toolset_from_coala_repo(sources)
        if toolset is not None:
            dest = import_skills_from_coala_repo(toolset, skills_dir=skills_dir)
        else:
            dest = import_skills(list(sources), skills_dir=skills_dir)
    except (FileNotFoundError, ValueError, OSError) as e:
        click.echo(str(e), err=True)
        raise SystemExit(1) from e
    click.echo(f"Skills imported to {dest}")


@cli.command()
@click.argument("query", required=True)
@click.option(
    "--refresh",
    is_flag=True,
    help="Ignore cache and re-fetch the tools index",
)
def search(query: str, refresh: bool) -> None:
    """Search for tools in the coala repo.

    Uses the package index from coala-mp (cached after first run). QUERY is matched
    against tool name, id, description, etc.
    """
    try:
        index = get_tools_index(force_refresh=refresh)
    except OSError as e:
        click.echo(f"Failed to load tools index: {e}", err=True)
        raise SystemExit(1) from e
    matches = search_tools(index, query)
    if not matches:
        click.echo("No tools found.")
        return
    for t in matches:
        name = t.get("name") or t.get("id") or t.get("toolset") or "(no name)"
        desc = t.get("description") or t.get("desc") or ""
        line = name if not desc else f"{name}: {desc[:80]}{'...' if len(desc) > 80 else ''}"
        click.echo(line)


@cli.command()
def config() -> None:
    """Show current configuration."""
    cfg = load_config()
    click.echo("Current Configuration:")
    click.echo(f"  Provider: {cfg.provider}")
    click.echo(f"  OpenAI Model: {cfg.openai_model}")
    click.echo(f"  Gemini Model: {cfg.gemini_model}")
    click.echo(f"  Ollama Model: {cfg.ollama_model}")
    click.echo(f"  MCP Config: {cfg.mcp_config_file}")

    click.echo("\nEnvironment Variables:")
    click.echo("  PROVIDER - Default provider (openai/gemini/ollama/custom)")
    click.echo("  OPENAI_API_KEY - OpenAI API key")
    click.echo("  OPENAI_MODEL - OpenAI model name")
    click.echo("  GEMINI_API_KEY - Gemini API key")
    click.echo("  GEMINI_MODEL - Gemini model name")
    click.echo("  OLLAMA_BASE_URL - Ollama base URL")
    click.echo("  OLLAMA_MODEL - Ollama model name")


if __name__ == "__main__":
    cli()
