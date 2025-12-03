#!/usr/bin/env python

import os
import json
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
import time
from datetime import datetime, timedelta
from enum import Enum

import dotenv
import requests
from fastmcp import FastMCP, Context
from prometheus_mcp_server.logging_config import get_logger

dotenv.load_dotenv()
mcp = FastMCP("Prometheus MCP")

# Cache for metrics list to improve completion performance (per region)
_metrics_cache = {}  # Dict[str, Dict[str, Any]] - key is "{region}_metrics"
_CACHE_TTL = 300  # 5 minutes

# Get logger instance
logger = get_logger()

# Health check tool for Docker containers and monitoring
@mcp.tool(
    description="Health check endpoint for container monitoring and status verification. Can check all regions or a specific region.",
    annotations={
        "title": "Health Check",
        "icon": "❤️",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def health_check(region: Optional[str] = None) -> Dict[str, Any]:
    """Return health status of the MCP server and Prometheus connection(s).
    
    Args:
        region: Optional region name to check (case-insensitive). If not specified, checks all regions.

    Returns:
        Health status including service information, configuration, and connectivity for all or specified region(s)
    """
    try:
        health_status = {
            "status": "healthy",
            "service": "prometheus-mcp-server",
            "version": "1.5.1",
            "timestamp": datetime.utcnow().isoformat(),
            "transport": config.mcp_server_config.mcp_server_transport if config.mcp_server_config else "stdio",
            "configuration": {
                "regions_configured": list(config.regions.keys()),
                "default_region": config.default_region,
                "org_id_configured": bool(config.org_id)
            }
        }
        
        # If region specified, check only that region
        if region:
            try:
                region_name, region_config = get_region_config(region)
                
                # Test Prometheus connectivity for the specified region
                try:
                    make_prometheus_request("query", params={"query": "up", "time": str(int(time.time()))}, region=region_name)
                    health_status["prometheus_connectivity"] = "healthy"
                    health_status["prometheus_url"] = region_config.url
                    health_status["region"] = region_name
                except Exception as e:
                    health_status["prometheus_connectivity"] = "unhealthy"
                    health_status["prometheus_error"] = str(e)
                    health_status["region"] = region_name
                    health_status["status"] = "degraded"
                    
            except ValueError as e:
                # Invalid region specified
                health_status["status"] = "unhealthy"
                health_status["error"] = str(e)
        else:
            # Check all regions
            regions_status = {}
            all_healthy = True
            
            for region_name, region_config in config.regions.items():
                try:
                    # Quick connectivity test
                    make_prometheus_request("query", params={"query": "up", "time": str(int(time.time()))}, region=region_name)
                    regions_status[region_name] = {
                        "prometheus_connectivity": "healthy",
                        "prometheus_url": region_config.url
                    }
                except Exception as e:
                    regions_status[region_name] = {
                        "prometheus_connectivity": "degraded",
                        "prometheus_error": str(e)
                    }
                    all_healthy = False
            
            health_status["regions"] = regions_status
            if not all_healthy:
                health_status["status"] = "degraded"
        
        logger.info("Health check completed", status=health_status["status"], region=region)
        return health_status
        
    except Exception as e:
        logger.error("Health check failed", error=str(e), region=region)
        return {
            "status": "unhealthy",
            "service": "prometheus-mcp-server",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


class TransportType(str, Enum):
    """Supported MCP server transport types."""

    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"

    @classmethod
    def values(cls) -> list[str]:
        """Get all valid transport values."""
        return [transport.value for transport in cls]

@dataclass
class MCPServerConfig:
    """Global Configuration for MCP."""
    mcp_server_transport: TransportType = None
    mcp_bind_host: str = None
    mcp_bind_port: int = None

    def __post_init__(self):
        """Validate mcp configuration."""
        if not self.mcp_server_transport:
            raise ValueError("MCP SERVER TRANSPORT is required")
        if not self.mcp_bind_host:
            raise ValueError(f"MCP BIND HOST is required")
        if not self.mcp_bind_port:
            raise ValueError(f"MCP BIND PORT is required")

@dataclass
class RegionConfig:
    """Configuration for a single Prometheus region."""
    url: str
    url_ssl_verify: bool = True
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    custom_headers: Optional[Dict[str, str]] = None

@dataclass
class PrometheusConfig:
    regions: Dict[str, RegionConfig]  # Map of region name to config
    default_region: str
    disable_prometheus_links: bool = False
    # Optional Org ID for multi-tenant setups
    org_id: Optional[str] = None
    # Optional Custom MCP Server Configuration
    mcp_server_config: Optional[MCPServerConfig] = None

def parse_region_configs() -> Dict[str, RegionConfig]:
    """Parse region configurations from environment variables.
    
    Supports both region-specific variables (e.g., PROMETHEUS_URL_ATL)
    and legacy single-region variables (e.g., PROMETHEUS_URL).
    
    Returns:
        Dictionary mapping region names to RegionConfig objects
    """
    regions = {}
    
    # Check for region-specific configurations
    # Look for environment variables with region suffixes
    region_suffixes = set()
    for key in os.environ.keys():
        if key.startswith("PROMETHEUS_URL_"):
            suffix = key[len("PROMETHEUS_URL_"):]
            if suffix:  # Ensure there's a suffix after PROMETHEUS_URL_
                region_suffixes.add(suffix)
    
    # Parse each region-specific configuration
    for region_suffix in region_suffixes:
        region_name = region_suffix.lower()
        url = os.environ.get(f"PROMETHEUS_URL_{region_suffix}")
        
        if url:
            # Parse custom headers if provided
            custom_headers_str = os.environ.get(f"PROMETHEUS_CUSTOM_HEADERS_{region_suffix}")
            custom_headers = None
            if custom_headers_str:
                try:
                    custom_headers = json.loads(custom_headers_str)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse custom headers for region {region_name}", error="Invalid JSON")
            
            regions[region_name] = RegionConfig(
                url=url,
                url_ssl_verify=os.environ.get(f"PROMETHEUS_SSL_VERIFY_{region_suffix}", "True").lower() in ("true", "1", "yes"),
                username=os.environ.get(f"PROMETHEUS_USERNAME_{region_suffix}", ""),
                password=os.environ.get(f"PROMETHEUS_PASSWORD_{region_suffix}", ""),
                token=os.environ.get(f"PROMETHEUS_TOKEN_{region_suffix}", ""),
                custom_headers=custom_headers
            )
            logger.info(f"Configured region {region_name}", url=url)
    
    # Backward compatibility: Check for legacy single-region configuration
    legacy_url = os.environ.get("PROMETHEUS_URL", "")
    if legacy_url and not regions:
        # No region-specific configs found, use legacy config as default region
        custom_headers_str = os.environ.get("PROMETHEUS_CUSTOM_HEADERS")
        custom_headers = None
        if custom_headers_str:
            try:
                custom_headers = json.loads(custom_headers_str)
            except json.JSONDecodeError:
                logger.warning("Failed to parse legacy custom headers", error="Invalid JSON")
        
        regions["default"] = RegionConfig(
            url=legacy_url,
            url_ssl_verify=os.environ.get("PROMETHEUS_URL_SSL_VERIFY", "True").lower() in ("true", "1", "yes"),
            username=os.environ.get("PROMETHEUS_USERNAME", ""),
            password=os.environ.get("PROMETHEUS_PASSWORD", ""),
            token=os.environ.get("PROMETHEUS_TOKEN", ""),
            custom_headers=custom_headers
        )
        logger.info("Using legacy single-region configuration", url=legacy_url)
    
    return regions

# Parse regions and create global config
_regions = parse_region_configs()
_default_region = os.environ.get("PROMETHEUS_DEFAULT_REGION", "").lower()

# If no default region specified, use the first available region or "default"
if not _default_region:
    if "default" in _regions:
        _default_region = "default"
    elif _regions:
        _default_region = next(iter(_regions.keys()))
    else:
        # No regions configured - this is allowed for testing purposes
        _default_region = "default"
        logger.warning("No Prometheus regions configured. Server will not be able to query Prometheus until configured.")

config = PrometheusConfig(
    regions=_regions,
    default_region=_default_region,
    disable_prometheus_links=os.environ.get("PROMETHEUS_DISABLE_LINKS", "False").lower() in ("true", "1", "yes"),
    org_id=os.environ.get("ORG_ID", ""),
    mcp_server_config=MCPServerConfig(
        mcp_server_transport=os.environ.get("PROMETHEUS_MCP_SERVER_TRANSPORT", "stdio").lower(),
        mcp_bind_host=os.environ.get("PROMETHEUS_MCP_BIND_HOST", "127.0.0.1"),
        mcp_bind_port=int(os.environ.get("PROMETHEUS_MCP_BIND_PORT", "8080"))
    )
)

# Log configuration status
if config.regions:
    # Validate default region exists
    if config.default_region not in config.regions:
        available_regions = ", ".join(config.regions.keys())
        logger.error(f"Default region '{config.default_region}' not found", available_regions=available_regions)
        raise ValueError(f"Default region '{config.default_region}' is not configured. Available regions: {available_regions}")
    logger.info(f"Prometheus MCP Server configured with {len(config.regions)} region(s)", regions=list(config.regions.keys()), default_region=config.default_region)
else:
    logger.warning("No Prometheus regions configured. Configure at least one region for the server to function.")

def get_region_config(region: Optional[str] = None) -> tuple[str, RegionConfig]:
    """Get configuration for a specific region.
    
    Args:
        region: Region name (case-insensitive). If None, uses default region.
        
    Returns:
        Tuple of (region_name, RegionConfig)
        
    Raises:
        ValueError: If the specified region is not configured
    """
    if region is None:
        region = config.default_region
    
    # Normalize region name to lowercase
    region_normalized = region.lower()
    
    # Check if region exists
    if region_normalized not in config.regions:
        available_regions = ", ".join(sorted(config.regions.keys()))
        logger.error(f"Region '{region}' not found", available_regions=available_regions)
        raise ValueError(f"Region '{region}' is not configured. Available regions: {available_regions}")
    
    return region_normalized, config.regions[region_normalized]

def get_prometheus_auth(region_config: RegionConfig):
    """Get authentication for Prometheus based on provided credentials.
    
    Args:
        region_config: RegionConfig object containing authentication credentials
        
    Returns:
        Authentication object (dict for bearer token, HTTPBasicAuth for basic auth, or None)
    """
    if region_config.token:
        return {"Authorization": f"Bearer {region_config.token}"}
    elif region_config.username and region_config.password:
        return requests.auth.HTTPBasicAuth(region_config.username, region_config.password)
    return None

def make_prometheus_request(endpoint, params=None, region: Optional[str] = None):
    """Make a request to the Prometheus API with proper authentication and headers.
    
    Args:
        endpoint: Prometheus API endpoint
        params: Query parameters
        region: Region name (case-insensitive). If None, uses default region.
        
    Returns:
        Response data from Prometheus API
        
    Raises:
        ValueError: If region is not configured or API returns an error
    """
    region_name, region_config = get_region_config(region)
    
    if not region_config.url:
        logger.error("Prometheus URL missing for region", region=region_name)
        raise ValueError(f"Prometheus URL is not configured for region '{region_name}'.")
    
    if not region_config.url_ssl_verify:
        logger.warning("SSL certificate verification is disabled. This is insecure and should not be used in production environments.", endpoint=endpoint, region=region_name)

    url = f"{region_config.url.rstrip('/')}/api/v1/{endpoint}"
    url_ssl_verify = region_config.url_ssl_verify
    auth = get_prometheus_auth(region_config)
    headers = {}

    if isinstance(auth, dict):  # Token auth is passed via headers
        headers.update(auth)
        auth = None  # Clear auth for requests.get if it's already in headers
    
    # Add OrgID header if specified
    if config.org_id:
        headers["X-Scope-OrgID"] = config.org_id

    if region_config.custom_headers:
        headers.update(region_config.custom_headers)

    try:
        logger.debug("Making Prometheus API request", endpoint=endpoint, url=url, params=params, headers=headers, region=region_name)

        # Make the request with appropriate headers and auth
        response = requests.get(url, params=params, auth=auth, headers=headers, verify=url_ssl_verify)
        
        response.raise_for_status()
        result = response.json()
        
        if result["status"] != "success":
            error_msg = result.get('error', 'Unknown error')
            logger.error("Prometheus API returned error", endpoint=endpoint, error=error_msg, status=result["status"], region=region_name)
            raise ValueError(f"Prometheus API error: {error_msg}")
        
        data_field = result.get("data", {})
        if isinstance(data_field, dict):
            result_type = data_field.get("resultType")
        else:
            result_type = "list"
        logger.debug("Prometheus API request successful", endpoint=endpoint, result_type=result_type, region=region_name)
        return result["data"]
    
    except requests.exceptions.RequestException as e:
        logger.error("HTTP request to Prometheus failed", endpoint=endpoint, url=url, error=str(e), error_type=type(e).__name__, region=region_name)
        raise
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Prometheus response as JSON", endpoint=endpoint, url=url, error=str(e), region=region_name)
        raise ValueError(f"Invalid JSON response from Prometheus: {str(e)}")
    except Exception as e:
        logger.error("Unexpected error during Prometheus request", endpoint=endpoint, url=url, error=str(e), error_type=type(e).__name__, region=region_name)
        raise

def get_cached_metrics(region: Optional[str] = None) -> List[str]:
    """Get metrics list with caching to improve completion performance.
    
    Args:
        region: Region name (case-insensitive). If None, uses default region.

    This helper function is available for future completion support when
    FastMCP implements the completion capability. For now, it can be used
    internally to optimize repeated metric list requests.
    """
    region_name = region.lower() if region else config.default_region
    cache_key = f"{region_name}_metrics"
    current_time = time.time()

    # Check if cache is valid for this region
    if cache_key in _metrics_cache and _metrics_cache[cache_key]["data"] is not None and (current_time - _metrics_cache[cache_key]["timestamp"]) < _CACHE_TTL:
        logger.debug("Using cached metrics list", cache_age=current_time - _metrics_cache[cache_key]["timestamp"], region=region_name)
        return _metrics_cache[cache_key]["data"]

    # Fetch fresh metrics
    try:
        data = make_prometheus_request("label/__name__/values", region=region)
        _metrics_cache[cache_key] = {"data": data, "timestamp": current_time}
        logger.debug("Refreshed metrics cache", metric_count=len(data), region=region_name)
        return data
    except Exception as e:
        logger.error("Failed to fetch metrics for cache", error=str(e), region=region_name)
        # Return cached data if available, even if expired
        if cache_key in _metrics_cache and _metrics_cache[cache_key]["data"] is not None:
            return _metrics_cache[cache_key]["data"]
        return []

# Note: Argument completions will be added when FastMCP supports the completion
# capability. The get_cached_metrics() function above is ready for that integration.

@mcp.tool(
    description="Execute a PromQL instant query against Prometheus",
    annotations={
        "title": "Execute PromQL Query",
        "icon": "📊",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def execute_query(query: str, time: Optional[str] = None, region: Optional[str] = None) -> Dict[str, Any]:
    """Execute an instant query against Prometheus.

    Args:
        query: PromQL query string
        time: Optional RFC3339 or Unix timestamp (default: current time)
        region: Optional region name (case-insensitive). If not specified, uses default region.

    Returns:
        Query result with type (vector, matrix, scalar, string) and values
    """
    params = {"query": query}
    if time:
        params["time"] = time
    
    region_name = region.lower() if region else config.default_region
    logger.info("Executing instant query", query=query, time=time, region=region_name)
    data = make_prometheus_request("query", params=params, region=region)

    result = {
        "resultType": data["resultType"],
        "result": data["result"],
        "region": region_name
    }

    if not config.disable_prometheus_links:
        from urllib.parse import urlencode
        region_normalized, region_config = get_region_config(region)
        ui_params = {"g0.expr": query, "g0.tab": "0"}
        if time:
            ui_params["g0.moment_input"] = time
        prometheus_ui_link = f"{region_config.url.rstrip('/')}/graph?{urlencode(ui_params)}"
        result["links"] = [{
            "href": prometheus_ui_link,
            "rel": "prometheus-ui",
            "title": "View in Prometheus UI"
        }]

    logger.info("Instant query completed",
                query=query,
                result_type=data["resultType"],
                result_count=len(data["result"]) if isinstance(data["result"], list) else 1,
                region=region_name)

    return result

@mcp.tool(
    description="Execute a PromQL range query with start time, end time, and step interval",
    annotations={
        "title": "Execute PromQL Range Query",
        "icon": "📈",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def execute_range_query(query: str, start: str, end: str, step: str, region: Optional[str] = None, ctx: Context | None = None) -> Dict[str, Any]:
    """Execute a range query against Prometheus.

    Args:
        query: PromQL query string
        start: Start time as RFC3339 or Unix timestamp
        end: End time as RFC3339 or Unix timestamp
        step: Query resolution step width (e.g., '15s', '1m', '1h')
        region: Optional region name (case-insensitive). If not specified, uses default region.

    Returns:
        Range query result with type (usually matrix) and values over time
    """
    params = {
        "query": query,
        "start": start,
        "end": end,
        "step": step
    }

    region_name = region.lower() if region else config.default_region
    logger.info("Executing range query", query=query, start=start, end=end, step=step, region=region_name)

    # Report progress if context available
    if ctx:
        await ctx.report_progress(progress=0, total=100, message="Initiating range query...")

    data = make_prometheus_request("query_range", params=params, region=region)

    # Report progress
    if ctx:
        await ctx.report_progress(progress=50, total=100, message="Processing query results...")

    result = {
        "resultType": data["resultType"],
        "result": data["result"],
        "region": region_name
    }

    if not config.disable_prometheus_links:
        from urllib.parse import urlencode
        region_normalized, region_config = get_region_config(region)
        ui_params = {
            "g0.expr": query,
            "g0.tab": "0",
            "g0.range_input": f"{start} to {end}",
            "g0.step_input": step
        }
        prometheus_ui_link = f"{region_config.url.rstrip('/')}/graph?{urlencode(ui_params)}"
        result["links"] = [{
            "href": prometheus_ui_link,
            "rel": "prometheus-ui",
            "title": "View in Prometheus UI"
        }]

    # Report completion
    if ctx:
        await ctx.report_progress(progress=100, total=100, message="Range query completed")

    logger.info("Range query completed",
                query=query,
                result_type=data["resultType"],
                result_count=len(data["result"]) if isinstance(data["result"], list) else 1,
                region=region_name)

    return result

@mcp.tool(
    description="List all available metrics in Prometheus with optional pagination support",
    annotations={
        "title": "List Available Metrics",
        "icon": "📋",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def list_metrics(
    limit: Optional[int] = None,
    offset: int = 0,
    filter_pattern: Optional[str] = None,
    region: Optional[str] = None,
    ctx: Context | None = None
) -> Dict[str, Any]:
    """Retrieve a list of all metric names available in Prometheus.

    Args:
        limit: Maximum number of metrics to return (default: all metrics)
        offset: Number of metrics to skip for pagination (default: 0)
        filter_pattern: Optional substring to filter metric names (case-insensitive)
        region: Optional region name (case-insensitive). If not specified, uses default region.

    Returns:
        Dictionary containing:
        - metrics: List of metric names
        - total_count: Total number of metrics (before pagination)
        - returned_count: Number of metrics returned
        - offset: Current offset
        - has_more: Whether more metrics are available
        - region: Region queried
    """
    region_name = region.lower() if region else config.default_region
    logger.info("Listing available metrics", limit=limit, offset=offset, filter_pattern=filter_pattern, region=region_name)

    # Report progress if context available
    if ctx:
        await ctx.report_progress(progress=0, total=100, message="Fetching metrics list...")

    data = make_prometheus_request("label/__name__/values", region=region)

    if ctx:
        await ctx.report_progress(progress=50, total=100, message=f"Processing {len(data)} metrics...")

    # Apply filter if provided
    if filter_pattern:
        filtered_data = [m for m in data if filter_pattern.lower() in m.lower()]
        logger.debug("Applied filter", original_count=len(data), filtered_count=len(filtered_data), pattern=filter_pattern, region=region_name)
        data = filtered_data

    total_count = len(data)

    # Apply pagination
    start_idx = offset
    end_idx = offset + limit if limit is not None else len(data)
    paginated_data = data[start_idx:end_idx]

    result = {
        "metrics": paginated_data,
        "total_count": total_count,
        "returned_count": len(paginated_data),
        "offset": offset,
        "has_more": end_idx < total_count,
        "region": region_name
    }

    if ctx:
        await ctx.report_progress(progress=100, total=100, message=f"Retrieved {len(paginated_data)} of {total_count} metrics")

    logger.info("Metrics list retrieved",
                total_count=total_count,
                returned_count=len(paginated_data),
                offset=offset,
                has_more=result["has_more"],
                region=region_name)

    return result

@mcp.tool(
    description="Get metadata for a specific metric",
    annotations={
        "title": "Get Metric Metadata",
        "icon": "ℹ️",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_metric_metadata(metric: str, region: Optional[str] = None) -> Dict[str, Any]:
    """Get metadata about a specific metric.

    Args:
        metric: The name of the metric to retrieve metadata for
        region: Optional region name (case-insensitive). If not specified, uses default region.

    Returns:
        Dictionary containing metadata entries for the metric and the region queried
    """
    region_name = region.lower() if region else config.default_region
    logger.info("Retrieving metric metadata", metric=metric, region=region_name)
    endpoint = f"metadata?metric={metric}"
    data = make_prometheus_request(endpoint, params=None, region=region)
    if "metadata" in data:
        metadata = data["metadata"]
    elif "data" in data:
        metadata = data["data"]
    else:
        metadata = data
    if isinstance(metadata, dict):
        metadata = [metadata]
    logger.info("Metric metadata retrieved", metric=metric, metadata_count=len(metadata), region=region_name)
    return {
        "metadata": metadata,
        "region": region_name
    }

@mcp.tool(
    description="Get information about all scrape targets",
    annotations={
        "title": "Get Scrape Targets",
        "icon": "🎯",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_targets(region: Optional[str] = None) -> Dict[str, Any]:
    """Get information about all Prometheus scrape targets.
    
    Args:
        region: Optional region name (case-insensitive). If not specified, uses default region.

    Returns:
        Dictionary with active and dropped targets information, and the region queried
    """
    region_name = region.lower() if region else config.default_region
    logger.info("Retrieving scrape targets information", region=region_name)
    data = make_prometheus_request("targets", region=region)
    
    result = {
        "activeTargets": data["activeTargets"],
        "droppedTargets": data["droppedTargets"],
        "region": region_name
    }
    
    logger.info("Scrape targets retrieved", 
                active_targets=len(data["activeTargets"]), 
                dropped_targets=len(data["droppedTargets"]),
                region=region_name)
    
    return result

if __name__ == "__main__":
    logger.info("Starting Prometheus MCP Server", mode="direct")
    mcp.run()
