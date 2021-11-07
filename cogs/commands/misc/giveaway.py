import datetime
import random
import traceback

import discord
import humanize
import pytimeparse
from data.model.giveaway import Giveaway as GiveawayDB
from data.services.guild_service import guild_service
from discord.commands import Option, slash_command
from discord.ext import commands
from discord.utils import format_dt
from utils.config import cfg
from utils.context import BlooContext
from utils.permissions.checks import PermissionsFailure, admin_and_up
from utils.permissions.slash_perms import slash_perms
from utils.tasks import end_giveaway


class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.giveaway_messages = {}

    @admin_and_up()
    @slash_command(guild_ids=[cfg.guild_id], description="Start a giveaway.", permissions=slash_perms.admin_and_up())
    async def giveawaystart(self, ctx: BlooContext, name: Option(str, description="Name of the giveaway"), sponsor: Option(discord.Member, description="Who sponsored the giveaway"), time: Option(str, description="How long should the giveaway last?"), winners: Option(int, description="How many winners?"), channel: Option(discord.TextChannel, description="Where to post the giveaway")):
        delta = pytimeparse.parse(time)
        if delta is None:
            raise commands.BadArgument("Invalid time passed in.")

        if winners <= 0:
            raise commands.BadArgument("Must have more than 1 winner!")

        # calculate end time
        now = datetime.datetime.now()
        end_time = now + datetime.timedelta(seconds=delta)

        # prepare giveaway embed and post it in giveaway channel
        embed = discord.Embed(title="New giveaway!")
        embed.description = f"**{name}** is being given away by {sponsor.mention} to **{winners}** lucky {'winner' if winners == 1 else 'winers'}!"
        embed.add_field(name="Time remaining",
                        value=f"Expires in {format_dt(end_time, style='R')}")
        embed.timestamp = end_time
        embed.color = discord.Color.random()
        embed.set_footer(text="Ends")

        message = await channel.send(embed=embed)
        await message.add_reaction('🎉')

        # store giveaway in database
        giveaway = GiveawayDB(
            _id=message.id,
            channel=channel.id,
            name=name,
            winners=winners,
            end_time=end_time,
            sponsor=sponsor.id)
        giveaway.save()

        await ctx.send_success(f"Giveaway created!")

        ctx.tasks.schedule_end_giveaway(
            channel_id=channel.id, message_id=message.id, date=end_time, winners=winners)

    @admin_and_up()
    @slash_command(guild_ids=[cfg.guild_id], description="Pick a new winner of an already ended giveaway.", permissions=slash_perms.admin_and_up())
    async def giveawayreroll(self, ctx: BlooContext, message_id: str):

        g = guild_service.get_giveaway(_id=int(message_id))

        if g is None:
            raise commands.BadArgument(
                "Couldn't find an ended giveaway by the provided ID.")
        elif not g.is_ended:
            raise commands.BadArgument("That giveaway hasn't ended yet!")
        elif len(g.entries) == 0:
            raise commands.BadArgument(
                f"There are no entries for the giveaway of **{g.name}**.")
        elif len(g.entries) <= len(g.previous_winners):
            raise commands.BadArgument("No more winners are possible!")

        the_winner = None
        while the_winner is None:
            random_id = random.choice(g.entries)
            the_winner = ctx.guild.get_member(random_id)
            if the_winner is not None and the_winner.id not in g.previous_winners:
                break
            the_winner = None

        g.previous_winners.append(the_winner.id)
        g.save()

        channel = ctx.guild.get_channel(g.channel)

        await channel.send(f"**Reroll**\nThe new winner of the giveaway of **{g.name}** is {the_winner.mention}! Congratulations!")
        await ctx.send_success("Rerolled!")

    @admin_and_up()
    @slash_command(guild_ids=[cfg.guild_id], description="End a giveaway early.", permissions=slash_perms.admin_and_up())
    async def giveawayend(self, ctx: BlooContext, message_id: str):
        giveaway = guild_service.get_giveaway(_id=int(message_id))
        if giveaway is None:
            raise commands.BadArgument(
                "A giveaway with that ID was not found.")
        elif giveaway.is_ended:
            raise commands.BadArgument("That giveaway has already ended.")

        ctx.tasks.tasks.remove_job(str(int(message_id) + 2), 'default')
        await end_giveaway(giveaway.channel, message_id, giveaway.winners)

        await ctx.send_success("Giveaway ended!")

    async def do_giveaway_update(self, giveaway: GiveawayDB, guild: discord.Guild):
        if giveaway is None:
            return
        if giveaway.is_ended:
            return

        now = datetime.datetime.now()
        end_time = giveaway.end_time
        if end_time is None or end_time < now:
            return

        channel = guild.get_channel(giveaway.channel)

        # caching mechanism for each giveaway message so we don't get ratelimited by discord
        if giveaway._id in self.giveaway_messages:
            message = self.giveaway_messages[giveaway._id]
        else:
            try:
                message = await channel.fetch_message(giveaway._id)
                self.giveaway_messages[giveaway._id] = message
            except Exception:
                return

        if len(message.embeds) == 0:
            return

        embed = message.embeds[0]
        embed.set_field_at(0, name="Time remaining",
                           value=f"Less than {humanize.naturaldelta(end_time - now)}")
        await message.edit(embed=embed)

    @giveawaystart.error
    @giveawayreroll.error
    @giveawayend.error
    async def info_error(self,  ctx: BlooContext, error):
        if isinstance(error, discord.ApplicationCommandInvokeError):
            error = error.original

        if (isinstance(error, commands.MissingRequiredArgument)
            or isinstance(error, PermissionsFailure)
            or isinstance(error, commands.BadArgument)
            or isinstance(error, commands.BadUnionArgument)
            or isinstance(error, commands.MissingPermissions)
            or isinstance(error, commands.BotMissingPermissions)
            or isinstance(error, commands.MaxConcurrencyReached)
                or isinstance(error, commands.NoPrivateMessage)):
            await ctx.send_error(error)
        else:
            await ctx.send_error("A fatal error occured. Tell <@109705860275539968> about this.")
            traceback.print_exc()


def setup(bot):
    bot.add_cog(Giveaway(bot))
