import os
from pathlib import Path

from dotenv import load_dotenv
from groq import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    Groq,
    RateLimitError,
)


ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def get_ai_response(system_prompt: str, prompt_text: str) -> str:
    """Request a JSON response from Groq without executing any changes."""
    load_dotenv(ENV_PATH)

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv(
        "GROQ_MODEL", "openai/gpt-oss-20b"
    ).strip()

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is missing. Add it to your local .env file."
        )

    if not model:
        raise RuntimeError("GROQ_MODEL cannot be empty.")

    try:
        with Groq(
            api_key=api_key,
            timeout=45.0,
            max_retries=1,
        ) as client:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt_text},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_completion_tokens=4096,
            )

    except AuthenticationError as exc:
        raise RuntimeError(
            "Groq rejected the API key. Check your local configuration."
        ) from exc

    except RateLimitError as exc:
        raise RuntimeError(
            "Groq's usage limit was reached. Wait and retry."
        ) from exc

    except APIConnectionError as exc:
        raise RuntimeError(
            "Could not reach Groq. Check your connection and retry."
        ) from exc

    except APIStatusError as exc:
        raise RuntimeError(
            f"Groq returned HTTP {exc.status_code}. "
            "Check model access and account availability."
        ) from exc

    choice = response.choices[0]

    if choice.finish_reason != "stop":
        raise RuntimeError(
            "Groq did not finish the plan. Try a simpler cleaning goal."
        )

    content = choice.message.content
    if not content:
        raise RuntimeError("Groq returned an empty response.")

    return content