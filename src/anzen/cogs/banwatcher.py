import discord
from discord.app_commands import command
from discord.ext.commands import Cog

from anzen.modals.configure import Feedback


class BanWatcher(Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _member_banned_in_guild(self, member, guild) -> bool:
        try:
            ban_entry = await guild.fetch_ban(
                member
            )  # Member is a Member, not a snowflake nor a user, will this work?
            ban_entry
            # TODO: Ban reason parsing
        except discord.Forbidden as e:
            # TODO: Raise nice warning and log <3
            print(
                f"For some reason, {self.user} did not have permission to check for bans in {guild} with error {e}. Skipping."
            )
            return False
        except discord.HTTPException as e:
            # TODO: Raise nice warning and log <3
            print(
                f"Some HTTP error occurred while checking whether {member} is banned on server {guild} with error {e}. Skipping"
            )
            return False
        except discord.NotFound:
            return False
        return True

    @Cog.listener()
    async def on_member_join(self, member):
        """Handle checks whether this member is banned on other servers here."""
        banned_in = []
        for other_guild in self.guilds:
            # Skip the guild that triggered this
            if other_guild == member.guild:
                continue

            if self._member_banned_in_guild(member, other_guild):
                banned_in.append(other_guild)
                # New member is banned in other guild, log!

        print(
            f"Your new member {member} has previously been banned in {len(banned_in)} other guild(s):"
        )
        print(f"{banned_in}")

    @Cog.listener()
    async def on_member_ban(self, guild, user):
        """Handle checks whether this member exists on other servers and notify them."""
        for other_guild in self.guilds:
            if other_guild == guild:
                continue

            if other_guild.get_member(user.id) is not None:
                print(f"Your member {user} has just been banned in {guild}")
                # Banned member is present on this guild, log!

    @command()
    async def configure(self, interaction: discord.Interaction):
        """Configure Anzen."""
        await interaction.response.send_modal(Feedback())


async def setup(bot):
    await bot.add_cog(BanWatcher(bot))
