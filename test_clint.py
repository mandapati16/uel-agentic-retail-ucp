import asyncio
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(
        command="python",
        args=["server.py"],
        env=os.environ.copy(),  # <-- pass GCP_PROJECT etc. through explicitly
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Available tools:", [t.name for t in tools.tools])

            result = await session.call_tool("get_sku", {"product_id": "PBOO0007"})
            print("get_sku result:", result)

asyncio.run(main())
