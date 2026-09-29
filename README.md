# Coala Client

A simple command line interface for LLM with MCP (Model Context Protocol) server support and OpenAI-compatible API support.

## Features

- **OpenAI-compatible API support**: Works with OpenAI, Google Gemini, Ollama, and any OpenAI-compatible API
- **MCP Server integration**: Connect to multiple MCP servers for extended tool capabilities
- **Interactive chat**: Rich terminal UI with streaming responses
- **Tool calling**: Automatic tool execution with MCP servers

## Installation

```bash
pip install coala-client
```

## Quick Start

### 1. Initialize Configuration

```bash
coala init
```

This creates a default MCP servers configuration file at `~/.config/coala/mcps/mcp_servers.json`.

### 2. Set API Key

```bash
# For OpenAI
export OPENAI_API_KEY=your-openai-api-key

# For Gemini
export GEMINI_API_KEY=your-gemini-api-key

# Ollama doesn't require an API key (runs locally)
```

### 3. Start Chatting

```bash
# Interactive chat with default provider (OpenAI)
coala

# Use a specific provider
coala -p gemini
coala -p ollama

# Use a specific model
coala -p openai -m gpt-4-turbo

# Single prompt
coala ask "What is the capital of France?"

# Disable MCP servers
coala --no-mcp
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PROVIDER` | Default LLM provider | `openai` |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `OPENAI_BASE_URL` | OpenAI base URL | `https://api.openai.com/v1` |
| `OPENAI_MODEL` | OpenAI model | `gpt-4o` |
| `GEMINI_API_KEY` | Gemini API key | - |
| `GEMINI_BASE_URL` | Gemini base URL | `https://generativelanguage.googleapis.com/v1beta/openai` |
| `GEMINI_MODEL` | Gemini model | `gemini-2.5-flash-lite` |
| `OLLAMA_BASE_URL` | Ollama base URL | `http://localhost:11434/v1` |
| `OLLAMA_MODEL` | Ollama model | `qwen3` |
| `SYSTEM_PROMPT` | System prompt | `You are a helpful assistant.` |
| `MAX_TOKENS` | Max tokens in response | `4096` |
| `TEMPERATURE` | Temperature | `0.7` |
| `MCP_CONFIG_FILE` | MCP config file path | `~/.config/coala/mcps/mcp_servers.json` |

### MCP Servers Configuration

Edit `~/.config/coala/mcps/mcp_servers.json`:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"],
      "env": {}
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your-token"
      }
    }
  }
}
```

### Environment Variables for MCP Servers

You can set environment variables that will be available to all MCP servers by editing `~/.config/coala/env`:

```bash
# Environment variables for MCP servers
# Format: KEY=value

# Set default provider (openai, gemini, ollama, custom)
PROVIDER=gemini

# API keys and model settings
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-2.5-flash-lite
```

**Note:** The `PROVIDER` variable in the env file will set the default LLM provider. These variables will be merged with server-specific `env` settings in `mcp_servers.json`. Server-specific environment variables take precedence over the base environment variables.

## CLI Commands

### Interactive Chat

```bash
coala [OPTIONS]
coala chat [OPTIONS]
```

Options:
- `-p, --provider`: LLM provider (openai/gemini/ollama/custom)
- `-m, --model`: Model name override
- `--no-mcp`: Disable MCP servers
- `--sandbox`: Enable `run_command` tool so the LLM can run basic Linux shell commands (timeout 30s)

### Single Prompt

```bash
coala ask "Your prompt here"
coala -c "Your prompt here"
```

### Chat Commands

During interactive chat:
- `/help` - Show help
- `/exit` / `/quit` - Exit chat
- `/clear` - Clear conversation history
- `/tools` - List available MCP tools
- `/servers` - List connected MCP servers
- `/skill` - List installed skills (from ~/.config/coala/skills/)
- `/skill <name>` - Load a skill into the chat (adds its instructions to context)
- `/model` - Show current model info
- `/switch <provider>` - Switch provider

### Configuration

```bash
coala init    # Create default config files
coala config  # Show current configuration
```

### CWL toolset as MCP server

Import from the **coala-repo** (no full repo download; only the tool folder is fetched via GitHub API):

```bash
# Import from coala-repo (data/<TOOLSET>), e.g. data/bwa
coala mcp <TOOLSET>
coala mcp bwa
# Alias: coala mcp-import bwa
```

Or provide your own CWL sources:

```bash
# Import one or more CWL files into a named toolset (copied to ~/.config/coala/mcps/<toolset>/)
coala mcp <TOOLSET> file1.cwl [file2.cwl ...]

