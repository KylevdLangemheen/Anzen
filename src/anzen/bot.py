import math

import discord
from discord import Interaction, app_commands
from discord.ext.commands import Bot

MY_GUILD = discord.Object(id=593006751394037790)


class Anzen(Bot):
    def __init__(self, intents=discord.Intents.default()):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("Starting Anzen, loading banwatcher...")
        await self.load_extension("anzen.cogs.banwatcher")
        print("Banwatcher loaded, syncing to debugging guild...")
        self.tree.copy_global_to(guild=MY_GUILD)
        cmds = await self.tree.sync(guild=MY_GUILD)
        print(f"Syncing complete with commands:\n{cmds}")

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


# Source - https://stackoverflow.com/a/48091128
# Posted by mental, modified by community. See post 'Timeline' for change history
# Retrieved 2026-06-20, License - CC BY-SA 4.0
@anzen_bot.tree.command()
async def ping(interaction: Interaction):
    await interaction.response.send_message(
        f"Pong! {math.ceil(anzen_bot.latency * 1000)}ms"
    )


# Source - https://stackoverflow.com/a/76395873
# Posted by thecalendar
# Retrieved 2026-06-20, License - CC BY-SA 4.0
@anzen_bot.tree.command()
@app_commands.guild_only()
async def sync(interaction: Interaction):
    print("sync command")

    perms = interaction.user.guild_permissions
    if perms.administrator or perms.manage_guild:
        await anzen_bot.tree.sync()
        await interaction.channel.send("Command tree synced.")
    else:
        await interaction.channel.send(
            "You must have `Manage Server` permissions (or be an admin) to use this command!"
        )
