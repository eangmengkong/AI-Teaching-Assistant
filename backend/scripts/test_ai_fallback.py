"""
Offline sanity check for the AI provider fallback chain (app/core/ai_providers.py).

Run from the backend folder:
    venv\\Scripts\\activate
    python scripts/test_ai_fallback.py

No real API keys are needed — provider failures are simulated.
"""
import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.core.ai_providers as aip


async def test_all_fail():
    """Both providers point at a dead local port -> the chain must try both in order."""
    os.environ["AI_FALLBACK_1_API_KEY"] = "test-key-1"
    os.environ["AI_FALLBACK_1_MODEL"] = "test-model-1"
    os.environ["AI_FALLBACK_1_BASE_URL"] = "http://127.0.0.1:9/v1"
    os.environ["AI_FALLBACK_2_API_KEY"] = "test-key-2"
    os.environ["AI_FALLBACK_2_MODEL"] = "test-model-2"
    os.environ["AI_FALLBACK_2_BASE_URL"] = "http://127.0.0.1:9/v1"

    chain = aip.get_provider_chain()
    names = [(p.name, p.model) for p in chain]
    print("chain:", names)
    # The .env primary key is still the unfilled placeholder, so it must be skipped.
    assert [n for n, _ in names] == ["fallback_1", "fallback_2"], names

    aip.reset_cooldowns()
    resp, info = await aip.chat_with_fallback(messages=[{"role": "user", "content": "hi"}])
    assert resp is None, "expected total failure with dead endpoints"
    print("all-fail summary:", info)
    assert "fallback_1" in info and "fallback_2" in info
    print("PASS: chain tried both providers in order")


async def test_first_success_wins():
    """Provider 1 raises a simulated 429 -> provider 2 must answer automatically."""
    calls = {"n": 0}

    class _Msg:
        function_call = None
        content = "Hello from the fallback provider!"

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    class _Completions:
        async def create(self, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("429 Rate limit reached (simulated)")
            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Client:
        def __init__(self, api_key=None, base_url=None, timeout=None):
            self.chat = _Chat()

    aip.reset_cooldowns()
    aip.openai = SimpleNamespace(AsyncOpenAI=_Client)

    resp, info = await aip.chat_with_fallback(messages=[{"role": "user", "content": "hi"}])
    assert resp is not None, info
    assert resp.choices[0].message.content == "Hello from the fallback provider!", info
    assert info == "fallback_2", info
    assert calls["n"] == 2, calls
    print("PASS: provider 1 failed (429) -> provider 2 answered automatically")


async def main():
    # Force the placeholder-primary behavior so this offline test is
    # deterministic regardless of what real keys are in backend/.env.
    aip.settings.OPENAI_API_KEY = "sk-proj-your-openai-api-key-here"
    await test_all_fail()
    await test_first_success_wins()
    print("\nAll fallback-chain tests passed")


if __name__ == "__main__":
    asyncio.run(main())