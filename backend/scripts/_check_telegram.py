"""Feed a fake '/start' through handle_update in a fresh process (exactly like
real polling: one session per update). No prior DB session is held."""
import asyncio
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.chdir(BASE)

import app.telegram.bot as bot_mod


async def _noop_send(chat_id: str, text: str, *args, **kwargs):
    print(f"[would-send to {chat_id}] {text[:50]}...")
    return True


async def main():
    bot_mod.CentralAgentTools.send_telegram_message = _noop_send
    update = {"message": {"chat": {"id": 703281574}, "text": "/start"}}
    result = await bot_mod.TelegramBotHandler.handle_update(update)
    assert result == "OK", result
    print("\nPASS: /start built the command list and delivered it (no closed-session / multiple-rows error")


if __name__ == "__main__":
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())