import asyncio
from enum import Enum

import discord
from discord import Guild, Member, Thread, User  # noqa
from discord.abc import GuildChannel, PrivateChannel
from discord.app_commands import command
from discord.ext.commands import Bot, Cog
from pydantic import BaseModel

from anzen.data.database import DB_HOST, DatabaseSessionManager
from anzen.data.datamodel import Config
from anzen.views.configure import Settings, SettingsView

# Wants bot permissions "ban members" "view audit log", "send messages", "send messages in threads"


class BanItem(BaseModel):
    server_id: int
    user_id: int
    reason: str | None


# TODO: Add your preferred ban fetch methods here if you do not want to rely on the discord api
class BanFetchMethod(Enum):
    DISCORD_API: int = 0


class BanWatcher(Cog):
    # Experimenting with Components V2 now.
    server_config: dict[int, Config] = {}

    async def _update_logchannels(self) -> dict[int, int]:
        async with self.sessionmanager.session() as db:
            all_configs = await Config.get_all(db)
            self.server_config = {config.server_id: config for config in all_configs}

    def __init__(self, bot: Bot):
        self.bot = bot
        self.sessionmanager = DatabaseSessionManager()
        self.sessionmanager.init(DB_HOST)

    async def cog_load(self):
        await self._update_logchannels()
        return await super().cog_load()

    def _get_logchannel_for_guild(
        self, guild: Guild
    ) -> GuildChannel | Thread | PrivateChannel | None:
        if guild.id in self.server_config:
            channel = self.bot.get_channel(self.server_config[guild.id].logchannel_id)
            return channel
        else:
            return None

    async def _member_banned_in_guild_discord_api(
        self, member: Member, guild: Guild
    ) -> BanItem | None:
        try:
            ban_entry = await guild.fetch_ban(
                member
            )  # Member is a Member, not a snowflake nor a user, will this work?
            if ban_entry is None:
                return None
            ban_item = BanItem(
                server_id=guild.id, user_id=ban_entry.user.id, reason=ban_entry.reason
            )
            # TODO: Ban reason parsing
            return ban_item
        except discord.Forbidden as e:
            # TODO: Raise nice warning and log <3
            print(
                f"For some reason, no permission to check whether {member} is banned in {guild} with error {e}. Skipping."
            )
        except (
            discord.HTTPException
        ) as e:  # This is the default when member was not banned before.
            # TODO: Raise nice warning and log <3
            # Base case is simply that the user doesn't exist ;)
            if not (e.status == 404 and e.code == 10026):
                print(
                    f"Some HTTP error occurred while checking whether {member} is banned on server {guild} with error {e}. Skipping"
                )
        except discord.NotFound:  # Not used I think?
            pass

    async def _member_banned_in_guild(
        self,
        member: Member,
        guild: Guild,
        method: BanFetchMethod = BanFetchMethod.DISCORD_API,
    ) -> BanItem | None:
        # TODO: allow Anzen to be configured to query an external API for subset of bans instead
        ban_item = None
        if method == BanFetchMethod.DISCORD_API:
            ban_item = await self._member_banned_in_guild_discord_api(
                member=member, guild=guild
            )
        else:
            raise NotImplementedError(
                f"BanFetchMethod '{method}' not yet implemented.\nSupported methods are: {[m.name for m in BanFetchMethod]}"
            )
        return ban_item

    def _format_joinmessage(self, bi: BanItem):
        if bi.reason is not None:
            return (
                f"{str(self.bot.get_guild(bi.server_id))}\n  - With reason: {bi.reason}"
            )
        return f"{str(self.bot.get_guild(bi.server_id))}"

    @Cog.listener()
    async def on_member_join(self, member: Member):
        """Handle checks whether this member is banned on other servers here."""
        # TODO: optionally ignore expired bans & unbans
        ban_items: list[BanItem] = []
        for other_guild in self.bot.guilds:
            # Skip the guild that triggered this
            if other_guild == member.guild:
                continue

            ban_item = await self._member_banned_in_guild(member, other_guild)
            if ban_item is not None:
                ban_items.append(ban_item)
                # New member is banned in other guild, log!

        if not ban_items:
            return

        channel = self._get_logchannel_for_guild(member.guild)
        if channel is None:
            return
        role_id = self.server_config.get(member.guild.id).modrole_id
        ping = f"\n<@&{role_id}> " if role_id else ""
        message = f"# New Member{ping}\nYour new member <@{member.id}> has previously been banned in {len(ban_items)} other guild(s):\n- {'\n- '.join([self._format_joinmessage(bi) for bi in ban_items])}"
        await channel.send(message)

    async def log_new_member(self, member: Member, ban_list: list[BanItem]):
        pass

    async def get_ban_reason(
        self, guild: Guild, member: User | Member, retries: int = 3
    ) -> str | None:
        # TODO: If a lot of members are banned within a couple of seconds, this method will miss them.
        # There doesn't seem to be a better way of doing this for now though.
        await asyncio.sleep(1)
        for _ in range(retries):
            async for entry in guild.audit_logs(limit=10):
                if entry.target.id == member.id:
                    return entry.reason
            await asyncio.sleep(2)

    @Cog.listener()
    async def on_member_ban(self, guild: Guild, member: User | Member):
        """Handle checks whether this member exists on other servers and notify them."""
        # TODO: Store references to logs such that logs can be removed when necessary
        # TODO: Be able to invoke on_member_ban through API. Optionally connect this bot's on_member_ban to said API
        print(f"{member} got banned in {guild}.")
        bi = BanItem(
            server_id=guild.id,
            user_id=member.id,
            reason=await self.get_ban_reason(guild, member),
        )
        for other_guild in self.bot.guilds:
            if other_guild == guild:
                continue

            if other_guild.get_member(member.id) is None:
                continue

            print(f"Member {member} exists in other server {other_guild}.")
            channel = self._get_logchannel_for_guild(other_guild)
            if channel is None:
                continue
            role_id = self.server_config.get(other_guild.id).modrole_id
            ping = f"\n<@&{role_id}> " if role_id else ""
            if bi.reason is not None:
                message = f"# Banned Member{ping}\nYour member <@{bi.user_id}> just got banned in {self.bot.get_guild(bi.server_id)} with reason: {bi.reason}."
                print(f"Trying to log to {channel}")
                print(message)
                await channel.send(message)
                continue
            message = f"# Banned Member{ping}\nYour member <@{bi.user_id}> just got banned in {self.bot.get_guild(bi.server_id)}."
            await channel.send(message)

    @command()
    async def configure(self, interaction: discord.Interaction):
        """Configure Anzen."""
        settings = Settings()
        view = SettingsView(self.sessionmanager, Config, interaction.guild, settings)
        # await interaction.channel.send("No.")
        await interaction.response.send_message(view=view, ephemeral=False)
        await view.wait()

        await self._update_logchannels()

        print(f"Settings updated: {settings}")


async def setup(bot):
    await bot.add_cog(BanWatcher(bot))
