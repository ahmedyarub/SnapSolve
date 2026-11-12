import builtins
import logging
import os
import sys

# Monkey-patch print to write to stderr, preventing accidental output
# from corrupting the MCP stdio JSON-RPC protocol
_original_print = builtins.print


def _stderr_print(*args, **kwargs):
    kwargs["file"] = sys.stderr
    _original_print(*args, **kwargs)


builtins.print = _stderr_print

from mcp.server.fastmcp import FastMCP  # noqa: E402

# Ensure the parent directory (SnapSolve root) is in the path
# This allows importing from core and config
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, root_dir)
os.chdir(root_dir)

from core.sessions import store  # noqa: E402

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP Server
mcp = FastMCP("SnapSolve MCP Server")


def _read_transcription(session_id: str) -> str | None:
    """The session's transcript, or None if it has none."""
    path = store.session_transcription_path(session_id)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


@mcp.tool()
def list_sessions(limit: int = 20, offset: int = 0) -> str:
    """
    List lightweight metadata for recent SnapSolve sessions.

    Args:
        limit: Maximum number of sessions to return.
        offset: Number of sessions to skip.

    Returns:
        A formatted string detailing the recent sessions.
    """
    sessions = store.list_sessions()  # newest first

    results = sessions[offset : offset + limit]
    if not results:
        return "No sessions found."

    output = [f"Found {len(results)} sessions (total: {len(sessions)}):"]
    for s in results:
        s_id = s.get("id")
        name = s.get("name") or s.get("title") or s_id
        tags = ", ".join(s.get("tags", []))
        interaction_count = s.get("interaction_count", 0)
        output.append(f"- ID: {s_id}")
        output.append(f"  Name: {name}")
        output.append(f"  Tags: {tags if tags else 'None'}")
        output.append(f"  Interactions: {interaction_count}")
        output.append("")

    return "\n".join(output)


@mcp.tool()
def get_session(session_id: str) -> str:
    """
    Get full details and interaction history of a specific SnapSolve session.

    Args:
        session_id: The UUID of the session to retrieve.

    Returns:
        A formatted string containing the session's history and details.
    """
    session_data = store.read_session(session_id)

    if not session_data:
        return f"Session with ID '{session_id}' not found."

    name = session_data.get("name") or session_data.get("title") or session_id
    tags = ", ".join(session_data.get("tags", []))
    history = session_data.get("history", [])

    output = [
        f"Session: {name}",
        f"ID: {session_id}",
        f"Tags: {tags if tags else 'None'}",
        "",
        "History:",
    ]

    if not history:
        output.append("No interactions in this session.")
    else:
        for idx, interaction in enumerate(history):
            output.append(f"--- Interaction {idx + 1} ---")
            prompt = interaction.get("prompt", "")
            response = interaction.get("response", "")
            extracted = interaction.get("extracted_text", "")

            if prompt:
                output.append(f"User Prompt:\n{prompt}\n")
            if extracted:
                output.append(f"Extracted Text/Context:\n{extracted}\n")
            if response:
                output.append(f"AI Response:\n{response}\n")

    # Append full transcription if available
    transcription = _read_transcription(session_id)
    if transcription:
        output.append("--- Full Transcription ---")
        output.append(transcription)

    return "\n".join(output)


@mcp.tool()
def search_sessions(query: str, limit: int = 10) -> str:
    """
    Search for SnapSolve sessions containing the given text query.

    Args:
        query: The text to search for within prompts, responses, or transcriptions.
        limit: Maximum number of matching sessions to return.

    Returns:
        A formatted string of matching sessions.
    """
    # We will use simple text matching over history to avoid requiring embeddings
    # for the basic MCP search, which is faster and easier for generic text search.
    sessions = store.list_sessions()  # newest first

    q_lower = query.lower()
    matches = []

    for s in sessions:
        s_id = s.get("id")
        session_data = store.read_session(s_id)
        if not session_data:
            continue

        history = session_data.get("history", [])
        found = False

        # Check name and tags
        name = session_data.get("name") or session_data.get("title") or ""
        if q_lower in name.lower() or any(
            q_lower in tag.lower() for tag in session_data.get("tags", [])
        ):
            found = True

        # Check history
        if not found:
            for interaction in history:
                fields = (
                    interaction.get("prompt"),
                    interaction.get("response"),
                    interaction.get("extracted_text"),
                )
                if any(f and q_lower in f.lower() for f in fields):
                    found = True
                    break

        # Check transcription
        if not found:
            transcription = _read_transcription(s_id)
            if transcription and q_lower in transcription.lower():
                found = True

        if found:
            matches.append(s)
            if len(matches) >= limit:
                break

    if not matches:
        return f"No sessions found matching query: '{query}'"

    output = [f"Found {len(matches)} matching sessions:"]
    for s in matches:
        s_id = s.get("id")
        name = s.get("name") or s.get("title") or s_id
        output.append(f"- {name} (ID: {s_id})")

    return "\n".join(output)


@mcp.tool()
def get_tags() -> str:
    """
    Get a list of all unique tags used across SnapSolve sessions.

    Returns:
        A comma-separated list of tags.
    """
    sessions = store.list_sessions()

    all_tags = set()
    for s in sessions:
        for tag in s.get("tags", []):
            all_tags.add(tag)

    if not all_tags:
        return "No tags found."

    return "Available tags: " + ", ".join(sorted(all_tags))


if __name__ == "__main__":
    mcp.run(transport="stdio")
