import discord
from discord.ext.commands import Bot

MY_GUILD = discord.Object(id=593006751394037790)


class Anzen(Bot):
    def __init__(self, intents=discord.Intents.default()):
        super().__init__(command_prefix="/", intents=intents)

    async def setup_hook(self):
        await self.load_extension("anzen.cogs.banwatcher")

    async def on_message(self, message: discord.Message):
        if message.author.guild.id == MY_GUILD.id:
            if message.content == "sync":
                await message.channel.send("Help I'm syncing!")
                self.tree.copy_global_to(guild=MY_GUILD)
                synced = await self.tree.sync(guild=MY_GUILD)
                await message.channel.send(f"Sync complete: {synced}")

            if message.content == "list":
                print([c.name for c in self.tree.get_commands()])
        else:
            print(
                f"Message from {message.author} in {message.author.guild.name}: {message.content}"
            )


intents = discord.Intents.default()
intents.message_content = True  # Placeholder for development
intents.members = True  # Necessary for on_member_join / etc.
intents.bans = True  # Necessary for on_member_ban

anzen_bot = Anzen(intents=intents)
