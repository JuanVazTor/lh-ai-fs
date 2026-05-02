import os
from typing import TypeVar

from openai import OpenAI
from dotenv import load_dotenv
from pydantic import TypeAdapter

load_dotenv()

T = TypeVar("T")

_client: OpenAI | None = None


class LLMError(RuntimeError):
    pass


def is_llm_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def get_client() -> OpenAI:
    global _client
    if not is_llm_available():
        raise LLMError("OPENAI_API_KEY is not configured")
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


def call_llm(
    messages: list[dict],
    model: str = "gpt-4o",
    temperature: float = 0,
) -> str:
    """Call the OpenAI API and return the response content."""
    response = get_client().chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content


def call_llm_json(
    messages: list[dict],
    adapter: TypeAdapter[T],
    model: str | None = None,
    temperature: float = 0,
) -> T:
    """Call the LLM and validate a JSON object with a Pydantic TypeAdapter."""
    response = get_client().chat.completions.create(
        model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=messages,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    if not content:
        raise LLMError("LLM returned an empty response")
    try:
        return adapter.validate_json(content)
    except Exception as exc:  # noqa: BLE001 - surface validation failures as agent errors.
        raise LLMError(f"LLM JSON validation failed: {exc}") from exc
