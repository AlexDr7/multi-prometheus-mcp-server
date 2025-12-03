"""Tests for multi-region functionality."""

import pytest
import json
from unittest.mock import patch, MagicMock
from fastmcp import Client
from prometheus_mcp_server.server import (
    mcp, config, RegionConfig, get_region_config, 
    execute_query, health_check
)

@pytest.fixture
def setup_multi_regions():
    """Setup multiple test regions in the configuration."""
    # Save original regions
    original_regions = config.regions.copy()
    original_default = config.default_region
    
    # Setup test regions
    config.regions = {
        "atl": RegionConfig(
            url="http://atl.example.com:9090",
            url_ssl_verify=True,
            username="",
            password="",
            token="",
            custom_headers=None
        ),
        "blr": RegionConfig(
            url="http://blr.example.com:9090",
            url_ssl_verify=True,
            username="",
            password="",
            token="token123",
            custom_headers={"X-Custom": "blr-value"}
        ),
        "wdc": RegionConfig(
            url="http://wdc.example.com:9090",
            url_ssl_verify=False,
            username="admin",
            password="pass",
            token="",
            custom_headers=None
        )
    }
    config.default_region = "atl"
    
    yield
    
    # Restore original configuration
    config.regions = original_regions
    config.default_region = original_default


def test_get_region_config_default(setup_multi_regions):
    """Test get_region_config with default region."""
    region_name, region_config = get_region_config(None)
    assert region_name == "atl"
    assert region_config.url == "http://atl.example.com:9090"


def test_get_region_config_specific(setup_multi_regions):
    """Test get_region_config with specific region."""
    region_name, region_config = get_region_config("blr")
    assert region_name == "blr"
    assert region_config.url == "http://blr.example.com:9090"
    assert region_config.token == "token123"


def test_get_region_config_case_insensitive(setup_multi_regions):
    """Test get_region_config is case-insensitive."""
    region_name1, config1 = get_region_config("ATL")
    region_name2, config2 = get_region_config("atl")
    region_name3, config3 = get_region_config("AtL")
    
    assert region_name1 == region_name2 == region_name3 == "atl"
    assert config1 == config2 == config3


def test_get_region_config_invalid_region(setup_multi_regions):
    """Test get_region_config with invalid region."""
    with pytest.raises(ValueError, match="Region 'invalid' is not configured"):
        get_region_config("invalid")


@pytest.mark.asyncio
async def test_execute_query_with_region(setup_multi_regions):
    """Test execute_query with specific region."""
    with patch("prometheus_mcp_server.server.make_prometheus_request") as mock_request:
        mock_request.return_value = {
            "resultType": "vector",
            "result": [{"metric": {"__name__": "up"}, "value": [1617898448.214, "1"]}]
        }
        
        async with Client(mcp) as client:
            result = await client.call_tool("execute_query", {"query": "up", "region": "blr"})
            
            # Verify the request was made to the BLR region
            mock_request.assert_called_once_with("query", params={"query": "up"}, region="blr")
            assert result.data["region"] == "blr"


@pytest.mark.asyncio
async def test_execute_query_default_region(setup_multi_regions):
    """Test execute_query without specifying region uses default."""
    with patch("prometheus_mcp_server.server.make_prometheus_request") as mock_request:
        mock_request.return_value = {
            "resultType": "vector",
            "result": [{"metric": {"__name__": "up"}, "value": [1617898448.214, "1"]}]
        }
        
        async with Client(mcp) as client:
            result = await client.call_tool("execute_query", {"query": "up"})
            
            # Verify the request was made with no region specified (will use default)
            mock_request.assert_called_once_with("query", params={"query": "up"}, region=None)
            # The tool should return the default region
            assert result.data["region"] == "atl"


@pytest.mark.asyncio
async def test_health_check_all_regions(setup_multi_regions):
    """Test health_check without region checks all regions."""
    with patch("prometheus_mcp_server.server.make_prometheus_request") as mock_request:
        # Mock successful responses
        mock_request.return_value = {"resultType": "vector", "result": []}
        
        async with Client(mcp) as client:
            result = await client.call_tool("health_check", {})
            
            # Should have checked all three regions
            assert "regions" in result.data
            assert len(result.data["regions"]) == 3
            assert "atl" in result.data["regions"]
            assert "blr" in result.data["regions"]
            assert "wdc" in result.data["regions"]
            
            # All should be healthy
            assert result.data["regions"]["atl"]["prometheus_connectivity"] == "healthy"
            assert result.data["regions"]["blr"]["prometheus_connectivity"] == "healthy"
            assert result.data["regions"]["wdc"]["prometheus_connectivity"] == "healthy"


