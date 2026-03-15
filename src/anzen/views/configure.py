from __future__ import annotations

import enum
import logging
import os
import traceback
from typing import Callable, List, Optional, Union

import attr
import discord
from discord import (
    ButtonStyle,
    CategoryChannel,
    ChannelType,
    Guild,
    Interaction,
    Member,
    PartialMessageable,
    Role,
    SelectDefaultValue,
    SelectDefaultValueType,
    SelectOption,
    SeparatorSpacing,
    TextStyle,
    User,
    ui,
)
from discord.ext import commands
from discord.ui import (
    ActionRow,
    Button,
    ChannelSelect,
    Container,
    Label,
    LayoutView,
    Modal,
    Select,
    Separator,
    TextDisplay,
    TextInput,
    View,
)
from pydantic import BaseModel, ConfigDict

from anzen.data.database import DatabaseSessionManager
from anzen.data.datamodel import Config


# This is where we'll store our intermediate settings.
class Settings(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    category: PartialMessageable | None = None
    channel: str | None = (
        None  # channel id in as str # TODO: add channel as partialmessageable?
    )
    modrole: str | None = None
    # roles: list[Role] = pydantic_field(default_factory=list)
    # members: List[Union[Member, User]] = pydantic_field(default_factory=list)
    log_all_bans: bool = True
    log_all_reasons: bool = True
    log_bans_override: str = "--no-log"
    log_reasons_override: str = "--no-reason"

    _category_callbacks: list[Callable] = []

    def on_category_change(self, callback: Callable):
        """Register a callback to fire when category changes"""
        self._category_callbacks.append(callback)
        return callback  # allows use as decorator

    def __setattr__(self, name, value):
        if name == "category" and hasattr(self, "_category_callbacks"):
            old_value = getattr(self, "category", None)
            super().__setattr__(name, value)
            if old_value != value:
                for callback in self._category_callbacks:
                    callback(old_value, value)
        else:
            super().__setattr__(name, value)


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
                options += [SelectOption(label=ch.name, value=ch.id) for ch in channels]
                break
            if cat is None or cat.id != target_category_id:
                continue
            options += [SelectOption(label=ch.name, value=ch.id) for ch in channels]
            break
        if not options:  # Fallback
            options = [SelectOption(label="No channels available", value="0")]
        return options[:25]

    def update_options(
        self, old_category: PartialMessageable, new_category: PartialMessageable
    ) -> None:
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
        await interaction.response.defer()
        # await interaction.response.edit_message()
        #     print(self.settings.channel)
        #     for option in self.options:
        #         option.default = option.value == self.values[0]
        # await interaction.response.edit_message(view=self.view)


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
        sessionmanager: DatabaseSessionManager,
        config: Config,
        guild: Guild,
        settings: Settings,
    ):
        super().__init__()
        self.settings = settings
        self.guild = guild
        self.sessionmanager = sessionmanager
        self.config = config

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
                modrole_id=int(self.settings.modrole)
                if self.settings.modrole
                else None,
            )
        # ...and then send a confirmation message.
        await interaction.followup.send("Settings saved.", ephemeral=True)
        # Then delete the settings panel
        self.stop()
        await interaction.delete_original_response()


class SettingsView(LayoutView):
    row = ActionRow()

    def __init__(self, guild: Guild, settings: Settings, *args, **kwargs):
        super().__init__()
        self.pages = ["a", ChannelPage(guild=guild, settings=settings), "c"]
        self.current_page = 0
        self.message = None
        self.logger = logging.getLogger(__name__)

        self.page_content = Container(TextDisplay("Welcome!"))

    def _refresh_page(self, page):
        self.remove_item(self.page_content)
        self.add_item(self.page_content)

        self.remove_item(self.row)
        self.add_item(self.row)

    @row.button(
        label="◀️ Previous",
        style=discord.ButtonStyle.secondary,
        disabled=True,
        custom_id="prev",
    )
    async def prev_button(self, interaction: Interaction, button: Button):
        try:
            self.current_page = max(0, self.current_page - 1)
            await self.update_buttons(interaction)
        except discord.HTTPException as e:
            self.logger.error(f"Prev failed: {e}")
            await interaction.response.send_message(
                "Navigation failed!", ephemeral=True
            )

    @row.button(label="Next ▶️", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_button(self, interaction: Interaction, button: Button):
        try:
            self.current_page = min(len(self.pages) - 1, self.current_page + 1)
            await self.update_buttons(interaction)
        except discord.HTTPException as e:
            self.logger.error(f"Next failed: {e}")
            await interaction.response.send_message(
                "Navigation failed!", ephemeral=True
            )

    async def update_buttons(self, interaction: Interaction):
        try:
            self.row.children[0].disabled = self.current_page == 0
            self.row.children[1].disabled = self.current_page == len(self.pages) - 1
            print(self.pages[self.current_page])
            self.page_content = self.pages[self.current_page]
            await interaction.response.edit_message(view=self)
        except discord.HTTPException as e:
            self.logger.error(f"Pagination update failed: {e}")
