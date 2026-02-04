#!/usr/bin/env python
import sys
import dotenv
from prometheus_mcp_server.server import mcp, config, TransportType
from prometheus_mcp_server.logging_config import setup_logging

# Initialize structured logging
logger = setup_logging()

def setup_environment():
    if dotenv.load_dotenv():
        logger.info("Environment configuration loaded", source=".env file")
    else:
        logger.info("Environment configuration loaded", source="environment variables", note="No .env file found")

    # Prometheus URL is now optional - can be provided per-request
    if config.url:
        logger.info("Default Prometheus URL configured", url=config.url)
    else:
        logger.info(
            "No default Prometheus URL configured",
            note="Prometheus URL, username, and password must be provided with each tool call",
            mode="credential-free"
        )
    
    # MCP Server configuration validation
    mcp_config = config.mcp_server_config
    if mcp_config:
        if str(mcp_config.mcp_server_transport).lower() not in TransportType.values():
            logger.error(
                "Invalid mcp transport",
                error="PROMETHEUS_MCP_SERVER_TRANSPORT environment variable is invalid",
                suggestion="Please define one of these acceptable transports (http/sse/stdio)",
                example="http"
            )
            return False

        try:
            if mcp_config.mcp_bind_port:
                int(mcp_config.mcp_bind_port)
        except (TypeError, ValueError):
            logger.error(
                "Invalid mcp port",
                error="PROMETHEUS_MCP_BIND_PORT environment variable is invalid",
                suggestion="Please define an integer",
                example="8080"
            )
            return False
    
    # Determine authentication method for default credentials
    auth_method = "none (credential-free mode)"
    if config.username and config.password:
        auth_method = "basic_auth (default credentials configured)"
    elif config.token:
        auth_method = "bearer_token (default credentials configured)"
    
    logger.info(
        "Prometheus MCP Server configuration",
        default_server_url=config.url if config.url else "not configured",
        default_authentication=auth_method,
        org_id=config.org_id if config.org_id else None,
        mode="credential-free" if not config.url else "hybrid"
    )
    
    return True

def run_server():
    """Main entry point for the Prometheus MCP Server"""
    # Setup environment
    if not setup_environment():
        logger.error("Environment setup failed, exiting")
        sys.exit(1)
    
    mcp_config = config.mcp_server_config
    transport = mcp_config.mcp_server_transport

    http_transports = [TransportType.HTTP.value, TransportType.SSE.value]
    if transport in http_transports:
        mcp.run(transport=transport, host=mcp_config.mcp_bind_host, port=mcp_config.mcp_bind_port)
        logger.info("Starting Prometheus MCP Server", 
                transport=transport, 
                host=mcp_config.mcp_bind_host,
                port=mcp_config.mcp_bind_port)
    else:
        mcp.run(transport=transport)
        logger.info("Starting Prometheus MCP Server", transport=transport)

if __name__ == "__main__":
    run_server()
