"""Hermes directory-plugin wrapper for the GOAT web tools."""

import json

from .goat_tools import (
    MAX_CRAWL_DEPTH,
    MAX_CRAWL_PAGES,
    MAX_RESULTS,
    map_error,
    register as goat_handlers,
)


_TOOL_SPECS = {
    "goat_search": {
        "description": "Search public web results with bounded output.",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "max_results": {
                "type": "integer",
                "description": f"Maximum results (1..{MAX_RESULTS}); non-integers use the default of {MAX_RESULTS}.",
                "minimum": 1,
                "maximum": MAX_RESULTS,
                "default": MAX_RESULTS,
            },
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
        "properties": {
            "url": {"type": "string", "description": "Public HTTPS start URL."},
            "max_depth": {
                "type": "integer",
                "description": f"Maximum crawl depth (0..{MAX_CRAWL_DEPTH}).",
                "minimum": 0,
                "maximum": MAX_CRAWL_DEPTH,
                "default": MAX_CRAWL_DEPTH,
            },
            "max_pages": {
                "type": "integer",
                "description": f"Maximum pages to visit (1..{MAX_CRAWL_PAGES}).",
                "minimum": 1,
                "maximum": MAX_CRAWL_PAGES,
                "default": MAX_CRAWL_PAGES,
            },
        },
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
        try:
            return json.dumps(handler(**(args or {})), ensure_ascii=False)
        except Exception as error:
            return json.dumps({"error": {"code": map_error(error)}}, ensure_ascii=False)

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
                "additionalProperties": False,
            },
        }
        ctx.register_tool(
            name=name,
            toolset="goat_web",
            schema=schema,
            handler=_json_handler(handler),
            description=spec["description"],
        )
