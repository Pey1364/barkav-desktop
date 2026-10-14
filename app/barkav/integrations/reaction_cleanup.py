from __future__ import annotations

import asyncio


def clear_group_reaction(token: str, chat_id: int, message_id: int) -> tuple[bool, str]:
    """Best-effort cleanup only. Financial DB changes must never depend on Telegram."""
    if not token:
        return False, 'BOT_TOKEN موجود نیست'
    try:
        from telegram import Bot
        from telegram.error import TelegramError
    except ModuleNotFoundError:
        return False, 'python-telegram-bot نصب نیست'

    async def _run():
        bot = Bot(token=token)
        try:
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[],
                read_timeout=20,
                write_timeout=20,
                connect_timeout=10,
                pool_timeout=10,
            )
            return True, 'OK'
        except TelegramError as exc:
            return False, f'{type(exc).__name__}: {exc}'
        finally:
            try:
                await bot.shutdown()
            except Exception:
                pass

    try:
        return asyncio.run(_run())
    except Exception as exc:
        return False, f'{type(exc).__name__}: {exc}'
