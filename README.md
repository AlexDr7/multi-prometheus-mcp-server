# Prometheus MCP Server
[![GitHub Container Registry](https://img.shields.io/badge/ghcr.io-pab1it0%2Fprometheus--mcp--server-blue?logo=docker)](https://github.com/users/pab1it0/packages/container/package/prometheus-mcp-server)
[![GitHub Release](https://img.shields.io/github/v/release/pab1it0/prometheus-mcp-server)](https://github.com/pab1it0/prometheus-mcp-server/releases)
[![Codecov](https://codecov.io/gh/pab1it0/prometheus-mcp-server/branch/main/graph/badge.svg)](https://codecov.io/gh/pab1it0/prometheus-mcp-server)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
[![License](https://img.shields.io/github/license/pab1it0/prometheus-mcp-server)](https://github.com/pab1it0/prometheus-mcp-server/blob/main/LICENSE)

A [Model Context Protocol][mcp] (MCP) server for Prometheus.

This provides access to your Prometheus metrics and queries through standardized MCP interfaces, allowing AI assistants to execute PromQL queries and analyze your metrics data.

[mcp]: https://modelcontextprotocol.io

## Features

- [x] Execute PromQL queries against Prometheus
- [x] Discover and explore metrics
  - [x] List available metrics
  - [x] Get metadata for specific metrics
  - [x] View instant query results
  - [x] View range query results with different step intervals
- [x] Authentication support
  - [x] Basic auth from environment variables
  - [x] Bearer token auth from environment variables
- [x] Docker containerization support

- [x] Provide interactive tools for AI assistants

The list of tools is configurable, so you can choose which tools you want to make available to the MCP client.
This is useful if you don't use certain functionality or if you don't want to take up too much of the context window.

## Getting Started

### Prerequisites

- Prometheus server accessible from your environment
- MCP-compatible client (Claude Desktop, VS Code, Cursor, Windsurf, etc.)

### Installation Methods

<details>
<summary><b>Claude Desktop</b></summary>

Add to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "prometheus": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "PROMETHEUS_URL",
        "ghcr.io/pab1it0/prometheus-mcp-server:latest"
      ],
      "env": {
        "PROMETHEUS_URL": "<your-prometheus-url>"
      }
    }
  }
}
```
</details>

<details>
<summary><b>Claude Code</b></summary>

Install via the Claude Code CLI:

```bash
claude mcp add prometheus --env PROMETHEUS_URL=http://your-prometheus:9090 -- docker run -i --rm -e PROMETHEUS_URL ghcr.io/pab1it0/prometheus-mcp-server:latest
```
</details>

<details>
<summary><b>VS Code / Cursor / Windsurf</b></summary>

Add to your MCP settings in the respective IDE:

```json
{
  "prometheus": {
    "command": "docker",
    "args": [
      "run",
      "-i",
      "--rm",
      "-e",
      "PROMETHEUS_URL",
      "ghcr.io/pab1it0/prometheus-mcp-server:latest"
    ],
    "env": {
      "PROMETHEUS_URL": "<your-prometheus-url>"
    }
  }
}
```
</details>

<details>
<summary><b>Docker Desktop</b></summary>

The easiest way to run the Prometheus MCP server is through Docker Desktop:

<a href="https://hub.docker.com/open-desktop?url=https://open.docker.com/dashboard/mcp/servers/id/prometheus/config?enable=true">
  <img src="https://img.shields.io/badge/+%20Add%20to-Docker%20Desktop-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Add to Docker Desktop" />
</a>

1. **Via MCP Catalog**: Visit the [Prometheus MCP Server on Docker Hub](https://hub.docker.com/mcp/server/prometheus/overview) and click the button above
   
2. **Via MCP Toolkit**: Use Docker Desktop's MCP Toolkit extension to discover and install the server

3. Configure your connection using environment variables (see Configuration Options below)

</details>

<details>
<summary><b>Manual Docker Setup</b></summary>

Run directly with Docker:

```bash
# With environment variables
docker run -i --rm \
  -e PROMETHEUS_URL="http://your-prometheus:9090" \
  ghcr.io/pab1it0/prometheus-mcp-server:latest

# With authentication
docker run -i --rm \
  -e PROMETHEUS_URL="http://your-prometheus:9090" \
  -e PROMETHEUS_USERNAME="admin" \
  -e PROMETHEUS_PASSWORD="password" \
  ghcr.io/pab1it0/prometheus-mcp-server:latest
```
</details>

### Configuration Options

#### Single-Region Configuration (Legacy)

For a single Prometheus instance, use these environment variables:

| Variable | Description | Required |
|----------|-------------|----------|
| `PROMETHEUS_URL` | URL of your Prometheus server | Yes |
| `PROMETHEUS_URL_SSL_VERIFY` | Set to False to disable SSL verification | No (default: True) |
| `PROMETHEUS_DISABLE_LINKS` | Set to True to disable Prometheus UI links in query results (saves context tokens) | No (default: False) |
| `PROMETHEUS_USERNAME` | Username for basic authentication | No |
| `PROMETHEUS_PASSWORD` | Password for basic authentication | No |
| `PROMETHEUS_TOKEN` | Bearer token for authentication | No |
| `PROMETHEUS_CUSTOM_HEADERS` | Custom headers as JSON string | No |
| `ORG_ID` | Organization ID for multi-tenant setups | No |
| `PROMETHEUS_MCP_SERVER_TRANSPORT` | Transport mode (stdio, http, sse) | No (default: stdio) |
| `PROMETHEUS_MCP_BIND_HOST` | Host for HTTP transport | No (default: 127.0.0.1) |
| `PROMETHEUS_MCP_BIND_PORT` | Port for HTTP transport | No (default: 8080) |

#### Multi-Region Configuration

To query multiple Prometheus instances across different regions, use region-specific environment variables. Region names are case-insensitive (e.g., `ATL`, `atl`, `Atl` are equivalent).

**Region-specific URLs** (required for each region):
- `PROMETHEUS_URL_<REGION>` - Prometheus URL for the region (e.g., `PROMETHEUS_URL_ATL`, `PROMETHEUS_URL_BLR`, `PROMETHEUS_URL_WDC`)

**Region-specific authentication** (optional per region):
- `PROMETHEUS_USERNAME_<REGION>`, `PROMETHEUS_PASSWORD_<REGION>` - Basic auth credentials
- `PROMETHEUS_TOKEN_<REGION>` - Bearer token for authentication

**Region-specific SSL verification** (optional per region):
- `PROMETHEUS_SSL_VERIFY_<REGION>` - SSL verification setting (default: true)

**Region-specific custom headers** (optional per region):
- `PROMETHEUS_CUSTOM_HEADERS_<REGION>` - JSON string of custom headers

**Global settings**:
- `PROMETHEUS_DEFAULT_REGION` - Default region when none specified (default: first configured region)
- `PROMETHEUS_DISABLE_LINKS` - Disable Prometheus UI links globally
- `ORG_ID` - Organization ID for multi-tenant setups

**Example multi-region configuration:**

```bash
# Atlanta region
PROMETHEUS_URL_ATL=http://sos-proms01-atl01.example.com:9090
PROMETHEUS_TOKEN_ATL=atl_secret_token

# Bangalore region  
PROMETHEUS_URL_BLR=http://sos-proms01-blr01.example.com:9090
PROMETHEUS_SSL_VERIFY_BLR=false
PROMETHEUS_USERNAME_BLR=admin
PROMETHEUS_PASSWORD_BLR=password

# Washington DC region
PROMETHEUS_URL_WDC=http://sos-proms01-wdc01.example.com:9090
PROMETHEUS_CUSTOM_HEADERS_WDC={"X-Environment":"production"}

# Set default region
PROMETHEUS_DEFAULT_REGION=atl
```

#### Using the Region Parameter

All tools accept an optional `region` parameter to specify which Prometheus instance to query:

```python
# Query Atlanta region
execute_query(query="up", region="atl")

# Query Bangalore region  
execute_query(query="up", region="blr")

# Use default region (when not specified)
execute_query(query="up")

# Check health of all regions
health_check()

# Check health of specific region
health_check(region="wdc")
```

#### Migration from Single-Region to Multi-Region

If you have an existing single-region deployment:

1. **Keep existing variables** - Your legacy `PROMETHEUS_URL`, `PROMETHEUS_USERNAME`, etc. will continue to work
2. **Add new regions** - Add region-specific variables for additional Prometheus instances
3. **Set default region** - Optionally set `PROMETHEUS_DEFAULT_REGION` to control which region is used by default

The server maintains backward compatibility, so existing configurations will work without changes.

## Development

Contributions are welcome! Please see our [Contributing Guide](CONTRIBUTING.md) for detailed information on how to get started, coding standards, and the pull request process.

This project uses [`uv`](https://github.com/astral-sh/uv) to manage dependencies. Install `uv` following the instructions for your platform:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

You can then create a virtual environment and install the dependencies with:

```bash
uv venv
source .venv/bin/activate  # On Unix/macOS
.venv\Scripts\activate     # On Windows
uv pip install -e .
```

### Testing

The project includes a comprehensive test suite that ensures functionality and helps prevent regressions.

Run the tests with pytest:

```bash
# Install development dependencies
uv pip install -e ".[dev]"

# Run the tests
pytest

# Run with coverage report
pytest --cov=src --cov-report=term-missing
```

When adding new features, please also add corresponding tests.

### Tools

All tools support an optional `region` parameter to specify which Prometheus instance to query. If not specified, the default region is used.

| Tool | Category | Description |
| --- | --- | --- |
| `health_check` | System | Health check endpoint for container monitoring and status verification. Can check all regions or a specific region. |
| `execute_query` | Query | Execute a PromQL instant query against Prometheus. Optionally specify a region. |
| `execute_range_query` | Query | Execute a PromQL range query with start time, end time, and step interval. Optionally specify a region. |
| `list_metrics` | Discovery | List all available metrics in Prometheus with pagination and filtering support. Optionally specify a region. |
| `get_metric_metadata` | Discovery | Get metadata for a specific metric. Optionally specify a region. |
| `get_targets` | Discovery | Get information about all scrape targets. Optionally specify a region. |

## License

MIT

---

[mcp]: https://modelcontextprotocol.io
