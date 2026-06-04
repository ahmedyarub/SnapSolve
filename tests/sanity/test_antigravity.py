"""Sanity test for the Google Antigravity SDK.

This script tests the SDK directly by:
1. Listing available Gemini models via the GenAI API.
2. Creating an Agent with LocalAgentConfig.
3. Sending a simple prompt and streaming the response.

This test must be run in WSL (Linux) since the SDK has no Windows wheel.

Prerequisites:
    export GEMINI_API_KEY="your_key"
    pip install google-antigravity google-genai

Usage:
    python tests/sanity/test_antigravity.py
    python tests/sanity/test_antigravity.py --prompt "List files in this directory"
    python tests/sanity/test_antigravity.py --model gemini-2.5-flash
"""

import argparse
import asyncio
import os
import sys
import time


def list_models() -> bool:
    """List available Gemini models via the GenAI API."""
    print("[1] Listing available models...")
    print("-" * 50)

    try:
        from google import genai
    except ImportError:
        print("✗ google-genai is not installed.")
        print("  Install it with: pip install google-genai")
        return False

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("✗ GEMINI_API_KEY environment variable not set.")
        return False

    try:
        client = genai.Client(api_key=api_key)
        models = client.models.list()

        count = 0
        for model in models:
            model_id = model.name.replace("models/", "")
            desc = getattr(model, "display_name", "") or ""
            print(f"  {model_id:<40} {desc}")
            count += 1

        print(f"\n✓ Found {count} models.")
        return True

    except Exception as e:
        print(f"✗ Error listing models: {e}")
        return False


async def test_agent(prompt: str, model: str = None) -> bool:
    """Create an Agent, send a prompt, and stream the response."""
    try:
        from google.antigravity import Agent, LocalAgentConfig
    except ImportError:
        print("✗ google-antigravity is not installed.")
        print("  Install it with: pip install google-antigravity")
        print("  Note: This only works on Linux/macOS (run in WSL on Windows).")
        return False

    step = "[2]" if not model else "[2]"
    model_label = model or "default"
    print(f"\n{step} Chat test (model={model_label})")
    print(f"Prompt: \"{prompt}\"")
    print("=" * 50)

    config_kwargs = {}
    if model:
        config_kwargs["model"] = model
    config = LocalAgentConfig(**config_kwargs)

    try:
        async with Agent(config) as agent:
            print(f"✓ Agent created successfully (model={model_label}).\n")

            start = time.time()
            response = await agent.chat(prompt)

            first_token_time = None
            chunks = []

            async for token in response:
                if first_token_time is None:
                    first_token_time = time.time()
                chunks.append(token)
                sys.stdout.write(token)
                sys.stdout.flush()

            elapsed = time.time() - start
            ttft = (first_token_time - start) if first_token_time else elapsed
            full_response = "".join(chunks)

            print("\n")
            print("=" * 50)
            print(f"Response length: {len(full_response)} chars")
            print(f"Time to first token: {ttft:.2f}s")
            print(f"Total time: {elapsed:.2f}s")

            if len(full_response) > 0:
                print("✓ Chat test passed!")
                return True
            else:
                print("✗ Empty response.")
                return False

    except Exception as e:
        print(f"\n✗ Agent error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Sanity test for Google Antigravity SDK")
    parser.add_argument("--prompt", default="Say hello in exactly 5 words.", help="Prompt to send")
    parser.add_argument("--model", default=None, help="Model ID to use (e.g. gemini-3.5-flash)")
    args = parser.parse_args()

    print("Antigravity SDK Sanity Test")
    print("-" * 50)

    models_ok = list_models()
    chat_ok = asyncio.run(test_agent(args.prompt, model=args.model))

    print("\n" + "=" * 50)
    if models_ok and chat_ok:
        print("✓ All tests passed!")
        sys.exit(0)
    else:
        print("✗ Some tests failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
