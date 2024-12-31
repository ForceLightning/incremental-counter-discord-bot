import json
import os
import warnings
from enum import Enum, auto
from io import TextIOWrapper
from typing import Any

import discord
from discord.ext import commands
from discord.ext.commands.context import Context
from discord.message import Message
from discord.ui import Item


class ConfirmDeny(Enum):
    CONFIRM = auto()
    DENY = auto()


class ButtonType(Enum):
    INCREMENT = auto()
    DECREMENT = auto()


def create_count_embed(
    count: int,
    description: str = "Counting the number of times squid uses 'slay' unironically.",
) -> discord.Embed:
    """Creates a counting embed."""
    field = discord.EmbedField(name="Value", value=str(count))
    embed = discord.Embed(
        title="Current count", description=description, fields=[field]
    )
    return embed


class ConfirmationView(discord.ui.View):
    """A confirmation/denial view for certain overwriting operations."""

    def __init__(
        self,
        *items: Item,
        timeout: float | None = 180,
        disable_on_timeout: bool = False,
    ):
        super().__init__(*items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        # Set default value to DENY.
        self.value: ConfirmDeny = ConfirmDeny.DENY

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.primary, emoji="✅")
    async def confirm_callback(self, button, interaction: discord.Interaction):
        self.value = ConfirmDeny.CONFIRM
        await interaction.response.send_message("Confirming...", ephemeral=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.secondary, emoji="❌")
    async def deny_callback(self, button, interaction: discord.Interaction):
        self.value = ConfirmDeny.DENY
        await interaction.response.send_message("Denying...", ephemeral=True)


class IncrementButton(discord.ui.Button):
    """A button that can increment/decrement a count for any view."""

    def __init__(self, guild_id: int, message_id: int | None, type: ButtonType):
        match type:
            case ButtonType.INCREMENT:
                style = discord.ButtonStyle.primary
                label = "+1"
                emoji = "➕"
            case ButtonType.DECREMENT:
                style = discord.ButtonStyle.secondary
                label = "-1"
                emoji = "➖"

        super().__init__(
            label=label,
            style=style,
            emoji=emoji,
            custom_id=f"{guild_id}::{type}",
        )
        self.guild_id = guild_id
        self.message_id: int
        if message_id:
            self.message_id = message_id
        self.button_type = type
        self.cache: dict[str, Any]
        if not os.path.exists("cache.json"):
            with open("cache.json", "w", encoding="utf-8") as f:
                self.cache = {}
                json.dump(self.cache, f, sort_keys=True)
                return

        with open("cache.json", "r+", encoding="utf-8") as f:
            try:
                self.cache = json.load(f)
            except json.JSONDecodeError:
                self.cache = {}
                warnings.warn(
                    "JSON decode failed, silently overwriting to empty dict.",
                    stacklevel=1,
                )
                f.seek(0)
                f.truncate(0)
                json.dump(self.cache, f, sort_keys=True)

    async def save_cache(self):
        with open("cache.json", "r+", encoding="utf-8") as f:
            f.seek(0)
            f.truncate(0)
            json.dump(self.cache, f, sort_keys=True, indent=2)

    def post_init_message_id(self, message_id: int):
        self.message_id = message_id

    async def callback(self, interaction: discord.Interaction):
        with open("cache.json", "r", encoding="utf-8") as f:
            self.cache = json.load(f)
        assert interaction.guild_id is not None
        # NOTE: This button should not even exist if the initial pinned message is not set.
        try:
            assert interaction.channel is not None
            assert isinstance(interaction.channel, discord.TextChannel)
            message = await interaction.channel.fetch_message(self.message_id)
            match self.button_type:
                case ButtonType.INCREMENT:
                    self.cache[str(interaction.guild_id)]["count"] += 1
                case ButtonType.DECREMENT:
                    self.cache[str(interaction.guild_id)]["count"] -= 1

            count = self.cache[str(interaction.guild_id)]["count"]
            await self.save_cache()
            embed = create_count_embed(count)
            await message.edit(embed=embed)
            await interaction.response.send_message("Count updated.", ephemeral=True)

        except discord.NotFound:
            await interaction.response.send_message(
                "Original pinned message not found. Resetting state.",
                ephemeral=True,
            )
            self.cache[str(interaction.guild_id)] = {}
            await self.save_cache()
            return
        except discord.Forbidden:
            await interaction.response.send_message(
                "Original pinned message is no longer accessible by the bot. Resetting state.",
                ephemeral=True,
            )
            self.cache[str(interaction.guild_id)] = {}
            await self.save_cache()
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"HTTP error with code: {e.status}. Try again later.", ephemeral=True
            )
            return
        except Exception as e:
            raise e


