from __future__ import annotations

import logging
from typing import Callable

import discord
from discord import (
    ButtonStyle,
    ChannelType,
    Guild,
    Interaction,
    PartialMessageable,
    SelectDefaultValue,
    SelectDefaultValueType,
    SelectOption,
    SeparatorSpacing,
    TextStyle,
    ui,
)
from discord.ui import (
    ActionRow,
    Button,
    ChannelSelect,
    Container,
    LayoutView,
    Select,
    Separator,
    TextDisplay,
)
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from anzen.data.database import DatabaseSessionManager
from anzen.data.datamodel import Config


# This is where we'll store our intermediate settings.
class Settings(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    category: PartialMessageable | None = None
    channel: str | None = None
    modroles: list[str] = Field(default_factory=list)
    modusers: list[str] = Field(default_factory=list)
    log_all_bans: bool = True
    log_all_reasons: bool = True
    log_bans_override: str = "--no-log"
    log_reasons_override: str = "--no-reason"

    # Not strictly necessary to set this as PrivateAttr in pydanticv2
    # But as you know, explicit is better than implicit...
    _category_callbacks: list[Callable] = PrivateAttr(default_factory=list)
    _log_all_bans_callbacks: list[Callable] = PrivateAttr(default_factory=list)
    _log_all_reasons_callbacks: list[Callable] = PrivateAttr(default_factory=list)

    @classmethod
    def from_config(cls, config: Config | None) -> Settings:
        """Build the intermediate settings from a guild's saved `Config`.

        Falls back to the defaults for a guild without preexisting config.
        Fields are passed through the initializer, which does not go through
        `__setattr__`, so none of the change callbacks fire (which would
        overwrite the saved override flags)! The category is not persisted,
        so it always starts unset.
        """
        # TODO: handle category not persisted
        # TODO: handle graceful fallback or warning message if roles or channels changed between now and previous configure run. I.e. when a role was removed.
        if config is None:
            return cls()
        return cls(
            channel=str(config.logchannel_id),
            modroles=[str(rid) for rid in config.modrole_ids],
            modusers=[str(uid) for uid in config.moduser_ids],
            log_all_bans=config.log_all_bans,
            log_all_reasons=config.log_all_reasons,
            log_bans_override=config.log_bans_override,
            log_reasons_override=config.log_reasons_override,
        )

    def on_category_change(self, callback: Callable):
        """Register a callback to fire when category changes"""
        self._category_callbacks.append(callback)
        return callback

    def on_log_all_bans_change(self, callback: Callable):
        """Register a callback to fire when log_all_bans changes"""
        self._log_all_bans_callbacks.append(callback)
        return callback

    def on_log_all_reasons_change(self, callback: Callable):
        """Register a callback to fire when log_all_reasons changes"""
        self._log_all_reasons_callbacks.append(callback)
        return callback

    def __setattr__(self, name, value):
        if name == "category" and hasattr(self, "_category_callbacks"):
            old_value = getattr(self, "category", None)
            super().__setattr__(name, value)
            if old_value != value:
                for callback in self._category_callbacks:
                    callback(old_value, value)
        elif name == "log_all_bans" and hasattr(self, "_log_all_bans_callbacks"):
            old_value = getattr(self, "log_all_bans", None)
            super().__setattr__(name, value)
            if old_value != value:
                for callback in self._log_all_bans_callbacks:
                    callback(old_value, value)
        elif name == "log_all_reasons" and hasattr(self, "_log_all_reasons_callbacks"):
            old_value = getattr(self, "log_all_reasons", None)
            super().__setattr__(name, value)
            if old_value != value:
                for callback in self._log_all_reasons_callbacks:
                    callback(old_value, value)
        else:
            super().__setattr__(name, value)


class LogAllBansToggle(ActionRow["SettingsView"]):
    def __init__(self, settings: Settings, id: int | None = None):
        super().__init__(id=id)
        self.settings = settings
        self._sync_button()

    def _sync_button(self) -> None:
        enabled = self.settings.log_all_bans
        self.toggle.label = f"Log all bans: {'On' if enabled else 'Off'}"
        self.toggle.style = ButtonStyle.green if enabled else ButtonStyle.red

    @ui.button(label="Log all bans: On", style=ButtonStyle.green)
    async def toggle(self, interaction: Interaction, button: Button) -> None:
        self.settings.log_all_bans = not self.settings.log_all_bans
        self._sync_button()
        await interaction.response.edit_message(view=self.view)


class LogBansOverrideModal(ui.Modal, title="Set ban log override flag"):
    override_input = ui.TextInput(
        label="Override flag",
        placeholder="--no-log",
        min_length=1,
        max_length=50,
        required=True,
    )

    def __init__(self, row: LogBansOverrideRow):
        super().__init__()
        self.row = row
        self.override_input.default = row.settings.log_bans_override

    async def on_submit(self, interaction: Interaction) -> None:
        value = self.override_input.value.strip()
        if not value:
            await interaction.response.send_message(
                "Override flag cannot be empty.", ephemeral=True
            )
            return
        self.row.settings.log_bans_override = value
        self.row._sync_button()
        await interaction.response.edit_message(view=self.row.view)


class LogBansOverrideRow(ActionRow["SettingsView"]):
    def __init__(self, settings: Settings, id: int | None = None):
        super().__init__(id=id)
        self.settings = settings
        self._sync_button()
        # Keep the override synced to the "log all bans" default, the same
        # way ChannelSetting listens for category changes.
        self.settings.on_log_all_bans_change(self.apply_default)

    def apply_default(self, old_value: bool, new_value: bool) -> None:
        self.settings.log_bans_override = "--no-log" if new_value else "--log"
        self._sync_button()

    def _sync_button(self) -> None:
        self.edit_override.label = f"Override: {self.settings.log_bans_override}"

    @ui.button(label="Override: --no-log", style=ButtonStyle.secondary)
    async def edit_override(self, interaction: Interaction, button: Button) -> None:
        await interaction.response.send_modal(LogBansOverrideModal(self))


class LogAllReasonsToggle(ActionRow["SettingsView"]):
    def __init__(self, settings: Settings, id: int | None = None):
        super().__init__(id=id)
        self.settings = settings
        self._sync_button()

    def _sync_button(self) -> None:
        enabled = self.settings.log_all_reasons
        self.toggle.label = f"Log all ban reasons: {'On' if enabled else 'Off'}"
        self.toggle.style = ButtonStyle.green if enabled else ButtonStyle.red

    @ui.button(label="Log all ban reasons: On", style=ButtonStyle.green)
    async def toggle(self, interaction: Interaction, button: Button) -> None:
        self.settings.log_all_reasons = not self.settings.log_all_reasons
        self._sync_button()
        await interaction.response.edit_message(view=self.view)


class LogReasonsOverrideModal(ui.Modal, title="Set reason log override flag"):
    override_input = ui.TextInput(
        label="Override flag",
        placeholder="--no-reason",
        min_length=1,
        max_length=50,
        required=True,
    )

    def __init__(self, row: LogReasonsOverrideRow):
        super().__init__()
        self.row = row
        self.override_input.default = row.settings.log_reasons_override

    async def on_submit(self, interaction: Interaction) -> None:
        value = self.override_input.value.strip()
        if not value:
            await interaction.response.send_message(
                "Override flag cannot be empty.", ephemeral=True
            )
            return
        self.row.settings.log_reasons_override = value
        self.row._sync_button()
        await interaction.response.edit_message(view=self.row.view)


class LogReasonsOverrideRow(ActionRow["SettingsView"]):
    def __init__(self, settings: Settings, id: int | None = None):
        super().__init__(id=id)
        self.settings = settings
        self._sync_button()
        self.settings.on_log_all_reasons_change(self.apply_default)

    def apply_default(self, old_value: bool, new_value: bool) -> None:
        self.settings.log_reasons_override = (
            "--no-reason" if new_value else "--log-reason"
        )
        self._sync_button()

    def _sync_button(self) -> None:
        self.edit_override.label = f"Override: {self.settings.log_reasons_override}"

    @ui.button(label="Override: --no-reason", style=ButtonStyle.secondary)
    async def edit_override(self, interaction: Interaction, button: Button) -> None:
        await interaction.response.send_modal(LogReasonsOverrideModal(self))


class BanSettingsPage(Container):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

        header = TextDisplay(
            "# Ban Logging\n-# Configure how bans and ban reasons are propagated to other servers."
        )
        self.add_item(header)
        self.add_item(Separator(spacing=SeparatorSpacing.large))

        self.add_item(
            TextDisplay(
                "## Log All Bans\n-# Whether every ban should be propagated per default, "
                "or none. Click the override to change override flag. Putting the override into "
                "the ban reason will override the default you select, effectively flipping "
                "the behaviour for that specific ban."
            )
        )
        self.add_item(LogAllBansToggle(settings, id=200))
        self.add_item(LogBansOverrideRow(settings, id=201))

        self.add_item(
            TextDisplay(
                "## Log All Ban Reasons\n-# Whether the reason text attached to a logged ban should "
                "be propagated per default. Click the override to change override flag. Putting the "
                "override flag into the ban reason flips the default for that specific ban. This override "
                "flag has unique behaviour: If NOT logging all bans AND NOT logging all reasons, "
                "including the reason override in the ban reason will log the ban anyways, with its "
                "reason. If bans are off but reasons are on, only the ban override can opt a ban in."
            )
        )
        self.add_item(LogAllReasonsToggle(settings, id=202))
        self.add_item(LogReasonsOverrideRow(settings, id=203))


class ChannelSetting(ActionRow["SettingsView"]):
    def __init__(self, guild: Guild, settings: Settings, id: int | None = None):
        super().__init__(id=id)
        self.settings = settings
        self.guild = guild
        self.logger = logging.getLogger(__name__)

        options = self._get_options()
        self.channel_option = ChannelOption(
            settings=settings,
            placeholder="Select a channel",
            options=options,
            max_values=1,
            min_values=1,
        )

        self.add_item(self.channel_option)
        self.settings.on_category_change(self.update_options)

    def _get_options(self, target_category_id: int | None = None):
        options = []
        for cat, channels in self.guild.by_category():
            if cat is None and target_category_id is None:
                options += [
                    SelectOption(label=ch.name, value=str(ch.id)) for ch in channels
                ]
                break
            if cat is None or cat.id != target_category_id:
                continue
            options += [
                SelectOption(label=ch.name, value=str(ch.id)) for ch in channels
            ]
            break
        if not options:
            options = [SelectOption(label="No channels available", value="0")]

        # Re-apply the previously selected channel, if it's still in this list.
        for option in options:
            option.default = option.value == self.settings.channel

        return options[:25]

    def update_options(self, old_category, new_category) -> None:
        target_category_id = new_category.id if new_category is not None else None
        options = self._get_options(target_category_id)
        self.channel_option.options = options
        return True


class ChannelOption(Select):
    def __init__(self, settings: Settings, **kwargs):
        super().__init__(**kwargs)
        self.settings = settings

    async def callback(self, interaction: Interaction):
        if self.values and self.values[0] and self.values[0] != "0":
            self.settings.channel = self.values[0]
            for option in self.options:
                option.default = option.value == self.values[0]
        await interaction.response.defer()


class CategorySetting(ActionRow["SettingsView"]):
    def __init__(self, settings: Settings, id=None):
        super().__init__(id=id)
        self.settings = settings
        if settings.category is not None:
            self.select_channel.default_values = [
                SelectDefaultValue(
                    id=settings.category.id, type=SelectDefaultValueType.channel
                )
            ]

    @ui.select(
        placeholder="Optional category",
        channel_types=[ChannelType.category],
        max_values=1,
        min_values=0,
        cls=ChannelSelect,
    )
    async def select_channel(
        self, interaction: Interaction, select: ChannelSelect
    ) -> None:
        if select.values:
            channel = select.values[0]
            self.settings.category = interaction.client.get_partial_messageable(
                channel.id, guild_id=channel.guild_id, type=channel.type
            )
            select.default_values = [
                SelectDefaultValue(id=channel.id, type=SelectDefaultValueType.channel)
            ]
        else:
            self.settings.category = None
            select.default_values = []
        await interaction.response.edit_message(view=self.view)


class RoleMultiButtonRow(ActionRow["SettingsView"]):
    def __init__(self, select_row: RoleMultiSelectRow, id=None):
        super().__init__(id=id)
        self.select_row = select_row

    @ui.button(label="Can't see a role? Add by ID", style=ButtonStyle.secondary)
    async def add_role_by_id(self, interaction: Interaction, button: ui.Button) -> None:
        await interaction.response.send_modal(RoleMultiIDModal(self.select_row))


class RoleMultiIDModal(ui.Modal, title="Add roles by ID"):
    role_ids_input = ui.TextInput(
        label="Role IDs (comma or newline separated)",
        style=TextStyle.paragraph,
        placeholder="123456789012345678, 234567890123456789",
        required=True,
    )

    def __init__(self, row: RoleMultiSelectRow):
        super().__init__()
        self.row = row

    async def on_submit(self, interaction: Interaction) -> None:
        raw_ids = [
            part.strip()
            for part in self.role_ids_input.value.replace(",", "\n").splitlines()
            if part.strip()
        ]

        resolved: list[discord.Role] = []
        invalid: list[str] = []
        for raw in raw_ids:
            if not raw.isdigit():
                invalid.append(raw)
                continue
            role = interaction.guild.get_role(int(raw))
            if role is None:
                invalid.append(raw)
                continue
            resolved.append(role)

        existing_ids = {int(rid) for rid in self.row.settings.modroles}
        merged = {r.id: r for r in resolved}
        merged_ids = existing_ids | merged.keys()

        if len(merged_ids) > 25:
            await interaction.response.send_message(
                "That would exceed the 25-role limit; add fewer at a time.",
                ephemeral=True,
            )
            return

        self.row.settings.modroles = [str(i) for i in merged_ids]
        self.row.select_roles.default_values = [
            SelectDefaultValue(id=i, type=SelectDefaultValueType.role)
            for i in merged_ids
        ]

        if invalid:
            await interaction.response.edit_message(view=self.row.view)
            await interaction.followup.send(
                f"Added the valid IDs. Couldn't resolve: {', '.join(invalid)}",
                ephemeral=True,
            )
        else:
            await interaction.response.edit_message(view=self.row.view)


class RoleMultiSelectRow(ActionRow["SettingsView"]):
    def __init__(self, settings: Settings, id=None):
        super().__init__(id=id)
        self.settings = settings
        if settings.modroles:
            self.select_roles.default_values = [
                SelectDefaultValue(id=int(rid), type=SelectDefaultValueType.role)
                for rid in settings.modroles
            ]

    @ui.select(
        placeholder="Optional roles to ping (up to 25)",
        cls=ui.RoleSelect,
        max_values=25,
        min_values=0,
    )
    async def select_roles(
        self, interaction: Interaction, select: ui.RoleSelect
    ) -> None:
        roles = select.values
        self.settings.modroles = [str(r.id) for r in roles]
        select.default_values = [
            SelectDefaultValue(id=r.id, type=SelectDefaultValueType.role) for r in roles
        ]
        await interaction.response.edit_message(view=self.view)


class RoleSelectRow(ActionRow["SettingsView"]):
    def __init__(self, settings: Settings, id=None):
        super().__init__(id=id)
        self.settings = settings

    @ui.select(
        placeholder="Optional role to ping",
        cls=ui.RoleSelect,
        max_values=1,
        min_values=0,
    )
    async def select_role(
        self, interaction: Interaction, select: ui.RoleSelect
    ) -> None:
        if select.values:
            role = select.values[0]
            self.settings.modrole = str(role.id)
            select.default_values = [
                SelectDefaultValue(id=role.id, type=SelectDefaultValueType.role)
            ]
        else:
            self.settings.modrole = None
            select.default_values = []
        await interaction.response.edit_message(view=self.view)


class RoleButtonRow(ActionRow["SettingsView"]):
    def __init__(self, select_row: RoleSelectRow, id=None):
        super().__init__(id=id)
        self.select_row = select_row

    @ui.button(label="Can't see your role?", style=ButtonStyle.secondary)
    async def set_role_by_id(self, interaction: Interaction, button: ui.Button) -> None:
        await interaction.response.send_modal(RoleIDModal(self.select_row))


class RoleIDModal(ui.Modal, title="Set role by ID"):
    role_id_input = ui.TextInput(
        label="Role ID",
        placeholder="Enter the role ID here...",
        min_length=17,
        max_length=20,
        required=True,
    )

    def __init__(self, action_row: RoleSelectRow):
        super().__init__()
        self.action_row = action_row

    async def on_submit(self, interaction: Interaction) -> None:
        raw = self.role_id_input.value.strip()

        if not raw.isdigit():
            await interaction.response.send_message(
                "Invalid role ID — must be a numeric snowflake.", ephemeral=True
            )
            return

        role = interaction.guild.get_role(int(raw))
        if role is None:
            await interaction.response.send_message(
                "No role with that ID was found in this server.", ephemeral=True
            )
            return

        self.action_row.settings.modrole = str(role.id)
        self.action_row.select_role.default_values = [
            SelectDefaultValue(id=role.id, type=SelectDefaultValueType.role)
        ]
        await interaction.response.edit_message(view=self.action_row.view)


class UserMultiSelectRow(ActionRow["SettingsView"]):
    def __init__(self, settings: Settings, id=None):
        super().__init__(id=id)
        self.settings = settings
        if settings.modusers:
            self.select_users.default_values = [
                SelectDefaultValue(id=int(uid), type=SelectDefaultValueType.user)
                for uid in settings.modusers
            ]

    @ui.select(
        placeholder="Optional users to ping (up to 25)",
        cls=ui.UserSelect,
        max_values=25,
        min_values=0,
    )
    async def select_users(
        self, interaction: Interaction, select: ui.UserSelect
    ) -> None:
        users = select.values
        self.settings.modusers = [str(u.id) for u in users]
        select.default_values = [
            SelectDefaultValue(id=u.id, type=SelectDefaultValueType.user) for u in users
        ]
        await interaction.response.edit_message(view=self.view)


class UserMultiButtonRow(ActionRow["SettingsView"]):
    def __init__(self, select_row: UserMultiSelectRow, id=None):
        super().__init__(id=id)
        self.select_row = select_row

    @ui.button(label="Can't see a user? Add by ID", style=ButtonStyle.secondary)
    async def add_user_by_id(self, interaction: Interaction, button: ui.Button) -> None:
        await interaction.response.send_modal(UserMultiIDModal(self.select_row))


class UserMultiIDModal(ui.Modal, title="Add users by ID"):
    user_ids_input = ui.TextInput(
        label="User IDs (comma or newline separated)",
        style=TextStyle.paragraph,
        placeholder="123456789012345678, 234567890123456789",
        required=True,
    )

    def __init__(self, row: UserMultiSelectRow):
        super().__init__()
        self.row = row

    async def on_submit(self, interaction: Interaction) -> None:
        raw_ids = [
            part.strip()
            for part in self.user_ids_input.value.replace(",", "\n").splitlines()
            if part.strip()
        ]

        resolved_ids: set[int] = set()
        invalid: list[str] = []
        for raw in raw_ids:
            if not raw.isdigit():
                invalid.append(raw)
                continue
            member = interaction.guild.get_member(int(raw))
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(int(raw))
                except discord.NotFound:
                    invalid.append(raw)
                    continue
            resolved_ids.add(member.id)

        existing_ids = {int(uid) for uid in self.row.settings.modusers}
        merged_ids = existing_ids | resolved_ids

        if len(merged_ids) > 25:
            await interaction.response.send_message(
                "That would exceed the 25-user limit; add fewer at a time.",
                ephemeral=True,
            )
            return

        self.row.settings.modusers = [str(i) for i in merged_ids]
        self.row.select_users.default_values = [
            SelectDefaultValue(id=i, type=SelectDefaultValueType.user)
            for i in merged_ids
        ]

        if invalid:
            await interaction.response.edit_message(view=self.row.view)
            await interaction.followup.send(
                f"Added the valid IDs. Couldn't resolve: {', '.join(invalid)}",
                ephemeral=True,
            )
        else:
            await interaction.response.edit_message(view=self.row.view)


class PingSettingsPage(Container):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

        self.add_item(
            TextDisplay("# Ping Settings\n-# Configure who gets pinged on ban events.")
        )
        self.add_item(Separator(spacing=SeparatorSpacing.large))

        self.add_item(TextDisplay("## Roles to Ping\n-# Optional, up to 25 roles."))
        role_row = RoleMultiSelectRow(settings, id=300)
        self.add_item(role_row)
        self.add_item(RoleMultiButtonRow(role_row, id=301))

        self.add_item(
            TextDisplay("## Users to Ping\n-# Optional, up to 25 individual users.")
        )
        user_row = UserMultiSelectRow(settings, id=302)
        self.add_item(user_row)
        self.add_item(UserMultiButtonRow(user_row, id=303))


class ChannelPage(Container):
    def __init__(self, guild: Guild, settings: Settings):
        super().__init__()
        self.settings = settings
        self.guild = guild

        # For this example, we'll use multiple sections to organize the settings.
        header = TextDisplay(
            "# Anzen Settings\n-# Configure where and what Anzen will log."
        )
        self.add_item(header)
        self.add_item(Separator(spacing=SeparatorSpacing.large))

        self.add_item(
            TextDisplay(
                "## Category Selection\n-# This optionally filters channels for Channel Selection."
            )
        )
        self.add_item(CategorySetting(self.settings, id=100))
        self.add_item(
            TextDisplay(
                "## Channel Selection\n-# This is the channel where the logs will be sent."
            )
        )
        self.add_item(ChannelSetting(self.guild, self.settings, id=101))
        self.add_item(
            TextDisplay(
                "## Coming Soon\n-# Further options such as default behaviour are coming soon."
            )
        )


class ChannelPageView(LayoutView):
    row = ActionRow()

    def __init__(
        self,
        guild: Guild,
        settings: Settings,
    ):
        super().__init__()
        self.settings = settings
        self.guild = guild

        # For this example, we'll use multiple sections to organize the settings.
        container = Container()
        header = TextDisplay(
            "# Anzen Settings\n-# Configure where and what Anzen will log."
        )
        container.add_item(header)
        container.add_item(Separator(spacing=SeparatorSpacing.large))

        container.add_item(
            TextDisplay(
                "## Category Selection\n-# This optionally filters channels for Channel Selection."
            )
        )
        container.add_item(CategorySetting(self.settings, id=100))
        container.add_item(
            TextDisplay(
                "## Channel Selection\n-# This is the channel where the logs will be sent."
            )
        )
        container.add_item(ChannelSetting(self.guild, self.settings, id=101))
        container.add_item(
            TextDisplay(
                "## Mod Role\n-# Optionally select a role to ping on notifications."
            )
        )
        select_row = RoleSelectRow(self.settings, id=102)
        button_row = RoleButtonRow(select_row, id=103)
        container.add_item(select_row)
        container.add_item(button_row)
        container.add_item(
            TextDisplay(
                "## Coming Soon\n-# Further options such as default behaviour are coming soon."
            )
        )
        self.add_item(container)

        # Swap the row so it's at the end
        self.remove_item(self.row)
        self.add_item(self.row)

    @row.button(label="Finish", style=ButtonStyle.green)
    async def finish_button(self, interaction: Interaction, button: Button) -> None:
        if self.settings.channel is None or self.settings.channel == "0":
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                "Please select a valid channel.", ephemeral=True
            )
            return
        # Edit the message to make it the interaction response...
        await interaction.response.edit_message(view=self)
        # Save the settings:
        async with self.sessionmanager.session() as db:
            await self.config.upsert(
                db,
                self.guild.id,
                logchannel_id=int(self.settings.channel),
                modrole_ids=[int(rid) for rid in self.settings.modroles],
                moduser_ids=[int(uid) for uid in self.settings.modusers],
                log_all_bans=self.settings.log_all_bans,
                log_all_reasons=self.settings.log_all_reasons,
                log_bans_override=self.settings.log_bans_override,
                log_reasons_override=self.settings.log_reasons_override,
            )
        # ...and then send a confirmation message.
        await interaction.followup.send("Settings saved.", ephemeral=True)
        # Then delete the settings panel
        self.stop()
        await interaction.delete_original_response()


