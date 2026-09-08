"""
Live check of every configured AI provider (reads keys from backend/.env).

Run from the backend folder:
    venv\\Scripts\\activate
    python scripts/test_ai_live.py

Sends one tiny ("Say OK") request per provider so you can see which keys work.
"""
import asyncio
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)  # so backend/.env is found

import openai  # noqa: E402


async def main():
    from app.core.ai_providers import get_provider_chain, reset_cooldowns

    reset_cooldowns()
    chain = get_provider_chain()
    print("Configured providers (in order):")
    for p in chain:
        print(f"  - {p.name}: model={p.model} base_url={p.base_url}")
    print()

    for p in chain:
        try:
            client = openai.AsyncOpenAI(api_key=p.api_key, base_url=p.base_url, timeout=120)
            r = await client.chat.completions.create(
                model=p.model,
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=200,
            )
            print(f"[OK]   {p.name} ({p.model}) -> {r.choices[0].message.content!r}")
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] {p.name} ({p.model}) -> {type(e).__name__}: {str(e)[:200]}")


if __name__ == "__main__":
    asyncio.run(main())