@pytest.mark.asyncio
async def test_health_check_specific_region(setup_multi_regions):
    """Test health_check with specific region."""
    with patch("prometheus_mcp_server.server.make_prometheus_request") as mock_request:
        mock_request.return_value = {"resultType": "vector", "result": []}
        
        async with Client(mcp) as client:
            result = await client.call_tool("health_check", {"region": "blr"})
            
            # Should only check the specified region
            assert "region" in result.data
            assert result.data["region"] == "blr"
            assert result.data["prometheus_connectivity"] == "healthy"
            # Should not have a "regions" key when checking specific region
            assert "regions" not in result.data


@pytest.mark.asyncio
async def test_health_check_degraded_region(setup_multi_regions):
    """Test health_check when one region is degraded."""
    with patch("prometheus_mcp_server.server.make_prometheus_request") as mock_request:
        # Mock BLR region failing
        def side_effect(endpoint, params, region):
            if region == "blr":
                raise ConnectionError("Connection refused")
            return {"resultType": "vector", "result": []}
        
        mock_request.side_effect = side_effect
        
        async with Client(mcp) as client:
            result = await client.call_tool("health_check", {})
            
            # Should have degraded status
            assert result.data["status"] == "degraded"
            assert result.data["regions"]["atl"]["prometheus_connectivity"] == "healthy"
            assert result.data["regions"]["blr"]["prometheus_connectivity"] == "degraded"
            assert "prometheus_error" in result.data["regions"]["blr"]
            assert result.data["regions"]["wdc"]["prometheus_connectivity"] == "healthy"


@pytest.mark.asyncio
async def test_list_metrics_with_region(setup_multi_regions):
    """Test list_metrics with specific region."""
    with patch("prometheus_mcp_server.server.make_prometheus_request") as mock_request:
        mock_request.return_value = ["up", "go_goroutines", "http_requests_total"]
        
        async with Client(mcp) as client:
            result = await client.call_tool("list_metrics", {"region": "wdc"})
            
            mock_request.assert_called_once_with("label/__name__/values", region="wdc")
            assert result.data["region"] == "wdc"
            assert result.data["total_count"] == 3


@pytest.mark.asyncio
async def test_get_targets_with_region(setup_multi_regions):
    """Test get_targets with specific region."""
    with patch("prometheus_mcp_server.server.make_prometheus_request") as mock_request:
        mock_request.return_value = {
            "activeTargets": [{"health": "up"}],
            "droppedTargets": []
        }
        
        async with Client(mcp) as client:
            result = await client.call_tool("get_targets", {"region": "atl"})
            
            payload = result.content[0].text
            json_data = json.loads(payload)
            
            mock_request.assert_called_once_with("targets", region="atl")
            assert json_data["region"] == "atl"


@pytest.mark.asyncio
async def test_execute_range_query_with_region(setup_multi_regions):
    """Test execute_range_query with specific region."""
    with patch("prometheus_mcp_server.server.make_prometheus_request") as mock_request:
        mock_request.return_value = {
            "resultType": "matrix",
            "result": [{"metric": {"__name__": "up"}, "values": [[1617898400, "1"]]}]
        }
        
        async with Client(mcp) as client:
            result = await client.call_tool("execute_range_query", {
                "query": "up",
                "start": "2023-01-01T00:00:00Z",
                "end": "2023-01-01T01:00:00Z",
                "step": "15s",
                "region": "blr"
            })
            
            mock_request.assert_called_once()
            assert result.data["region"] == "blr"


@pytest.mark.asyncio
async def test_get_metric_metadata_with_region(setup_multi_regions):
    """Test get_metric_metadata with specific region."""
    with patch("prometheus_mcp_server.server.make_prometheus_request") as mock_request:
        mock_request.return_value = {
            "data": [{"metric": "up", "type": "gauge"}]
        }
        
        async with Client(mcp) as client:
            result = await client.call_tool("get_metric_metadata", {
                "metric": "up",
                "region": "wdc"
            })
            
            payload = result.content[0].text
            json_data = json.loads(payload)
            
            mock_request.assert_called_once_with("metadata?metric=up", params=None, region="wdc")
            assert json_data["region"] == "wdc"
