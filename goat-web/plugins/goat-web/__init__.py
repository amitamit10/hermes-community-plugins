"""Hermes directory-plugin wrapper for the GOAT web tools."""

import json

from .goat_tools import register as goat_handlers


_TOOL_SPECS = {
    "goat_search": {
        "description": "Search public web results with bounded output.",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "max_results": {"type": "integer", "description": "Maximum results, capped at 5."},
        },
        "required": ["query"],
    },
    "goat_extract": {
        "description": "Fetch one public HTTPS page and return bounded content.",
        "properties": {"url": {"type": "string", "description": "Public HTTPS URL."}},
        "required": ["url"],
    },
    "goat_crawl": {
        "description": "Crawl same-origin public HTTPS pages within fixed bounds.",
        "properties": {"url": {"type": "string", "description": "Public HTTPS start URL."}},
        "required": ["url"],
    },
    "goat_probe": {
        "description": "Check a public HTTPS URL and return status and host.",
        "properties": {"url": {"type": "string", "description": "Public HTTPS URL."}},
        "required": ["url"],
    },
}


def _json_handler(handler):
    def call(args, **_kwargs):
        return json.dumps(handler(**(args or {})), ensure_ascii=False)

    return call


def register(ctx):
    """Register the four public GOAT tools with the Hermes plugin context."""
    handlers = goat_handlers()
    for name, handler in handlers.items():
        spec = _TOOL_SPECS[name]
        schema = {
            "name": name,
            "description": spec["description"],
            "parameters": {
                "type": "object",
                "properties": spec["properties"],
                "required": spec["required"],
            },
        }
        ctx.register_tool(
            name=name,
            toolset="goat_web",
            schema=schema,
            handler=_json_handler(handler),
            description=spec["description"],
        )
