---
name: coala-client
description: How to use the coala-client CLI for chat with LLMs, MCP servers, and skills. Use when the user asks how to use coala, run coala chat, add MCP servers, import CWL toolsets, list or call MCP tools, import or load skills, or configure project-local vs global agents paths.
homepage: https://github.com/coala-info/coala_client
metadata: {"clawdbot":{"emoji":"🧬","requires":{"bins":["coala-client"]},"install":[{"id":"uv","kind":"uv","package":"coala-client","bins":["coala-client"],"label":"Install coala-client (uv)"}]}}
---

# Coala Client

Part of the coala ecosystem. CLI for chat with OpenAI-compatible LLMs (OpenAI, Gemini, Ollama) and MCP (Model Context Protocol) servers. Supports importing CWL toolsets as MCP servers and importing skills.

## Config paths

**Chat / ask** read MCP servers from the path in `MCP_CONFIG_FILE` (env), defaulting to `~/.config/coala/mcps/mcp_servers.json`. They load optional shared env from `~/.config/coala/env` (or `ENV_FILE`).

**`coala mcp` / `coala mcp-import`** (imports) by default write to the **current project**:

- `<cwd>/.agents/mcps/mcp_servers.json` — server definitions merged on each import  
- `<cwd>/.agents/mcps/<toolset>/` — per-toolset dirs with `run_mcp.py` and CWL files  

Use **`--global`** to install under **`~/.agents/mcps/`** instead (same layout under the home path).

**`coala skill`** (imports) by default writes to **`<cwd>/.agents/skills/`** (one subfolder per source). Use **`--global`** for **`~/.agents/skills/`**.

**Legacy / still supported:** `~/.config/coala/skills/` — chat’s `/skill` resolves skills in this order: local `.agents/skills`, then `~/.config/coala/skills`, then `~/.agents/skills`.

**`coala init`** creates `~/.config/coala/mcps/mcp_servers.json` and `~/.config/coala/env` (global defaults for keys and MCP env).

If you import MCP toolsets **without** `--global`, set **`MCP_CONFIG_FILE`** to your project file (e.g. `$PWD/.agents/mcps/mcp_servers.json`) so chat uses the same config, or merge entries into the default global file.

## Quick start

1. **Init (first time)**  
   `coala init` — creates `~/.config/coala/mcps/mcp_servers.json` and `env`.

2. **Set API key**  
   e.g. `export OPENAI_API_KEY=...` or `export GEMINI_API_KEY=...`. Ollama needs no key.

3. **Chat**  
   `coala` or `coala chat` — interactive chat with MCP tools.  
   `coala ask "question"` or `coala -c "question"` / `coala --command "question"` — single prompt with MCP.

4. **Options**  
   `-p, --provider` (openai|gemini|ollama|custom), `-m, --model`, `--no-mcp`, **`--sandbox`** (enables a `run_command` tool for basic shell commands from the LLM).

## MCP: CWL toolsets

No API key needed for MCP import, list, or call — only for chat/ask with an LLM.

- **Import** (registers server and writes toolset files):  
  - **From coala-repo** (only the tool folder is downloaded, no full repo):  
    `coala mcp <TOOLSET>` e.g. `coala mcp bwa` (imports from coala-repo `data/<TOOLSET>/`).  
    For a **private** coala-repo, set **`COALA_REPO_TOKEN`** or **`GITHUB_TOKEN`**.  
  - **From your own sources:**  
    `coala mcp <TOOLSET> <SOURCES...>` or `coala mcp-import <TOOLSET> <SOURCES...>`  
    SOURCES: local `.cwl` files, a `.zip`, or http(s) URLs to a .cwl or .zip.  
  **Default install location:** project `.agents/mcps/`; add **`--global`** for `~/.agents/mcps/`.  
  Requires the **`coala`** package where the MCP server runs (for `run_mcp.py`).

- **List**  
  `coala mcp-list` — list server names (from the MCP config file chat uses).  
  `coala mcp-list <SERVER_NAME>` — print each tool’s schema (name, description, inputSchema).

- **Call**  
  `coala mcp-call <SERVER>.<TOOL> --args '<JSON>'`  
  Example: `coala mcp-call gene-variant.ncbi_datasets_gene --args '{"data": [{"gene": "TP53", "taxon": "human"}]}'`

## Skills

- **Import:**  
  - **From coala-repo** (only the skills folder is downloaded):  
    `coala skill <TOOLSET>` e.g. `coala skill bwa` (from coala-repo `data/<TOOLSET>/skills/`).  
  - **From URL or path:**  
    `coala skill <SOURCES...>` — GitHub tree URL, zip URL, or local zip/dir.  
  **Default:** `<cwd>/.agents/skills/`; **`--global`** → `~/.agents/skills/`.  
  Private repo: **`COALA_REPO_TOKEN`** or **`GITHUB_TOKEN`**.

- **In chat**  
  `/skill` — list installed skills (union of local, `~/.config/coala/skills`, `~/.agents/skills`).  
  `/skill <name>` — load skill from `<name>/` (prefers `SKILL.md`, else first `.md` in the folder).

## Search tools

- **Search** the coala tools index (from coala-mp; cached at `~/.config/coala/cache/tools-index.json`):  
  `coala search <QUERY>` — e.g. `coala search bwa`. Exact name matches appear first.  
  `coala search <QUERY> --refresh` — re-fetch the index.

## Chat commands

- `/help`, `/exit`, `/quit`, `/clear`  
- `/tools` — list MCP tools  
- `/servers` — list connected MCP servers  
- `/skill` — list skills; `/skill <name>` — load a skill  
- `/model` — show model info  
- `/switch <provider>` — switch provider  

## MCP on/off

- **All off:** `coala --no-mcp` (or `coala ask "..." --no-mcp`).  
- **Per file:** edit or split the JSON referenced by **`MCP_CONFIG_FILE`** (default `~/.config/coala/mcps/mcp_servers.json`).  
- **On:** default when `--no-mcp` is not used; servers are loaded from that config.

## Providers and env

Set provider via `-p` or env **`PROVIDER`**. Set keys and URLs per provider (e.g. `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OLLAMA_BASE_URL`). Optional: put vars in `~/.config/coala/env`.  
**`MCP_CONFIG_FILE`** — path to `mcp_servers.json` for chat and `mcp-list` / `mcp-call`.  

`coala config` — print current config paths and provider/model info.
