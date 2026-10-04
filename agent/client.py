# agent/client.py
import os

# This file handles setting up your AI model client (e.g. Gemini or OpenAI)
def get_ai_response(prompt_text: str) -> str:
    """
    Sends the prompt to your LLM API and returns the text response.
    For now, this returns a mock response so you can test without an API key.
    """
    # Replace this mock logic with your actual API call when ready
    return "Mock AI response"