def _placeholder_page(title: str) -> Container:
    """Simple stand-in page to display while I'm building content for this page."""
    return Container(TextDisplay(f"# {title}\n-# Coming soon."))


class SettingsView(LayoutView):
    row = ActionRow()

    def __init__(
        self,
        sessionmanager: DatabaseSessionManager,
        config: Config,
        guild: Guild,
        settings: Settings,
        *args,
        **kwargs,
    ):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.message = None
        self.sessionmanager = sessionmanager
        self.config = config
        self.guild = guild
        self.settings = settings

        # Every page must be a UI item
        self.pages: list[Container] = [
            ChannelPage(guild=guild, settings=settings),
            BanSettingsPage(settings=settings),
            PingSettingsPage(settings=settings),
        ]

        self.current_page = 0
        self.page_content: Container | None = None

        # Render the first page and put it in the view.
        self._show_page(self.current_page)

    def _show_page(self, index: int) -> None:
        """Swap the currently displayed page container for a new one.

        Has to call remove_item/add_item on the view to actually display.
        """
        if self.page_content is not None:
            self.remove_item(self.page_content)

        # `row` is declared at class level, so it's already present in
        # self.children from construction onward. Pull it out and re-add
        # it after the new page so it stays pinned at the bottom. We use the
        # same trick in trick ChannelPageView.__init__.
        self.remove_item(self.row)

        self.current_page = index
        self.page_content = self.pages[index]

        self.add_item(self.page_content)
        self.add_item(self.row)

        self.row.children[0].disabled = self.current_page == 0
        self.row.children[1].disabled = self.current_page == len(self.pages) - 1

    @row.button(
        label="◀️ Previous",
        style=discord.ButtonStyle.secondary,
        disabled=True,
        custom_id="prev",
    )
    async def prev_button(self, interaction: Interaction, button: Button):
        try:
            self._show_page(max(0, self.current_page - 1))
            await interaction.response.edit_message(view=self)
        except discord.HTTPException as e:
            self.logger.error(f"Prev failed: {e}")
            await interaction.response.send_message(
                "Navigation failed!", ephemeral=True
            )

    @row.button(label="Finish", style=discord.ButtonStyle.green, custom_id="finish")
    async def finish_button(self, interaction: Interaction, button: Button) -> None:
        if self.settings.channel is None or self.settings.channel == "0":
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                "Please select a valid channel.", ephemeral=True
            )
            return
        # Edit the message to make it the interaction response...
        await interaction.response.edit_message(view=self)
        # Save the settings:
        async with self.sessionmanager.session() as db:
            await self.config.upsert(
                db,
                self.guild.id,
                logchannel_id=int(self.settings.channel),
                modrole_ids=[int(rid) for rid in self.settings.modroles],
                moduser_ids=[int(uid) for uid in self.settings.modusers],
                log_all_bans=self.settings.log_all_bans,
                log_all_reasons=self.settings.log_all_reasons,
                log_bans_override=self.settings.log_bans_override,
                log_reasons_override=self.settings.log_reasons_override,
            )
        # ...and then send a confirmation message.
        await interaction.followup.send("Settings saved.", ephemeral=True)
        # Then delete the settings panel
        self.stop()
        await interaction.delete_original_response()

    @row.button(label="Next ▶️", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_button(self, interaction: Interaction, button: Button):
        try:
            self._show_page(min(len(self.pages) - 1, self.current_page + 1))
            await interaction.response.edit_message(view=self)
        except discord.HTTPException as e:
            self.logger.error(f"Next failed: {e}")
            await interaction.response.send_message(
                "Navigation failed!", ephemeral=True
            )
