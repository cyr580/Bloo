import json
import re
import traceback
import urllib
from datetime import datetime

import aiohttp
import discord
from data.services.guild_service import guild_service
from discord.commands.commands import Option, slash_command
from discord.commands.context import AutocompleteContext
from discord.ext import commands
from utils.async_cache import async_cacher
from utils.config import cfg
from utils.context import BlooContext, BlooOldContext
from utils.menu import Menu, TweakMenu
from utils.permissions.checks import PermissionsFailure
from utils.permissions.permissions import permissions
from yarl import URL

package_url = 'https://api.parcility.co/db/package/'
search_url = 'https://api.parcility.co/db/search?q='


async def package_request(package):
    async with aiohttp.ClientSession() as client:
        async with client.get(URL(f'{package_url}{package.get("Package")}', encoded=True)) as resp:
            if resp.status == 200:
                response = json.loads(await resp.text())
                if response.get('code') == 200:
                    package["Price"] = response['data'].get("Price")
            else:
                package["Price"] = "No price data"
                return package
    return package


async def search_request(search):
    async with aiohttp.ClientSession() as client:
        async with client.get(URL(f'{search_url}{urllib.parse.quote(search)}', encoded=True)) as resp:
            if resp.status == 200:
                response = json.loads(await resp.text())
                if response.get('code') == 404:
                    return []
                elif response.get('code') == 200:
                    return response.get('data')
                else:
                    return None
            else:
                return None


async def repo_autocomplete(ctx: AutocompleteContext):
    repos = await fetch_repos()
    repos = [repo["id"]
             for repo in repos if repo.get("id") and repo.get("id") is not None]
    repos.sort()
    return [repo for repo in repos if ctx.value.lower() in repo.lower()][:25]


@async_cacher()
async def fetch_repos():
    async with aiohttp.ClientSession() as client:
        async with client.get('https://api.parcility.co/db/repos/') as resp:
            if resp.status == 200:
                response = json.loads(await resp.text())
                if response.get('code') == 404:
                    return []
                elif response.get('code') == 200:
                    return response.get('data')
                else:
                    return None
            else:
                return None


async def format_tweak_page(entries, all_pages, current_page, ctx):
    # if entry is None:
    #     return discord.Embed(description="A ✨ Parcility 💖 error ocurred with this entry, please skip to the next one.", color=discord.Color.red())
    entry = entries[0]
    await package_request(entry)
    
    if not entry.get('repo').get('isDefault'):
        ctx.repo = entry.get('repo').get('url')
    else:
        ctx.repo = None
    
    embed = discord.Embed(title=entry.get('Name'), color=discord.Color.blue())
    embed.description = discord.utils.escape_markdown(
        entry.get('Description')) or "No description"
    embed.add_field(name="Author", value=discord.utils.escape_markdown(
        entry.get('Author') or "No author"), inline=True)
    embed.add_field(name="Version", value=discord.utils.escape_markdown(
        entry.get('Version') or "No version"), inline=True)
    embed.add_field(name="Price", value=entry.get("Price") or (entry.get(
        "Tag") and "cydia::commercial" in entry.get("Tag") and "Paid") or "Free")
    embed.add_field(
        name="Repo", value=f"[{entry.get('repo').get('label')}]({entry.get('repo').get('url')})" or "No repo", inline=True)
    # if entry.get('repo').get('isDefault') is False:
    #     embed.add_field(
    #         name="Add Repo", value=f"[Click Here](https://sharerepo.stkc.win/?repo={entry.get('repo').get('url')})" or "No repo", inline=True)
    try:
        if entry.get('Depiction'):
            embed.add_field(
                name="More Info", value=f"[View Depiction]({entry.get('Depiction')})", inline=False)
        else:
            raise Exception("No depiction found!")
    except:
        embed.add_field(
            name="More Info", value=f"[View on Parcility](https://parcility.co/package/{entry.get('Package')}/{entry.get('repo').get('slug')})", inline=False)
    pattern = re.compile(
        r"((http|https)\:\/\/)[a-zA-Z0-9\.\/\?\:@\-_=#]+\.([a-zA-Z]){2,6}([a-zA-Z0-9\.\&\/\?\:@\-_=#])*")
    if (pattern.match(entry.get('Icon'))):
        embed.set_thumbnail(url=entry.get('Icon'))
    embed.set_footer(icon_url=entry.get('repo').get('icon'), text=discord.utils.escape_markdown(
        entry.get('Package'))+f" • Page {current_page}/{len(all_pages)}" or "No package")
    embed.timestamp = datetime.now()
    return embed


