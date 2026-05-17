"""
DharmaGPT MCP Server

Exposes DharmaGPT's RAG pipeline as Model Context Protocol tools so any
MCP-compatible client (Claude Desktop, Cursor, Zed, etc.) can query
India's sacred texts with full citation grounding.

Usage:
  # stdio — for Claude Desktop / local MCP clients
  python mcp_server.py

  # HTTP — for hosted / remote MCP access
  python mcp_server.py --transport streamable-http --port 8001

Claude Desktop config (~/.claude/claude_desktop_config.json):
  {
    "mcpServers": {
      "dharmagpt": {
        "command": "python",
        "args": ["/path/to/dharmagpt/mcp_server.py"],
        "env": { "PYTHONPATH": "/path/to/dharmagpt" }
      }
    }
  }
"""

import argparse
import asyncio
from typing import Literal

from mcp.server.fastmcp import FastMCP

from core.rag_engine import answer
from models.schemas import QueryMode, QueryRequest

mcp = FastMCP(
    name="DharmaGPT",
    instructions=(
        "DharmaGPT answers questions grounded in India's sacred texts — "
        "the Ramayana, Mahabharata, Bhagavad Gita, Upanishads, and Puranas. "
        "Every response includes inline citations traceable to the source passage. "
        "Use ask_dharma for life questions, guidance, scholarly lookup, or storytelling."
    ),
)


def _format_sources(sources) -> str:
    if not sources:
        return ""
    lines = ["\n\n---\n**Sources**"]
    for i, s in enumerate(sources, 1):
        lines.append(f"[{i}] {s.citation}")
        if s.url:
            lines.append(f"    {s.url}")
    return "\n".join(lines)


@mcp.tool()
async def ask_dharma(
    question: str,
    mode: Literal["guidance", "scholar", "story", "children"] = "guidance",
) -> str:
    """
    Ask a question grounded in India's sacred texts.

    Returns a cited answer with inline verse references drawn from the
    Ramayana, Mahabharata, Bhagavad Gita, Upanishads, and Puranas.

    Modes:
    - guidance  : Life questions, emotional support, dharmic wisdom (default)
    - scholar   : Academic analysis with IAST citations and structured headers
    - story     : Narrative retelling accurate to the source chapter and verse
    - children  : Age-appropriate stories with a clear moral lesson
    """
    request = QueryRequest(query=question, mode=QueryMode(mode))
    result = await answer(request)
    return result.answer + _format_sources(result.sources)


@mcp.tool()
async def search_scripture(
    query: str,
    section: str | None = None,
) -> str:
    """
    Search for passages across India's sacred texts using semantic similarity.

    Optionally filter by section (e.g. 'Sundara Kanda', 'Bhagavad Gita',
    'Adi Parva', 'Chandogya Upanishad').

    Returns the top matching passages with full citation metadata.
    """
    request = QueryRequest(
        query=query,
        mode=QueryMode.scholar,
        filter_section=section,
    )
    result = await answer(request)

    if not result.sources:
        return "No passages found for that query."

    lines = [f"**{len(result.sources)} passage(s) found**\n"]
    for i, s in enumerate(result.sources, 1):
        lines.append(f"**[{i}] {s.citation}** (score: {s.score:.3f})")
        lines.append(s.text[:400] + ("…" if len(s.text) > 400 else ""))
        if s.url:
            lines.append(f"Source: {s.url}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DharmaGPT MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport type (default: stdio for local Claude Desktop use)",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    if args.transport == "streamable-http":
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")
