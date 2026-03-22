from typing import List, Optional

from ..ai_constants import DEFAULT_SYSTEM_CONTENT
from .anthropic import AnthropicAPI

MODEL = "claude-sonnet-4-6"


def get_provider_response(
    user_id: str,
    prompt: str,
    context: Optional[List] = [],
    system_content=DEFAULT_SYSTEM_CONTENT,
):
    formatted_context = "\n".join([f"{msg['user']}: {msg['text']}" for msg in context])
    full_prompt = f"Prompt: {prompt}\nContext: {formatted_context}"
    provider = AnthropicAPI()
    provider.set_model(MODEL)
    return provider.generate_response(full_prompt, system_content)
