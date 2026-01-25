import discord
from discord.ext.commands import Cog, check, command


class DevTools(Cog):
    def __init__(self, bot):
        self.bot = bot

    @command()
    async def sync(self, ctx, *, member: discord.Member = None):
        """Doesn't say hello."""
        ctx.send("nohello")


def setup(bot):
    bot.add_cog(DevTools(bot))