# Import a zip of CWL files (extracted to ~/.config/coala/mcps/<toolset>/)
coala mcp <TOOLSET> tools.zip

# SOURCES can also be http(s) URLs to a .cwl file or a .zip
coala mcp <TOOLSET> https://example.com/tools.zip
```

This creates `run_mcp.py` in `~/.config/coala/mcps/<toolset>/`, adds the server to `~/.config/coala/mcps/mcp_servers.json`, and prints the MCP entry. The generated script uses `coala.mcp_api` (stdio transport). Ensure the `coala` package is installed in the environment that runs the MCP server.

**List servers and tools:**

```bash
# List configured MCP server names
coala mcp-list

# Show tool schemas (name, description, inputSchema) for a server
coala mcp-list <SERVER_NAME>
```

**Call an MCP tool directly:**

```bash
coala mcp-call <SERVER>.<TOOL> --args '<JSON>'
# Example:
coala mcp-call gene-variant.ncbi_datasets_gene --args '{"data": [{"gene": "TP53", "taxon": "human"}]}'
```

### Skills

Import from the **coala-repo** (only the skills folder is fetched; no full repo download):

```bash
# Import from coala-repo (data/<TOOLSET>/skills), e.g. data/bwa/skills
coala skill <TOOLSET>
coala skill bwa
```

Or provide a GitHub tree URL, zip URL, or local path:

```bash
# Import skills from a GitHub folder (e.g. vercel-labs/agent-skills/skills)
coala skill https://github.com/vercel-labs/agent-skills/tree/main/skills

# Import from a zip URL or local zip/directory
coala skill http://localhost:3000/files/bedtools/bedtools-skills.zip
coala skill ./my-skills.zip
```

All skills are copied to `~/.config/coala/skills/`. Each source gets its own subfolder (e.g. `skills/bwa/` for `coala skill bwa`, `skills/bedtools/` for a zip from `.../bedtools/bedtools-skills.zip`).

### Search tools (coala repo)

Search the coala tools index (from [coala-mp](https://github.com/coala-info/coala-mp); cached after first run):

```bash
# Search by name or description (exact name match listed first)
coala search <QUERY>
coala search bwa

# Re-fetch the index (ignore cache)
coala search bwa --refresh
```

The index is cached at `~/.config/coala/cache/tools-index.json`.

## Examples

### Using with Ollama

```bash
# Start Ollama server
ollama serve

# Pull a model
ollama pull llama3.2

# Chat with Ollama
coala -p ollama -m llama3.2
```

### Using with Gemini

```bash
export GEMINI_API_KEY=your-api-key
coala -p gemini
```

### Using Custom OpenAI-compatible API

```bash
export CUSTOM_API_KEY=your-api-key
export CUSTOM_BASE_URL=https://your-api.com/v1
export CUSTOM_MODEL=your-model
coala -p custom
```

## Development

```bash
# Install with dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest
```

## Publishing to PyPI

The repo includes a GitHub Action (`.github/workflows/release.yml`) that builds with uv (`uv build`) and publishes to PyPI when a release is published.

1. **Create a GitHub environment** named `pypi` (optional but recommended).
2. **Configure PyPI** using one of:
   - **Trusted Publishing (recommended)**: In PyPI → Your projects → coala-client → Publishing, add a new trusted publisher: GitHub, this repo, workflow `publish-pypi.yml`, environment `pypi`. No secrets needed.
   - **API token**: Generate a token at pypi.org, add it as repository (or `pypi` environment) secret `PYPI_API_TOKEN`.
3. **Publish**: Create a new release (tag e.g. `v0.1.0`). The workflow runs on release and uploads the built package. You can also run it manually (Actions → Build and publish to PyPI → Run workflow).

## License

MIT
