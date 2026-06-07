import asyncio
import os
import sys

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

async def main():
    print("=== SnapSolve MCP Server Sanity Test (over stdio) ===")
    
    # Run the MCP server from the root of the workspace
    # Since this test script is in tests/sanity/, we need to resolve the root path
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    
    server_script = os.path.join(root_dir, "services", "mcp_server", "server.py")
    
    if not os.path.exists(server_script):
        print(f"Error: Could not find MCP server at {server_script}")
        sys.exit(1)

    print(f"Starting MCP server at: {server_script}")
    
    # We pass the root_dir as the cwd so that SessionManager finds the sessions/ directory
    env = os.environ.copy()
    env["PYTHONPATH"] = root_dir
    
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
        env=env
    )
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize the connection
                await session.initialize()
                print("Connection initialized successfully.\n")
                
                # Fetch available tools
                print("[1] Fetching available tools...")
                tools_response = await session.list_tools()
                
                # Depending on the MCP SDK version, tools might be in a different format
                # Let's extract tool names
                tool_names = [tool.name for tool in tools_response.tools]
                print(f"Available tools: {', '.join(tool_names)}")
                
                # Test list_sessions
                if "list_sessions" in tool_names:
                    print("\n[2] Testing tool: list_sessions...")
                    result = await session.call_tool("list_sessions", {"limit": 5})
                    # Content is usually a list of text content objects
                    for content in result.content:
                        if content.type == "text":
                            print("-" * 40)
                            print(content.text)
                            print("-" * 40)
                else:
                    print("Tool 'list_sessions' not found.")
                
                # Test get_tags
                if "get_tags" in tool_names:
                    print("\n[3] Testing tool: get_tags...")
                    result = await session.call_tool("get_tags", {})
                    for content in result.content:
                        if content.type == "text":
                            print("-" * 40)
                            print(content.text)
                            print("-" * 40)
                
                # Test search_sessions
                if "search_sessions" in tool_names:
                    print("\n[4] Testing tool: search_sessions...")
                    result = await session.call_tool("search_sessions", {"query": "Brazil", "limit": 3})
                    
                    found_session_id = None
                    for content in result.content:
                        if content.type == "text":
                            print("-" * 40)
                            print(content.text)
                            print("-" * 40)
                            # Extract an ID to test get_session
                            if "ID: " in content.text:
                                # Quick parse to grab the first ID
                                for line in content.text.split("\n"):
                                    if "ID: " in line:
                                        found_session_id = line.split("ID: ")[1].strip(")")
                                        break
                                        
                # Test get_session
                if "get_session" in tool_names and found_session_id:
                    print(f"\n[5] Testing tool: get_session for ID {found_session_id}...")
                    result = await session.call_tool("get_session", {"session_id": found_session_id})
                    for content in result.content:
                        if content.type == "text":
                            print("-" * 40)
                            # Truncate to avoid spamming the console too much, but show it works
                            text = content.text
                            print(text[:800] + ("\n... [TRUNCATED FOR TEST OUTPUT]" if len(text) > 800 else ""))
                            print("-" * 40)
                            
    except Exception as e:
        print(f"\n[!] Error during MCP communication: {e}")
        
    print("\n=== Sanity Test Complete ===")

if __name__ == "__main__":
    asyncio.run(main())
