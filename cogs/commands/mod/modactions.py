import traceback
from datetime import datetime, timedelta

import discord
import humanize
import pytimeparse
from data.model import Case
from data.services import guild_service, user_service
from discord.commands import Option, slash_command
from discord.commands.errors import ApplicationCommandInvokeError
from discord.ext import commands
from discord.utils import escape_markdown, escape_mentions
from utils import BlooContext, cfg
from utils.mod.mod_logs import *
from utils.mod.modactions_helpers import *
from utils.permissions import (PermissionsFailure, mod_and_up,
                               mods_and_above_external_resolver,
                               mods_and_above_member_resolver, slash_perms,
                               user_resolver)


class ModActions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @mod_and_up()
    @slash_command(guild_ids=[cfg.guild_id], description="Warn a user", permissions=slash_perms.mod_and_up())
    async def warn(self, ctx: BlooContext, user: Option(discord.Member, description="User to warn"), points: Option(int, description="Amount of points to warn for", min_value=1, max_value=600), reason: Option(str, description="Reason for warn", required=False) = "No reason."):
        """Warn a user (mod only)

        Example usage
        --------------
        !warn <@user/ID> <points> <reason (optional)>

        Parameters
        ----------
        user : discord.Member
            "The member to warn"
        points : int
            "Number of points to warn far"
        reason : str, optional
            "Reason for warning, by default 'No reason.'"

        """
        user = await mods_and_above_external_resolver(ctx, user)

        if points < 1:  # can't warn for negative/0 points
            raise commands.BadArgument(message="Points can't be lower than 1.")

        db_guild = guild_service.get_guild()

        reason = escape_markdown(reason)

        # prepare the case object for database
        case = Case(
            _id=db_guild.case_id,
            _type="WARN",
            mod_id=ctx.author.id,
            mod_tag=str(ctx.author),
            reason=reason,
            punishment=str(points)
        )

        # increment case ID in database for next available case ID
        guild_service.inc_caseid()
        # add new case to DB
        user_service.add_case(user.id, case)
        # add warnpoints to the user in DB
        user_service.inc_points(user.id, points)

        # fetch latest document about user from DB
        db_user = user_service.get_user(user.id)
        cur_points = db_user.warn_points

        # prepare log embed, send to #public-mod-logs, user, channel where invoked
        log = prepare_warn_log(ctx.author, user, case)
        log.add_field(name="Current points", value=cur_points, inline=True)

        # also send response in channel where command was called
        dmed = await notify_user_warn(ctx, user, db_user, db_guild, cur_points, log)
        await ctx.respond(embed=log, delete_after=10)
        await submit_public_log(ctx, db_guild, user, log, dmed)

    @mod_and_up()
    @slash_command(guild_ids=[cfg.guild_id], description="Kick a user", permissions=slash_perms.mod_and_up())
    async def kick(self, ctx: BlooContext, member: Option(discord.Member, description="User to kick"), *, reason: Option(str, description="Reason for kick", required=False) = "No reason.") -> None:
        """Kick a user (mod only)

        Example usage
        --------------
        !kick <@user/ID> <reason (optional)>

        Parameters
        ----------
        user : discord.Member
            "User to kick"
        reason : str, optional
            "Reason for kick, by default 'No reason.'"

        """

        member = await mods_and_above_member_resolver(ctx, member)

        reason = escape_markdown(reason)
        reason = escape_mentions(reason)

        db_guild = guild_service.get_guild()

        log = await add_kick_case(ctx, member, reason, db_guild)
        await notify_user(member, f"You were kicked from {ctx.guild.name}", log)

        await member.kick(reason=reason)

        await ctx.respond(embed=log, delete_after=10)
        await submit_public_log(ctx, db_guild, member, log)

    @mod_and_up()
    @slash_command(guild_ids=[cfg.guild_id], description="Kick a user", permissions=slash_perms.mod_and_up())
    async def roblox(self, ctx: BlooContext, member: Option(discord.Member, description="User to kick")) -> None:
        """Kick a user (mod only)

        Example usage
        --------------
        !kick <@user/ID> <reason (optional)>

        Parameters
        ----------
        user : discord.Member
            "User to kick"
        reason : str, optional
            "Reason for kick, by default 'No reason.'"

        """

        member = await mods_and_above_member_resolver(ctx, member)
        reason = "This Discord server is for iOS jailbreaking, not Roblox. Please join https://discord.gg/jailbreak instead, thank you!"

        db_guild = guild_service.get_guild()

        log = await add_kick_case(ctx, member, reason, db_guild)
        await notify_user(member, f"You were kicked from {ctx.guild.name}", log)

        await member.kick(reason=reason)

        await ctx.respond(embed=log, delete_after=10)
        await submit_public_log(ctx, db_guild, member, log)

    @mod_and_up()
    @slash_command(guild_ids=[cfg.guild_id], description="Mute a user", permissions=slash_perms.mod_and_up())
    async def mute(self, ctx: BlooContext, member: Option(discord.Member, description="User to mute"), dur: Option(str, description="Duration for mute", required=False) = "", reason: Option(str, description="Reason for mute", required=False) = "No reason.") -> None:
        """Mute a user (mod only)

        Example usage
        --------------
        !mute <@user/ID> <duration> <reason (optional)>

        Parameters
        ----------
        user : discord.Member
            "Member to mute"
        dur : str
            "Duration of mute (i.e 1h, 10m, 1d)"
        reason : str, optional
            "Reason for mute, by default 'No reason.'"

        """
        member = await mods_and_above_member_resolver(ctx, member)

        reason = escape_markdown(reason)
        reason = escape_mentions(reason)

        now = datetime.now()
        delta = pytimeparse.parse(dur)

        if delta is None:
            if reason == "No reason." and dur == "":
                reason = "No reason."
            elif reason == "No reason.":
                reason = dur
            else:
                reason = f"{dur} {reason}"

        mute_role = guild_service.get_guild().role_mute
        mute_role = ctx.guild.get_role(mute_role)

        if mute_role in member.roles:
            raise commands.BadArgument("This user is already muted.")

        db_guild = guild_service.get_guild()
        case = Case(
            _id=db_guild.case_id,
            _type="MUTE",
            date=now,
            mod_id=ctx.author.id,
            mod_tag=str(ctx.author),
            reason=reason,
        )

        if delta:
            try:
                time = now + timedelta(seconds=delta)
                case.until = time
                case.punishment = humanize.naturaldelta(
                    time - now, minimum_unit="seconds")
                ctx.tasks.schedule_unmute(member.id, time)
            except Exception as e:
                print(e)
                raise commands.BadArgument(
                    "An error occured, this user is probably already muted")
        else:
            case.punishment = "PERMANENT"

        guild_service.inc_caseid()
        user_service.add_case(member.id, case)
        u = user_service.get_user(id=member.id)
        u.is_muted = True
        u.save()

        await member.add_roles(mute_role)

        log = prepare_mute_log(ctx.author, member, case)
        await ctx.respond(embed=log, delete_after=10)

        log.remove_author()
        log.set_thumbnail(url=member.display_avatar)

        dmed = await notify_user(member, f"You have been muted in {ctx.guild.name}", log)
        await submit_public_log(ctx, db_guild, member, log, dmed)

    @mod_and_up()
    @slash_command(guild_ids=[cfg.guild_id], description="Unmute a user", permissions=slash_perms.mod_and_up())
    async def unmute(self, ctx: BlooContext, member: Option(discord.Member, description="User to mute"), reason: Option(str, description="Reason for mute", required=False) = "No reason.") -> None:
        """Unmute a user (mod only)

        Example usage
        --------------
        !unmute <@user/ID> <reason (optional)>

        Parameters
        ----------
        user : discord.Member
            "Member to unmute"
        reason : str, optional
            "Reason for unmute, by default 'No reason.'"
        """

        member = await mods_and_above_member_resolver(ctx, member)

        db_guild = guild_service.get_guild()
        mute_role = db_guild.role_mute
        mute_role = ctx.guild.get_role(mute_role)
        await member.remove_roles(mute_role)

        u = user_service.get_user(id=member.id)
        u.is_muted = False
        u.save()

        try:
            ctx.tasks.cancel_unmute(member.id)
        except Exception:
            pass

        case = Case(
            _id=db_guild.case_id,
            _type="UNMUTE",
            mod_id=ctx.author.id,
            mod_tag=str(ctx.author),
            reason=reason,
        )
        guild_service.inc_caseid()
        user_service.add_case(member.id, case)

        log = prepare_unmute_log(ctx.author, member, case)

        await ctx.respond(embed=log, delete_after=10)

        dmed = await notify_user(member, f"You have been unmuted in {ctx.guild.name}", log)
        await submit_public_log(ctx, db_guild, member, log, dmed)

    @mod_and_up()
    @slash_command(guild_ids=[cfg.guild_id], description="Ban a user", permissions=slash_perms.mod_and_up())
    async def ban(self, ctx: BlooContext, user: Option(discord.Member, description="User to ban"), reason: Option(str, description="Reason for ban", required=False) = "No reason."):
        """Ban a user (mod only)

        Example usage
        --------------
        !ban <@user/ID> <reason (optional)>

        Parameters
        ----------
        user : typing.Union[discord.Member, int]
            "The user to be banned, doesn't have to be part of the guild"
        reason : str, optional
            "Reason for ban, by default 'No reason.'"
        """

        user = await mods_and_above_external_resolver(ctx, user)

        reason = escape_markdown(reason)
        reason = escape_mentions(reason)
        db_guild = guild_service.get_guild()

        member_is_external = isinstance(user, User)

        # if the ID given is of a user who isn't in the guild, try to fetch the profile
        if member_is_external:
            async with ctx.typing():
                if self.bot.ban_cache.is_banned(user.id):
                    raise commands.BadArgument("That user is already banned!")

        self.bot.ban_cache.ban(user.id)
        log = await add_ban_case(ctx, user, reason, db_guild)

        if not member_is_external:
            await notify_user(user, f"You have been banned from {ctx.guild.name}", log)
            await user.ban(reason=reason)
        else:
            # hackban for user not currently in guild
            await ctx.guild.ban(discord.Object(id=user.id))

        await ctx.respond(embed=log, delete_after=10)
        await submit_public_log(ctx, db_guild, user, log)

    @mod_and_up()
    @slash_command(guild_ids=[cfg.guild_id], description="Unban a user", permissions=slash_perms.mod_and_up())
    async def unban(self, ctx: BlooContext, user: Option(discord.Member, description="User to unban"), reason: Option(str, description="Reason for unban", required=False) = "No reason.") -> None:
        """Unban a user (must use ID) (mod only)

        Example usage
        --------------
        !unban <user ID> <reason (optional)>

        Parameters
        ----------
        user : int
            "ID of the user to unban"
        reason : str, optional
            "Reason for unban, by default 'No reason.'"

        """

        user = await user_resolver(ctx, user)
        if ctx.guild.get_member(user.id) is not None:
            raise commands.BadArgument(
                "You can't unban someone already in the server!")

        reason = escape_markdown(reason)
        reason = escape_mentions(reason)

        if not self.bot.ban_cache.is_banned(user.id):
            raise commands.BadArgument("That user isn't banned!")

        try:
            await ctx.guild.unban(discord.Object(id=user.id), reason=reason)
        except discord.NotFound:
            raise commands.BadArgument(f"{user} is not banned.")

        self.bot.ban_cache.unban(user.id)

        db_guild = guild_service.get_guild()
        case = Case(
            _id=db_guild.case_id,
            _type="UNBAN",
            mod_id=ctx.author.id,
            mod_tag=str(ctx.author),
            reason=reason,
        )
        guild_service.inc_caseid()
        user_service.add_case(user.id, case)

        log = prepare_unban_log(ctx.author, user, case)
        await ctx.respond(embed=log, delete_after=10)

        await submit_public_log(ctx, db_guild, user, log)

    @mod_and_up()
    @slash_command(guild_ids=[cfg.guild_id], description="Purge channel messages", permissions=slash_perms.mod_and_up())
    async def purge(self, ctx: BlooContext, limit: Option(int, description="Number of messages to remove") = 0) -> None:
        """Purge messages from current channel (mod only)

        Example usage
        --------------
        !purge <number of messages>

        Parameters
        ----------
        limit : int, optional
            "Number of messages to purge, must be > 0, by default 0 for error handling"
        """

        if limit <= 0:
            raise commands.BadArgument(
                "Number of messages to purge must be greater than 0")
        elif limit >= 100:
            limit = 100

        msgs = await ctx.channel.history(limit=limit).flatten()

        await ctx.channel.purge(limit=limit)
        await ctx.respond(f'Purged {len(msgs)} messages.', delete_after=10)

    @mod_and_up()
    @slash_command(guild_ids=[cfg.guild_id], description="Lift a warn", permissions=slash_perms.mod_and_up())
    async def liftwarn(self, ctx: BlooContext, user: Option(discord.Member, description="User to lift warn of"), case_id: Option(int), reason: Option(str, required=False) = "No reason.") -> None:
        """Mark a warn as lifted and remove points. (mod only)

        Example usage
        --------------
        !liftwarn <@user/ID> <case ID> <reason (optional)>

        Parameters
        ----------
        user : discord.Member
            "User to remove warn from"
        case_id : int
            "The ID of the case for which we want to remove points"
        reason : str, optional
            "Reason for lifting warn, by default 'No reason.'"

        """

        user = await mods_and_above_external_resolver(ctx, user)

        # retrieve user's case with given ID
        cases = user_service.get_cases(user.id)
        case = cases.cases.filter(_id=case_id).first()

        reason = escape_markdown(reason)
        reason = escape_mentions(reason)

        # sanity checks
        if case is None:
            raise commands.BadArgument(
                message=f"{user} has no case with ID {case_id}")
        elif case._type != "WARN":
            raise commands.BadArgument(
                message=f"{user}'s case with ID {case_id} is not a warn case.")
        elif case.lifted:
            raise commands.BadArgument(
                message=f"Case with ID {case_id} already lifted.")

        u = user_service.get_user(id=user.id)
        if u.warn_points - int(case.punishment) < 0:
            raise commands.BadArgument(
                message=f"Can't lift Case #{case_id} because it would make {user.mention}'s points negative.")

        # passed sanity checks, so update the case in DB
        case.lifted = True
        case.lifted_reason = reason
        case.lifted_by_tag = str(ctx.author)
        case.lifted_by_id = ctx.author.id
        case.lifted_date = datetime.now()
        cases.save()

        # remove the warn points from the user in DB
        user_service.inc_points(user.id, -1 * int(case.punishment))
        dmed = True
        # prepare log embed, send to #public-mod-logs, user, channel where invoked
        log = prepare_liftwarn_log(ctx.author, user, case)
        dmed = await notify_user(user, f"Your warn has been lifted in {ctx.guild}.", log)

        await ctx.respond(embed=log, delete_after=10)
        await submit_public_log(ctx, guild_service.get_guild(), user, log, dmed)

    @mod_and_up()
    @slash_command(guild_ids=[cfg.guild_id], description="Edit case reason", permissions=slash_perms.mod_and_up())
    async def editreason(self, ctx: BlooContext, user: Option(discord.Member), case_id: Option(int), new_reason: Option(str)) -> None:
        """Edit case reason and the embed in #public-mod-logs. (mod only)

        Example usage
        --------------
        !editreason <@user/ID> <case ID> <reason>

        Parameters
        ----------
        user : discord.Member
            "User to edit case of"
        case_id : int
            "The ID of the case for which we want to edit reason"
        new_reason : str
            "New reason"

        """

        user = await mods_and_above_external_resolver(ctx, user)

        # retrieve user's case with given ID
        cases = user_service.get_cases(user.id)
        case = cases.cases.filter(_id=case_id).first()

        new_reason = escape_markdown(new_reason)
        new_reason = escape_mentions(new_reason)

        # sanity checks
        if case is None:
            raise commands.BadArgument(
                message=f"{user} has no case with ID {case_id}")

        old_reason = case.reason
        case.reason = new_reason
        case.date = datetime.now()
        cases.save()

        dmed = True
        log = prepare_editreason_log(ctx.author, user, case, old_reason)

        dmed = await notify_user(user, f"Your case was updated in {ctx.guild.name}.", log)

        public_chan = ctx.guild.get_channel(
            guild_service.get_guild().channel_public)

        found = False
        async with ctx.typing():
            async for message in public_chan.history(limit=200):
                if message.author.id != ctx.me.id:
                    continue
                if len(message.embeds) == 0:
                    continue
                embed = message.embeds[0]

                if embed.footer.text == discord.Embed.Empty:
                    continue
                if len(embed.footer.text.split(" ")) < 2:
                    continue

                if f"#{case_id}" == embed.footer.text.split(" ")[1]:
                    for i, field in enumerate(embed.fields):
                        if field.name == "Reason":
                            embed.set_field_at(
                                i, name="Reason", value=new_reason)
                            await message.edit(embed=embed)
                            found = True
        if found:
            await ctx.respond(f"We updated the case and edited the embed in {public_chan.mention}.", embed=log, delete_after=10)
        else:
            await ctx.respond(f"We updated the case but weren't able to find a corresponding message in {public_chan.mention}!", embed=log, delete_after=10)
            log.remove_author()
            log.set_thumbnail(url=user.avatar_url)
            await public_chan.send(user.mention if not dmed else "", embed=log)

    @mod_and_up()
    @slash_command(guild_ids=[cfg.guild_id], description="Edit case reason", permissions=slash_perms.mod_and_up())
    async def removepoints(self, ctx: BlooContext, user: Option(discord.Member), points: Option(int), reason: Option(str, required=False) = "No reason.") -> None:
        """Remove warnpoints from a user. (mod only)

        Example usage
        --------------
        !removepoints <@user/ID> <points> <reason (optional)>

        Parameters
        ----------
        user : discord.Member
            "User to remove warn from"
        points : int
            "Amount of points to remove"
        reason : str, optional
            "Reason for lifting warn, by default 'No reason.'"

        """

        user = await mods_and_above_external_resolver(ctx, user)

        reason = escape_markdown(reason)
        reason = escape_mentions(reason)

        if points < 1:
            raise commands.BadArgument("Points can't be lower than 1.")

        u = user_service.get_user(id=user.id)
        if u.warn_points - points < 0:
            raise commands.BadArgument(
                message=f"Can't remove {points} points because it would make {user.mention}'s points negative.")

        # passed sanity checks, so update the case in DB
        # remove the warn points from the user in DB
        user_service.inc_points(user.id, -1 * points)

        db_guild = guild_service.get_guild()
        case = Case(
            _id=db_guild.case_id,
            _type="REMOVEPOINTS",
            mod_id=ctx.author.id,
            mod_tag=str(ctx.author),
            punishment=str(points),
            reason=reason,
        )

        # increment DB's max case ID for next case
        guild_service.inc_caseid()
        # add case to db
        user_service.add_case(user.id, case)

        # prepare log embed, send to #public-mod-logs, user, channel where invoked
        log = prepare_removepoints_log(ctx.author, user, case)
        dmed = await notify_user(user, f"Your points were removed in {ctx.guild.name}.", log)

        await ctx.respond(embed=log, delete_after=10)
        await submit_public_log(ctx, db_guild, user, log, dmed)

    # @lock.error
    # @unlock.error
    # @freezeable.error
    # @unfreezeable.error
    # @freeze.error
    # @unfreeze.error
    @unmute.error
    @mute.error
    @liftwarn.error
    @unban.error
    @ban.error
    @warn.error
    @purge.error
    @kick.error
    @roblox.error
    @editreason.error
    @removepoints.error
    async def info_error(self,  ctx: BlooContext, error):
        if isinstance(error, ApplicationCommandInvokeError):
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
    bot.add_cog(ModActions(bot))
