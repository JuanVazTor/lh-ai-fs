import os
from typing import TypeVar

from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

T = TypeVar("T", bound=BaseModel)


def call_llm(
    messages: list[dict],
    model: str = "gpt-4o",
    temperature: float = 0,
) -> str:
    """Call the OpenAI API and return the response content."""
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content


def call_llm_structured(
    messages: list[dict],
    schema: type[T],
    model: str = "gpt-4o",
    temperature: float = 0,
) -> T:
    """Call the OpenAI API and parse the response into a Pydantic model.

    Uses the Responses/parse API (structured outputs) so the model is constrained
    to the given schema. This is how agents pass typed data — never raw text.
    """
    response = client.beta.chat.completions.parse(
        model=model,
        messages=messages,
        temperature=temperature,
        response_format=schema,
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise ValueError(f"Model returned no parseable {schema.__name__}")
    return parsed
