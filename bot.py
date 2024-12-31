import configparser
import os

import discord
from discord.ext import bridge, commands

description = "A discord bot to count the unironic use of 'slay'."

if not os.path.exists("settings.ini"):
    with open("settings.ini", "xt", encoding="utf-8") as f:
        f.writelines(
            [
                "[BASE]",
                "prefix = !",
                "[EXTENSIONS]",
                "cogs.fun = 0",
                "cogs.count = 0",
                "[SECRET]",
                "token = ",
                "[ADMIN_COMMANDS_GUILDS]",
            ]
        )

    raise RuntimeError(
        "Configure your settings.ini file first before restarting the bot."
    )

config = configparser.ConfigParser()
config.read("settings.ini")

intents = discord.Intents()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.reactions = True

bot = bridge.Bot(
    command_prefix=config["BASE"]["prefix"],
    description=description,
    help_command=None,
    intents=intents,
)
startup_extensions = list(config["EXTENSIONS"])
admin_commands_guilds = list(config["ADMIN_COMMANDS_GUILDS"])
TOKEN = config["SECRET"]["TOKEN"]


@bot.event
async def on_ready():
    assert bot.user is not None
    print("Logged in as")
    print(bot.user.name)
    print(bot.user.id)
    print("------")
    await bot.change_presence(activity=discord.Game(name="with 🦑"))


@bot.slash_command(hidden=True, guild_ids=admin_commands_guilds)
@commands.is_owner()
async def load(ctx, extension_name: str):
    "Loads an extension."
    member = ctx.author
    bot_info = await bot.application_info()
    if member == bot_info.owner:
        try:
            bot.load_extension(extension_name)
        except Exception as e:
            await ctx.respond("```py\n{}: {}\n```".format(type(e).__name__, str(e)))
            return
        await ctx.respond("{} loaded.".format(extension_name))
    else:
        await ctx.respond("{} is not bot owner!".format(member.mention))


@bot.slash_command(hidden=True, guild_ids=admin_commands_guilds)
@commands.is_owner()
async def unload(ctx, extension_name: str):
    "Unloads an extension."
    member = ctx.author
    bot_info = await bot.application_info()
    if member == bot_info.owner:
        bot.unload_extension(extension_name)
        await ctx.respond("{} unloaded.".format(extension_name))
    else:
        await ctx.respond("{} is not bot owner!".format(member.mention))


@bot.slash_command(hidden=True, guild_ids=admin_commands_guilds)
@commands.is_owner()
async def reload(ctx, extension_name: str):
    "Reloads an extension."
    member = ctx.author
    bot_info = await bot.application_info()
    if member == bot_info.owner:
        try:
            bot.unload_extension(extension_name)
            bot.load_extension(extension_name)
        except (AttributeError, ImportError) as e:
            await ctx.respond("```py\n{}: {}\n```".format(type(e).__name__, str(e)))
            return
        await ctx.respond("{} reloaded.".format(extension_name))
    else:
        await ctx.respond("{} is not bot owner!".format(member.mention))


@bot.slash_command(hidden=True, guild_ids=admin_commands_guilds)
async def owner(ctx):
    member = ctx.author
    bot_info = await bot.application_info()
    if member == bot_info.owner:
        await ctx.respond("{} is bot owner".format(member.mention))
    else:
        await ctx.respond("{} is not bot owner".format(member.mention))


if __name__ == "__main__":
    for extension in startup_extensions:
        try:
            bot.load_extension(extension)
        except Exception as e:
            exc = "{}: {}".format(type(e).__name__, e)
            print("Failed to load extension {}\n{}".format(extension, exc))
    bot.run(TOKEN)
