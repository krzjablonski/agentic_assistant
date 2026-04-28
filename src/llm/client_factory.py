from llm.openai_compatible_client import OpenAICompatibleClient
from llm.anthropic_client import AnthropicClient
from llm.gemini_client import GeminiClient
from config_service import config_service


def create_client(client_type: str, config: dict):
    if client_type == "OpenAI":
        return OpenAICompatibleClient(
            base_url="https://api.openai.com/v1",
            model=config["model"],
            api_key=config_service.get("llm.openai_api_key") or "",
        )
    elif client_type == "Anthropic":
        return AnthropicClient(model=config["model"])
    elif client_type == "Google Gemini":
        return GeminiClient(
            model=config["model"],
            api_key=config_service.get("llm.google_gemini_api_key") or "",
        )
    else:  # Local
        return OpenAICompatibleClient(
            base_url=config["base_url"],
            model=config["model"],
            api_key="ollama",
            context_window=config.get("context_window"),
        )
