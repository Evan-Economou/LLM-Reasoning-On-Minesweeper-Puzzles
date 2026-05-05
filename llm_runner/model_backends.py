from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ChatModelConfig:
    provider: str = "ollama"
    model_id: str = "llama3.2:3b"
    base_url: str = ""
    api_key: str | None = None
    timeout_seconds: float = 120.0
    max_new_tokens: int = 32
    temperature: float = 0.0
    top_p: float = 1.0
    repetition_penalty: float = 1.12
    no_repeat_ngram_size: int = 4


class ChatBackend(Protocol):
    provider_name: str
    model_id: str

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        raise NotImplementedError


def create_chat_backend(config: ChatModelConfig) -> ChatBackend:
    provider = config.provider.strip().lower()
    if provider == "ollama":
        return OllamaChatBackend(config)
    if provider == "openai":
        return OpenAIChatBackend(config)
    if provider == "anthropic":
        return AnthropicChatBackend(config)
    raise ValueError(f"Unsupported model provider: {config.provider!r}")


def _message_payload(messages: Sequence[ChatMessage]) -> list[dict[str, str]]:
    return [{"role": message.role, "content": message.content} for message in messages]


def _split_system_messages(messages: Sequence[ChatMessage]) -> tuple[str, list[dict[str, str]]]:
    system_parts: list[str] = []
    chat_messages: list[dict[str, str]] = []
    for message in messages:
        if message.role == "system":
            system_parts.append(message.content)
        else:
            chat_messages.append({"role": message.role, "content": message.content})
    return "\n\n".join(system_parts), chat_messages


class OllamaChatBackend:
    provider_name = "ollama"

    def __init__(self, config: ChatModelConfig) -> None:
        self.config = config
        self.model_id = config.model_id
        self.base_url = config.base_url or "http://localhost:11434"

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        payload = {
            "model": self.model_id,
            "messages": _message_payload(messages),
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
                "num_predict": self.config.max_new_tokens,
                "repeat_penalty": self.config.repetition_penalty,
                "repeat_last_n": self.config.no_repeat_ngram_size,
            },
        }
        request = Request(
            f"{self.base_url.rstrip('/')}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if self.config.api_key:
            request.add_header("Authorization", f"Bearer {self.config.api_key}")
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise RuntimeError(
                f"Ollama request failed with HTTP {exc.code} for model {self.model_id}: {error_body or exc.reason}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                f"Could not reach Ollama at {self.base_url!r}: {exc.reason}"
            ) from exc

        data = json.loads(raw)
        message = data.get("message") or {}
        content = message.get("content", "")
        if not content.strip():
            raise RuntimeError(f"Ollama returned an empty message for model {self.model_id}")
        return content.strip()


class AnthropicChatBackend:
    provider_name = "anthropic"

    def __init__(self, config: ChatModelConfig) -> None:
        self.config = config
        self.model_id = config.model_id
        try:
            from anthropic import Anthropic
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "anthropic is required for the Anthropic backend. Install it with: pip install anthropic"
            ) from exc

        self._client = Anthropic(api_key=config.api_key)

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        system_prompt, chat_messages = _split_system_messages(messages)
        request_kwargs = {
            "model": self.model_id,
            "messages": chat_messages,
            "max_tokens": max(1, self.config.max_new_tokens),
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
        }
        if system_prompt:
            request_kwargs["system"] = system_prompt
        response = self._client.messages.create(**request_kwargs)
        content_parts = [part.text for part in response.content if hasattr(part, "text")]
        content = "".join(content_parts).strip()
        if not content:
            raise RuntimeError(f"Anthropic returned an empty message for model {self.model_id}")
        return content