class Counting(commands.Cog, name="Counting"):
    """Counting cog."""

    def __init__(self, bot):
        self.bot = bot
        self.cache: dict[str, Any]
        if not os.path.exists("cache.json"):
            with open("cache.json", "w", encoding="utf-8") as f:
                self.cache = {}
                json.dump(self.cache, f, sort_keys=True, indent=True)

    @commands.slash_command(
        description="Initialises the count for the server.", guild_only=True
    )
    async def init_counter(self, ctx: "Context", initial_value: int):
        assert ctx.guild is not None

        # Initialise for the guild and channel if not set.
        if not os.path.exists("cache.json"):
            with open("cache.json", "w", encoding="utf-8") as f:
                embed = create_count_embed(initial_value)
                message = await ctx.send(embed=embed)

                self.cache = {
                    str(ctx.guild.id): {
                        "count": initial_value,
                        "message_id": message.id,
                    }
                }

                json.dump(self.cache, f, sort_keys=True, indent=True)

        else:
            with open("cache.json", "r+", encoding="utf-8") as f:
                self.cache = json.load(f)
                if (guild_entry := self.cache.get(str(ctx.guild.id), None)) is not None:
                    if isinstance(guild_entry, dict):
                        if (count := guild_entry.get("count", None)) is not None and (
                            message_id := guild_entry.get("message_id", None)
                        ) is not None:
                            await self.handle_override(
                                ctx, count, message_id, initial_value, f
                            )

                await self.create_count(ctx, initial_value, f)
                return

    async def handle_override(
        self,
        ctx: "Context",
        count: int,
        message_id: int,
        initial_value: int,
        f: TextIOWrapper,
    ):
        """Handles the case where an original counting message exists and will be overwritten."""
        # GUARD: Check that the original count message can be retrieved.
        assert isinstance(ctx.channel, discord.TextChannel)
        par_msg = ctx.channel.get_partial_message(message_id)
        try:
            count_msg = await par_msg.fetch()
            cd_view = ConfirmationView(timeout=15, disable_on_timeout=True)
            confirmation_msg = await ctx.reply(
                f"A value has already been set: {count}. Are you sure you want to override to {initial_value}?",
                view=cd_view,
            )
            await cd_view.wait()

            if cd_view.value == ConfirmDeny.DENY:
                await confirmation_msg.delete(reason="Confirmation cancelled.")
                return

            await confirmation_msg.edit(
                content=f"Initialising value to {initial_value}.",
                view=None,
            )

            await self.update_count(ctx, initial_value, count_msg, f)

            return
        except (discord.NotFound, discord.Forbidden):
            await ctx.reply(
                "The original counting message could not be found. Check the bot's permissions and whether the original message exists. Resetting state."
            )
            self.cache[str(ctx.guild.id)] = {}
        except discord.HTTPException as e:
            await ctx.reply(f"HTTP error with code: {e.status}. Try again later.")
            return

    async def update_count(
        self, ctx: "Context", count: int, count_msg: Message, file: TextIOWrapper
    ):
        """Handles the case where the count is simply updated."""
        embed = create_count_embed(count)
        await count_msg.edit(embed=embed)
        self.cache[str(ctx.guild.id)] = {
            "count": count,
            "message_id": count_msg.id,
        }

        file.seek(0)
        file.truncate(0)
        json.dump(self.cache, file, sort_keys=True, indent=2)

    async def create_count(self, ctx: "Context", count: int, file: TextIOWrapper):
        """Handles the case where a new count needs to be created."""
        embed = create_count_embed(count)
        view = discord.ui.View(timeout=None)
        decrement = IncrementButton(ctx.guild.id, None, ButtonType.DECREMENT)
        increment = IncrementButton(ctx.guild.id, None, ButtonType.INCREMENT)
        view.add_item(decrement)
        view.add_item(increment)
        count_msg = await ctx.reply(embed=embed, view=view)
        decrement.post_init_message_id(count_msg.id)
        increment.post_init_message_id(count_msg.id)
        self.cache[str(ctx.guild.id)] = {
            "count": count,
            "message_id": count_msg.id,
        }

        file.seek(0)
        file.truncate(0)
        json.dump(self.cache, file, sort_keys=True, indent=2)

    @commands.Cog.listener()
    async def on_ready(self):
        """Attach the views to the persistent buttons."""
        with open("cache.json", "r+", encoding="utf-8") as f:
            try:
                self.cache = json.load(f)
            except json.JSONDecodeError:
                self.cache = {}
                warnings.warn(
                    "JSON decode failed, silently overwriting to empty dict.",
                    stacklevel=2,
                )
                f.seek(0)
                f.truncate(0)
                json.dump(self.cache, f, sort_keys=True)

            for guild_id, guild_entries in self.cache.items():
                view = discord.ui.View(timeout=None)
                if (
                    "count" in guild_entries.keys()
                    and "message_id" in guild_entries.keys()
                ):
                    decrement = IncrementButton(
                        int(guild_id), guild_entries["message_id"], ButtonType.DECREMENT
                    )
                    increment = IncrementButton(
                        int(guild_id), guild_entries["message_id"], ButtonType.INCREMENT
                    )
                    view.add_item(decrement)
                    view.add_item(increment)
                    self.bot.add_view(view)


def setup(bot):
    bot.add_cog(Counting(bot))
