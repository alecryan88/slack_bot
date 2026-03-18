import os

import anthropic

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

SYSTEM_PROMPT = """You are a helpful GitHub assistant in a Slack thread. \
You have access to GitHub tools connected to an authenticated token. \
Never ask the user for their GitHub username or any credentials — \
you can list and search their repositories directly using the authenticated user endpoints. \
When asked about "my repos" or "my projects", immediately call the appropriate \
GitHub tool without any preamble or announcement. \
Never say what you are about to do — just do it and return the result."""


def call_llm(messages: list) -> str:
    client = anthropic.Anthropic()

    response = client.beta.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=messages,
        mcp_servers=[
            {
                "type": "url",
                "url": "https://api.githubcopilot.com/mcp/",
                "name": "github",
                "authorization_token": GITHUB_TOKEN,
            }
        ],
        tools=[
            {
                "type": "mcp_toolset",
                "mcp_server_name": "github",
            }
        ],
        betas=["mcp-client-2025-11-20"],
    )

    print("RESPONSE BLOCKS:", [(b.type, b.text[:50] if hasattr(b, "text") else "") for b in response.content])
    print("STOP REASON:", response.stop_reason)
    text_blocks = [block.text for block in response.content if block.type == "text"]
    return text_blocks[-1] if text_blocks else ""
