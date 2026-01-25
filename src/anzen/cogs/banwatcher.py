import discord
from discord import Guild, Member, Thread, User  # noqa
from discord.abc import GuildChannel, PrivateChannel
from discord.app_commands import command
from discord.ext.commands import Bot, Cog

from anzen.modals.configure import Feedback


class BanWatcher(Cog):
    # TODO: add ways to configure this nicely. Maybe a web UI?
    guild_logchannel = {
        # STEM Net : user-blacklist
        1449762075109752955: 1449797203362320496,
        # Artificial Intelligence :
        167811324590424065: 1465002838634533160,
    }

    def __init__(self, bot: Bot):
        self.bot = bot

    def _get_logchannel_for_guild(
        self, guild: Guild
    ) -> GuildChannel | Thread | PrivateChannel | None:
        if guild.id in self.guild_logchannel:
            channel = self.bot.get_channel(self.guild_logchannel[guild.id])
            return channel
        else:
            return None

    async def _member_banned_in_guild(self, member: Member, guild: Guild) -> bool:
        try:
            ban_entry = await guild.fetch_ban(
                member
            )  # Member is a Member, not a snowflake nor a user, will this work?
            ban_entry
            # TODO: Ban reason parsing
            return ban_entry is not None
        except discord.Forbidden as e:
            # TODO: Raise nice warning and log <3
            print(
                f"For some reason, {self.member} did not have permission to check for bans in {guild} with error {e}. Skipping."
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
        return False

    @Cog.listener()
    async def on_member_join(self, member: Member):
        """Handle checks whether this member is banned on other servers here."""
        banned_in = []
        for other_guild in self.bot.guilds:
            # Skip the guild that triggered this
            if other_guild == member.guild:
                continue

            was_banned = await self._member_banned_in_guild(member, other_guild)
            if was_banned:
                banned_in.append(other_guild)
                # New member is banned in other guild, log!

        if not banned_in:
            return

        channel = self._get_logchannel_for_guild(member.guild)
        if channel is None:
            return
        message = f"# New Member\nYour new member {member} has previously been banned in {len(banned_in)} other guild(s):\n- {'\n- '.join([str(g) for g in banned_in])}"
        await channel.send(message)

    @Cog.listener()
    async def on_member_ban(self, guild: Guild, member: User | Member):
        """Handle checks whether this member exists on other servers and notify them."""
        for other_guild in self.guilds:
            if other_guild == guild:
                continue

            if other_guild.get_member(member.id) is not None:
                channel = self._get_logchannel_for_guild(member.guild)
                if channel is None:
                    return
                message = f"# Banned Member\nYour member {member} just got banned in {other_guild}."
                await channel.send(message)

    @command()
    async def configure(self, interaction: discord.Interaction):
        """Configure Anzen."""
        await interaction.response.send_modal(Feedback())


async def setup(bot):
    await bot.add_cog(BanWatcher(bot))
