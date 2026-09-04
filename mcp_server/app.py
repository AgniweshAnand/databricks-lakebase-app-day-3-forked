"""
Databricks App entry point for Movie Night Planner MCP Server.
"""
from movie_mcp_server import mcp

# FastMCP provides __call__ for ASGI compatibility
app = mcp
