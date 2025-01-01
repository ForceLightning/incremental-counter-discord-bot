import logging
import sqlite3
import warnings
from enum import Enum, auto

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
        await interaction.response.send_message(
            "Confirming...", ephemeral=True, delete_after=15
        )

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.secondary, emoji="❌")
    async def deny_callback(self, button, interaction: discord.Interaction):
        self.value = ConfirmDeny.DENY
        await interaction.response.send_message(
            "Denying...", ephemeral=True, delete_after=15
        )


class IncrementButton(discord.ui.Button):
    """A button that can increment/decrement a count for any view."""

    def __init__(
        self,
        guild_id: int,
        message_id: int | None,
        type: ButtonType,
        con: sqlite3.Connection,
    ):
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

    def post_init_message_id(self, message_id: int):
        self.message_id = message_id

    async def callback(self, interaction: discord.Interaction):
        assert interaction.guild_id is not None
        # NOTE: This button should not even exist if the initial pinned message is not set.
        con = sqlite3.connect("cache.db")
        cur = con.cursor()
        try:
            assert interaction.channel is not None
            assert isinstance(interaction.channel, discord.TextChannel)
            assert interaction.user is not None
            message = await interaction.channel.fetch_message(self.message_id)
            update_query = "UPDATE counting SET count = count {} 1, active = TRUE WHERE server_id = ?"
            match self.button_type:
                case ButtonType.INCREMENT:
                    update_query = update_query.format("+")
                case ButtonType.DECREMENT:
                    update_query = update_query.format("-")

            cur.execute(update_query, (self.guild_id,))
            con.commit()
            select_query = "SELECT count FROM counting WHERE server_id = ?"
            count, *_ = cur.execute(select_query, (self.guild_id,)).fetchone()
            con.commit()
            embed = create_count_embed(count)
            await message.edit(embed=embed)
            await interaction.response.send_message(
                "Count updated.", ephemeral=True, delete_after=15
            )

            # Log the event.
            logging.info(
                "Server %d: %s %s the count",
                interaction.guild_id,
                (
                    interaction.user.global_name
                    if interaction.user.global_name is not None
                    else interaction.user.id
                ),
                (
                    "incremented"
                    if self.button_type == ButtonType.INCREMENT
                    else "decremented"
                ),
            )

        except discord.NotFound as e:
            await interaction.response.send_message(
                "Original pinned message not found. Resetting state.",
                ephemeral=True,
                delete_after=15,
            )
            cur.execute(
                "UPDATE counting SET active = FALSE WHERE server_id = ?",
                (self.guild_id,),
            )
            con.commit()
            logging.error("%s: message with id: %d not found.", e, self.message_id)
        except discord.Forbidden as e:
            await interaction.response.send_message(
                "Original pinned message is no longer accessible by the bot. Resetting state.",
                ephemeral=True,
                delete_after=15,
            )
            cur.execute(
                "UPDATE counting SET active = FALSE WHERE server_id = ?",
                (self.guild_id,),
            )
            con.commit()
            logging.error("%s: message with id: %d forbidden.", e, self.message_id)
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"HTTP error with code: {e.status}. Try again later.",
                ephemeral=True,
                delete_after=15,
            )
            logging.error("%s: HTTP error %d.", e, e.status)
        except Exception as e:
            logging.error("%s", e)
            raise e
        finally:
            con.close()


class Counting(commands.Cog, name="Counting"):
    """Counting cog."""

    def __init__(self, bot):
        self.bot = bot
        self.con = sqlite3.connect("cache.db")
        self.cur = self.con.cursor()
        self.cur.execute(
            "CREATE TABLE IF NOT EXISTS counting(server_id INTEGER PRIMARY KEY, message_id INTEGER, count INTEGER, active BOOLEAN NOT NULL CHECK (active IN (0, 1)))"
        )
        self.con.commit()

    async def cog_before_invoke(self, ctx):
        self.con = sqlite3.connect("cache.db")
        self.cur = self.con.cursor()

    async def cog_after_invoke(self, ctx):
        self.con.close()
        del self.cur

    @commands.slash_command(description="Initialises the count for the server.")
    async def init_counter(self, ctx: "Context", initial_value: int):
        assert ctx.guild is not None

        res: tuple[int, int, int, bool] | None = self.cur.execute(
            "SELECT * FROM counting WHERE ? = server_id", (ctx.guild.id,)
        ).fetchone()
        if res is None:
            await self.create_count(ctx, initial_value)
        else:
            await self.handle_override(ctx, res[2], res[1], initial_value)

    async def handle_override(
        self,
        ctx: "Context",
        count: int,
        message_id: int,
        initial_value: int,
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

            await self.update_count(ctx, initial_value, count_msg)

            return
        except (discord.NotFound, discord.Forbidden) as e:
            await ctx.reply(
                "The original counting message could not be found. Check the bot's permissions and whether the original message exists. Resetting state."
            )
            await self.create_count(ctx, initial_value)
            warnings.warn(
                f"{e}: Message with id: {message_id} not found or not accessible.",
                stacklevel=2,
            )
        except discord.HTTPException as e:
            await ctx.reply(f"HTTP error with code: {e.status}. Try again later.")
            return

    async def update_count(self, ctx: "Context", count: int, count_msg: Message):
        """Handles the case where the count is simply updated."""
        embed = create_count_embed(count)
        await count_msg.edit(embed=embed)
        self.cur.execute(
            "UPDATE counting SET message_id = ?, count = ?, active = TRUE WHERE server_id = ?",
            (count_msg.id, count, ctx.guild.id),
        )
        self.con.commit()

    async def create_count(self, ctx: "Context", count: int):
        """Handles the case where a new count needs to be created."""
        embed = create_count_embed(count)
        view = discord.ui.View(timeout=None)
        decrement = IncrementButton(
            ctx.guild.id, None, ButtonType.DECREMENT, sqlite3.connect("cache.db")
        )
        increment = IncrementButton(
            ctx.guild.id, None, ButtonType.INCREMENT, sqlite3.connect("cache.db")
        )
        view.add_item(decrement)
        view.add_item(increment)
        count_msg = await ctx.reply(embed=embed, view=view)
        decrement.post_init_message_id(count_msg.id)
        increment.post_init_message_id(count_msg.id)
        if (
            self.cur.execute(
                "SELECT * FROM counting WHERE server_id = ?", (ctx.guild.id,)
            ).fetchone()
            is None
        ):
            self.cur.execute(
                "INSERT INTO counting (server_id, message_id, count, active) VALUES (?, ?, ?, TRUE)",
                (ctx.guild.id, count_msg.id, count),
            )
        else:
            self.cur.execute(
                "UPDATE counting SET message_id = ?, count = ?, active = TRUE WHERE server_id = ?",
                (count_msg.id, count, ctx.guild.id),
            )
        self.con.commit()

    @commands.Cog.listener()
    async def on_ready(self):
        """Attach the views to the persistent buttons."""
        res: list[tuple[int, int]] = self.cur.execute(
            "SELECT server_id, message_id FROM counting WHERE active = TRUE"
        ).fetchall()
        for server_id, message_id in res:
            view = discord.ui.View(timeout=None)
            decrement = IncrementButton(
                server_id, message_id, ButtonType.DECREMENT, sqlite3.connect("cache.db")
            )
            view.add_item(decrement)
            increment = IncrementButton(
                server_id, message_id, ButtonType.INCREMENT, sqlite3.connect("cache.db")
            )
            view.add_item(increment)
            self.bot.add_view(view)
        self.con.close()


def setup(bot):
    bot.add_cog(Counting(bot))
