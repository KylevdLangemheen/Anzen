import discord
from discord.ext.commands import Bot

MY_GUILD = discord.Object(id=167811324590424065)


class Anzen(Bot):
    def __init__(self, intents=discord.Intents.default()):
        super().__init__(command_prefix="/", intents=intents)

    async def setup_hook(self):
        await self.load_extension("anzen.cogs.banwatcher")

    async def on_guild_join(self, guild: discord.Guild):
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)


intents = discord.Intents.none()
# intents.message_content = False  # Not necessary!
intents.members = True  # Necessary for on_member_join / etc.
intents.bans = True  # Necessary for on_member_ban
intents.guilds = True  # Necessary for on_guild_join
intents.moderation = True  # Same as intents.bans?

anzen_bot = Anzen(intents=intents)
