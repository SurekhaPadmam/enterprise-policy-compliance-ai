"""Check that the Gemini API key in .env works with LangChain.

Run with: uv run test_api_key.py
"""
from agents.llm import create_llm


def main() -> None:
    try:
        response = create_llm().invoke("Reply with exactly: API key works.")
    except Exception as error:
        print(f"Gemini API request failed: {error.__class__.__name__}")
        print(f"Details: {error}")
        return

    print("API key works.")
    print(f"Model response: {response.content}")


if __name__ == "__main__":
    main()
