import asyncio
import os
from typing import List, Optional

from agents import Agent, Runner
from agents.mcp import MCPServerStreamableHttp
from agents.model_settings import ModelSettings

from .constants import DEFAULT_SYSTEM_CONTENT

MODEL = "gpt-4o-mini"


def get_response(
    prompt: str,
    context: Optional[List[dict]] = None,
    system_content: str = DEFAULT_SYSTEM_CONTENT,
) -> str:
    formatted_context = "\n".join(
        [f"{msg['user']}: {msg['text']}" for msg in (context or [])]
    )
    full_prompt = f"Prompt: {prompt}\nContext: {formatted_context}"
    return asyncio.run(_run_agent(full_prompt, system_content))


async def _run_agent(prompt: str, system_content: str) -> str:
    async with MCPServerStreamableHttp(
        name="GitHub MCP",
        params={
            "url": "https://api.githubcopilot.com/mcp/",
            "headers": {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"},
            "timeout": 10,
        },
    ) as server:
        agent = Agent(
            name="Github Agent",
            instructions=system_content,
            mcp_servers=[server],
            model=MODEL,
            model_settings=ModelSettings(tool_choice="required"),
        )
        result = await Runner.run(agent, prompt, max_turns=50)
        return result.final_output
