from .base_provider import BaseAPIProvider
import anthropic
import os
import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")


class AnthropicAPI(BaseAPIProvider):
    # IDs from https://docs.anthropic.com — Claude API (not Bedrock/Vertex IDs)
    MODELS = {
        "claude-opus-4-6": {
            "name": "Claude Opus 4.6",
            "provider": "Anthropic",
            "max_tokens": 8192,
        },
        "claude-sonnet-4-6": {
            "name": "Claude Sonnet 4.6",
            "provider": "Anthropic",
            "max_tokens": 8192,
        },
        "claude-haiku-4-5": {
            "name": "Claude Haiku 4.5",
            "provider": "Anthropic",
            "max_tokens": 8192,
        },
    }

    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")

    def set_model(self, model_name: str):
        if model_name not in self.MODELS.keys():
            raise ValueError("Invalid model")
        self.current_model = model_name

    def get_models(self) -> dict:
        if self.api_key is not None:
            return self.MODELS
        else:
            return {}

    def generate_response(self, prompt: str, system_content: str) -> str:
        logger.info(f"Generating response with model={self.current_model}, prompt_length={len(prompt)}")
        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            response = client.beta.messages.create(
                model=self.current_model,
                max_tokens=self.MODELS[self.current_model]["max_tokens"],
                system=system_content,
                messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
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
            logger.info(f"Response received: stop_reason={response.stop_reason}")
            text_blocks = [block.text for block in response.content if block.type == "text"]
            return text_blocks[-1] if text_blocks else ""
        except anthropic.APIConnectionError as e:
            logger.error(f"Server could not be reached: {e.__cause__}")
            raise e
        except anthropic.RateLimitError as e:
            logger.error(f"A 429 status code was received. {e}")
            raise e
        except anthropic.AuthenticationError as e:
            logger.error(f"There's an issue with your API key. {e}")
            raise e
        except anthropic.APIStatusError as e:
            logger.error(f"Another non-200-range status code was received: {e.status_code}")
            raise e