async def format_repo_page(entries, all_pages, current_page, ctx):
    repo_data = entries[0]
    if not repo_data.get('isDefault'):
        ctx.repo = repo_data.get('url')
    else:
        ctx.repo = None

    embed = discord.Embed(title=repo_data.get(
        'Label'), color=discord.Color.blue())
    embed.description = repo_data.get('Description')
    embed.add_field(name="Packages", value=repo_data.get(
        'package_count'), inline=True)
    embed.add_field(name="Sections", value=repo_data.get(
        'section_count'), inline=True)
    embed.add_field(name="URL", value=repo_data.get('url'), inline=False)
    # if repo_data.get('isDefault') is False:
    #     embed.add_field(
    #         name="Add Repo", value=f'[Click Here](https://sharerepo.stkc.win/?repo={repo_data.get("url")})', inline=True)
    embed.add_field(
        name="More Info", value=f'[View on Parcility](https://parcility.co/{repo_data.get("id")})', inline=False)
    embed.set_thumbnail(url=repo_data.get('Icon'))
    if repo_data.get('isDefault') == True:
        embed.set_footer(text='Default Repo')

    embed.set_footer(
        text=f"Page {current_page} of {len(all_pages)}")

    return embed


class Parcility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.repo_url = 'https://api.parcility.co/db/repo/'

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild is None:
            return
        # if not message.guild.id == self.bot.settings.guild_id:
        #     return

        author = message.guild.get_member(message.author.id)
        if author is None:
            return

        whisper = False
        if not permissions.has(message.guild, author, 5) and message.channel.id == guild_service.get_guild().channel_general:
            whisper = True

        pattern = re.compile(
            r".*?(?<!\[)+\[\[((?!\s+)([\w+\ \&\+\-]){2,})\]\](?!\])+.*")
        if not pattern.match(message.content):
            return

        matches = pattern.findall(message.content)
        if not matches:
            return

        search_term = matches[0][0].replace('[[', '').replace(']]', '')
        if not search_term:
            return

        ctx = await self.bot.get_context(message, cls=BlooOldContext)
        async with ctx.typing():
            response = await search_request(search_term)

        if response is None:
            await ctx.send_error("An error occurred while searching for that tweak.")
            return
        elif len(response) == 0:
            await ctx.send_error("Sorry, I couldn't find any tweaks with that name.")
            return

        menu = TweakMenu(pages=response, channel=ctx.channel,
                    format_page=format_tweak_page, interaction=False, ctx=ctx, whisper=whisper, no_skip=True)
        await menu.start()

    @slash_command(guild_ids=[cfg.guild_id], description="Search for a repo")
    async def repo(self,  ctx: BlooContext, *, repo: Option(str, description="Name of the repo to search for", autocomplete=repo_autocomplete)):
        async with ctx.typing():
            data = await self.repo_request(repo)

        whisper = False
        if not permissions.has(ctx.guild, ctx.author, 5) and ctx.channel.id == guild_service.get_guild().channel_general:
            whisper = True

        if data is None:
            raise commands.BadArgument(
                'An error occurred while searching for that repo')

        if not isinstance(data, list):
            data = [data]

        if len(data) == 0:
            raise commands.BadArgument(
                "Sorry, I couldn't find a repo by that name.")

        menu = TweakMenu(data, ctx.channel, format_repo_page,
                    interaction=True, ctx=ctx, whisper=whisper)
        await menu.start()

    async def repo_request(self, repo):
        async with aiohttp.ClientSession() as client:
            async with client.get(f'{self.repo_url}{repo}') as resp:
                if resp.status == 200:
                    response = json.loads(await resp.text())
                    if response.get('code') == 404:
                        return []
                    elif response.get('code') == 200:
                        return response.get('data')
                    else:
                        return None
                else:
                    return None

    @repo.error
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
    bot.add_cog(Parcility(bot))