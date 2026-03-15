import asyncio
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from anzen.bot import anzen_bot

BOT_TOKEN = os.getenv("BOT_TOKEN")

if __name__ == "__main__":
    anzen_bot.run(BOT_TOKEN)
