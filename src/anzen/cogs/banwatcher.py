import asyncio
from datetime import datetime
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
    ban_datetime: datetime | None = None


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
        self.server_config = {}

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

    @staticmethod
    def _flag_present(reason: str | None, flag: str) -> bool:
        """Check whether `flag` appears as a standalone token in `reason`.

        Whole-token matching (split on whitespace) rather than a raw
        substring check, so e.g. an override of "--no-log" won't
        accidentally match inside a reason like "--no-logging-policy".
        """
        if not reason or not flag:
            return False
        return flag in reason.split()

    @classmethod
    def _resolve_reason_visibility(cls, config: Config, reason: str | None) -> bool:
        """Whether the ban reason text should be shared, per the banning
        guild's privacy configuration.

        log_all_reasons is a baseline; a matched override flag flips it:
            True  + not matched -> True   (log by default)
            True  + matched     -> False  (explicitly suppressed this one)
            False + not matched -> False  (don't log by default)
            False + matched     -> True   (explicitly opted this one in)
        """
        if reason is None:
            return False
        override_matched = cls._flag_present(reason, config.log_reasons_override)
        return config.log_all_reasons != override_matched

    @classmethod
    def _resolve_ban_visibility(
        cls, config: Config, reason: str | None
    ) -> tuple[bool, bool]:
        """Whether a ban should be shared with other guilds at all, and
        whether its reason specifically should be included.

        Returns (should_log_ban, should_log_reason).

        Bans have the same flip pattern as ban reason:
            log_all_bans True  + flag not matched -> logged (opt-out)
            log_all_bans True  + flag matched     -> not logged
            log_all_bans False + flag not matched -> not logged (opt-in)
            log_all_bans False + flag matched     -> logged

        With one exception: only when BOTH log_all_bans and log_all_reasons are
        False: the reason override flag also opts the ban in. The reason is
        then opt-in too, so using its flag means "log this ban with its
        reason".
        """
        should_log_reason = cls._resolve_reason_visibility(config, reason)
        bans_override_matched = cls._flag_present(reason, config.log_bans_override)

        if config.log_all_bans:
            should_log_ban = not bans_override_matched
        else:
            reason_opted_in = not config.log_all_reasons and should_log_reason
            should_log_ban = bans_override_matched or reason_opted_in

        return should_log_ban, should_log_reason

    @classmethod
    def _resolve_shareable_ban_item(
        cls, config: Config | None, ban_item: BanItem
    ) -> BanItem | None:
        """Given the banning guild's Config and a raw BanItem, return the
        version of it safe to share with other guilds, or None if the
        banning guild's privacy settings say it shouldn't be shared at all.

        If the banning guild has no Anzen configuration (never ran
        /configure), we fail closed: no config means no explicit consent
        to share its ban data, so we don't share anything.
        """
        if config is None:
            return None

        should_log_ban, should_log_reason = cls._resolve_ban_visibility(
            config, ban_item.reason
        )
        if not should_log_ban:
            return None
        if should_log_reason:
            return ban_item
        return ban_item.model_copy(update={"reason": None})

    @staticmethod
    def _build_ping_mentions(config: Config) -> str:
        """Ping prefix for a log message: mentions the RECEIVING guild's
        configured mod roles and mod users. Empty string if none configured.
        """
        mentions = [f"<@&{role_id}>" for role_id in config.modrole_ids]
        mentions += [f"<@{user_id}>" for user_id in config.moduser_ids]
        if not mentions:
            return ""
        return "\n" + " ".join(mentions)

    async def _find_ban_audit_entry(
        self, guild: Guild, member: User | Member
    ) -> discord.AuditLogEntry | None:
        """Look up the audit log entry for `member`'s ban in `guild`, if one
        is still present in the audit log. Used to recover the original
        ban timestamp (AuditLogEntry.created_at) for bans that already
        existed before this bot noticed them (e.g. discovered on join,
        rather than caught live via on_member_ban).
        """
        try:
            async for entry in guild.audit_logs(
                action=discord.AuditLogAction.ban, limit=50
            ):
                if entry.target and entry.target.id == member.id:
                    return entry
        except discord.Forbidden:
            pass
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
            # fetch_ban doesn't include a timestamp, so pull it from the
            # audit log if it's still available there.
            audit_entry = await self._find_ban_audit_entry(guild, member)
            ban_item = BanItem(
                server_id=guild.id,
                user_id=ban_entry.user.id,
                reason=ban_entry.reason,
                ban_datetime=audit_entry.created_at if audit_entry else None,
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
        guild_name = str(self.bot.get_guild(bi.server_id))
        when = (
            f" ({discord.utils.format_dt(bi.ban_datetime, style='f')})"
            if bi.ban_datetime is not None
            else ""
        )
        if bi.reason is not None:
            return f"{guild_name}{when}\n  - With reason: {bi.reason}"
        return f"{guild_name}{when}"

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
            if ban_item is None:
                continue

            # Privacy check belongs to the guild the ban happened in
            banning_guild_config = self.server_config.get(other_guild.id)
            shareable_item = self._resolve_shareable_ban_item(
                banning_guild_config, ban_item
            )
            if shareable_item is not None:
                ban_items.append(shareable_item)

        if not ban_items:
            return

        channel = self._get_logchannel_for_guild(member.guild)
        if channel is None:
            return

        # Ping preferences belong to the RECEIVING guild
        receiving_config = self.server_config[member.guild.id]
        ping = self._build_ping_mentions(receiving_config)

        message = (
            f"# New Member{ping}\nYour new member <@{member.id}> has previously been "
            f"banned in {len(ban_items)} other guild(s):\n- "
            + "\n- ".join(self._format_joinmessage(bi) for bi in ban_items)
        )
        await channel.send(message)

    async def log_new_member(self, member: Member, ban_list: list[BanItem]):
        pass

    async def get_ban_reason(
        self, guild: Guild, member: User | Member, retries: int = 3
    ) -> tuple[str | None, datetime | None]:
        # TODO: If a lot of members are banned within a couple of seconds, this method will miss them.
        # There doesn't seem to be a better way of doing this for now though.
        await asyncio.sleep(1)
        for _ in range(retries):
            async for entry in guild.audit_logs(limit=10):
                if entry.target.id == member.id:
                    return entry.reason, entry.created_at
            await asyncio.sleep(2)
        return None, None

    @Cog.listener()
    async def on_member_ban(self, guild: Guild, member: User | Member):
        """Handle checks whether this member exists on other servers and notify them."""
        # TODO: Store references to logs such that logs can be removed when necessary
        # TODO: Be able to invoke on_member_ban through API. Optionally connect this bot's on_member_ban to said API
        print(f"{member} got banned in {guild}.")
        reason, ban_datetime = await self.get_ban_reason(guild, member)
        bi = BanItem(
            server_id=guild.id,
            user_id=member.id,
            reason=reason,
            ban_datetime=ban_datetime,
        )

        # Resolve privacy ONCE.
        banning_guild_config = self.server_config.get(guild.id)
        shareable_item = self._resolve_shareable_ban_item(banning_guild_config, bi)
        if shareable_item is None:
            return  # Banning guild's privacy settings say: don't share this ban anywhere.

        for other_guild in self.bot.guilds:
            if other_guild == guild:
                continue

            if other_guild.get_member(member.id) is None:
                continue

            print(f"Member {member} exists in other server {other_guild}.")
            channel = self._get_logchannel_for_guild(other_guild)
            if channel is None:
                continue

            # Ping preferences belong to the RECEIVING guild.
            receiving_config = self.server_config[other_guild.id]
            ping = self._build_ping_mentions(receiving_config)

            when = (
                f" {discord.utils.format_dt(shareable_item.ban_datetime, style='f')}"
                if shareable_item.ban_datetime is not None
                else ""
            )

            if shareable_item.reason is not None:
                message = (
                    f"# Banned Member{ping}\nYour member <@{shareable_item.user_id}> just "
                    f"got banned in {self.bot.get_guild(shareable_item.server_id)}{when} with "
                    f"reason: {shareable_item.reason}."
                )
                print(f"Trying to log to {channel}")
                print(message)
                await channel.send(message)
                continue
            message = (
                f"# Banned Member{ping}\nYour member <@{shareable_item.user_id}> just "
                f"got banned in {self.bot.get_guild(shareable_item.server_id)}{when}."
            )
            await channel.send(message)

    @command()
    async def configure(self, interaction: discord.Interaction):
        """Configure Anzen."""
        # Start from what this guild already saved, so re-running /configure
        # shows (and re-saves) the current values instead of the defaults.
        settings = Settings.from_config(self.server_config.get(interaction.guild.id))
        view = SettingsView(self.sessionmanager, Config, interaction.guild, settings)
        await interaction.response.send_message(view=view, ephemeral=False)
        await view.wait()

        await self._update_logchannels()

        print(f"Settings updated: {settings}")


async def setup(bot):
    await bot.add_cog(BanWatcher(bot))
