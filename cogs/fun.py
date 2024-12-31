import json
import os
import random
from typing import Any

import numpy as np
from discord.ext import commands
from discord.ext.commands.context import Context


class Fun(commands.Cog, name="Fun"):

    cache: dict[str, Any]

    def __init__(self, bot):
        self.bot = bot
        if not os.path.exists("cache.json"):
            with open("cache.json", "w", encoding="utf-8") as f:
                f.write("")

        with open("cache.json", "r+", encoding="utf-8") as f:
            try:
                self.cache = json.load(f)
            except json.JSONDecodeError:
                self.cache = {}

    async def save_cache(self):
        with open("cache.json", "r+", encoding="utf-8") as f:
            f.seek(0)
            f.truncate(0)
            json.dump(self.cache, f, sort_keys=True)

    @commands.slash_command()
    async def roll(self, ctx, dice: str):
        """Rolls dice in NdM format."""
        try:
            (rolls, limit) = map(int, dice.split("d"))
        except Exception:
            await ctx.reply("Format has to be in NdN!")
            return
        result = ", ".join((str(random.randint(1, limit)) for _ in range(rolls)))
        try:
            await ctx.reply(result)
        except Exception:
            await ctx.reply("Maximum length of bot text is 2000 characters")
            return

    @commands.slash_command()
    async def choose(self, ctx, *choices: str):
        """For when you wanna settle the score some other way."""
        await ctx.reply(random.choice(choices))

    @commands.slash_command(description="Turtle!")
    @commands.cooldown(1, 15, type=commands.BucketType.user)
    async def turtle(self, ctx):
        """Global ecologies depend on this."""
        await ctx.reply(
            random.choice(
                [
                    "🌊🐢🐢 A turtle made it to the water!",
                    " 🦀🐢🦀 The cycle of life can be cruel...",
                ]
            )
        )

    @commands.slash_command()
    async def r8(self, ctx, *, input_string: str):
        """i r8 something out of 8 m8"""
        randomNumber = random.randint(0, 8)
        await ctx.reply("i r8 {} {}/8 m8".format(input_string, randomNumber))

    @commands.slash_command()
    async def how(self, ctx, *, input_string: str):
        """Determines how great or terrible something is
        Usage: /how adjective <is/are/was/were> subject"""
        splitters = [" is ", " are ", " was ", " were "]
        sec_splitters = [" to ", " of "]
        flag = False
        string_splitter = ""
        for split in splitters[::(-1)]:
            if split in input_string:
                string_splitter = split  # structure is &how adjective is subject
                flag = True  # return subject is x% adjective
        if flag:
            splitter = input_string.find(string_splitter)
            adjective = input_string[:splitter]
            subject = input_string[splitter + len(string_splitter) :]
            for sec_split in sec_splitters:
                if sec_split in subject:
                    splitter = subject.find(sec_split)
                    adjective += f"{sec_split}" + subject[splitter + len(sec_split) :]
                    subject = subject[:splitter]
            percent = -1
            while percent < 0 or percent > 120:
                percent = int(random.gauss(50, 70))
            s_percent = ""
            if percent > 110:
                percent = random.randint(110, 300)
            s_percent = str(percent)
            sign = ""
            if random.randint(0, 9) <= 2:
                sign = "-"
            if percent == 69:
                s_percent = ":six::nine:"
            await ctx.reply(
                "{subject}{splitter}{sign}{percent}% {adjective}".format(
                    subject=subject,
                    splitter=string_splitter,
                    sign=sign,
                    percent=s_percent,
                    adjective=adjective,
                )
            )
        else:
            await ctx.reply(
                '```Input must have the "adjective is/are/was/were subject" syntax```'
            )

    @commands.slash_command(aliases=["3dbox"])
    async def box(self, ctx: "Context", *, sentence: str):
        """🎲"""
        if len(sentence) % 2 == 1:
            diags = len(sentence) // 2 // 2
        else:
            diags = len(sentence[: len(sentence) // 2]) - 2
        ret = np.full(
            (len(sentence) + diags + 1, len(sentence) + diags + 1), " ", dtype=str
        )
        ret[0, : len(sentence)] = list(sentence)
        ret[: len(sentence), 0] = list(sentence)
        ret[len(sentence) - 1, : len(sentence)] = list(sentence)[::-1]
        ret[: len(sentence), len(sentence) - 1] = list(sentence)[::-1]
        ret = np.roll(ret, diags + 1, axis=0)
        ret = np.roll(ret, diags + 1, axis=1)
        ret[0, : len(sentence)] = list(sentence)
        ret[: len(sentence), 0] = list(sentence)
        ret[len(sentence) - 1, : len(sentence)] = list(sentence)[::-1]
        ret[: len(sentence), len(sentence) - 1] = list(sentence)[::-1]
        for i in range(diags):
            char = "╲"
            ret[i + 1, i + 1] = char
            ret[i + 1, len(sentence) + i] = char
            ret[len(sentence) + i, i + 1] = char
            ret[len(sentence) + i, len(sentence) + i] = char
        r = [" ".join(row).rstrip() for row in ret]
        r = "\n".join(r)
        r.replace("    ", "\t")
        await ctx.reply("```\n{}\n```".format(r))

    @box.error
    async def get_error_handler(self, ctx, error):
        await ctx.reply("```py\n{}: {}\n```".format(type(error).__name__, str(error)))

    @commands.slash_command()
    async def clap(self, ctx, *, sentence: str):
        """Claps 👏 because 👏 they 👏 are 👏 necessary 👏"""
        words = sentence.split()
        msg = " 👏 ".join(words)
        msg += " 👏"
        await ctx.reply(msg)

    @commands.slash_command()
    async def mock(self, ctx, *, sentence):
        """bECAUsE pEOpLe sAy StUpid shIt"""
        new_sentence = ""
        sentence = sentence.lower()
        for c in range(len(sentence)):
            if random.randint(0, 1):
                new_sentence += sentence[c].upper()
            else:
                new_sentence += sentence[c]
        await ctx.reply(new_sentence)


def setup(bot):
    bot.add_cog(Fun(bot))
