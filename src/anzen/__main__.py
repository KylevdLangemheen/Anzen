import os

from anzen.bot import anzen_bot

BOT_TOKEN = os.getenv("BOT_TOKEN")

if __name__ == "__main__":
    anzen_bot.run(BOT_TOKEN)
