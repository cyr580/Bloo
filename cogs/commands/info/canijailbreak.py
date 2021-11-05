import json
import re
import traceback
from collections import OrderedDict

import aiohttp
from discord.colour import Color
from discord.commands.commands import Option, slash_command
from discord.commands.errors import ApplicationCommandInvokeError
from discord.embeds import Embed
from discord.ext import commands
from utils.autocompleters.devices import cij_device_autocomplete
from utils.config import cfg
from utils.context import BlooContext
from utils.permissions.checks import (PermissionsFailure, always_whisper, ensure_invokee_role_lower_than_bot, whisper)
from utils.views.devices import Confirm, FirmwareDropdown


class CanIJailbreak(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.devices_url = "https://api.ipsw.me/v4/devices"
        self.firmwares_url = "https://api.ipsw.me/v4/device/"
        self.devices_test = re.compile(r'^.+ \[.+\,.+\]$')
        self.devices_remove_re = re.compile(r'\[.+\,.+\]$')
        self.possible_devices = ['iphone', 'ipod', 'ipad']
        #self.CIJ_KEY = os.environ.get("CIJ_KEY")
        self.cij_baseurl = "https://canijailbreak2.com/v1/pls"

    @always_whisper()
    @slash_command(guild_ids=[cfg.guild_id], description="Check if you can jailbreak.")
    async def cij(self, ctx: BlooContext, device: Option(str, description="Name of your device", autocomplete=cij_device_autocomplete)) -> None:
        
        if not device.split(" ")[0].lower() in self.possible_devices:
            return await ctx.send_error("Unsupported device.")

        the_device = await self.find_device_from_ipsw_me(device)
        
        # did we find a device with given name?
        if the_device is None:
            return await ctx.send_error("Device doesn't exist!")
        
        new_device = device.lower()
        new_device = new_device.replace('s plus', '+')
        real_name = ""

        async with aiohttp.ClientSession() as session:
            async with session.get(self.devices_url) as resp:
                if resp.status == 200:
                    data = await resp.text()
                    devices = json.loads(data)
        
        for d in devices:
            name = re.sub(r'\((.*?)\)', "", d["name"])
            name = name.strip()
            name = name.replace('4[S]', '4S')
            if name.lower() == new_device:
                fix_casing = {'5s': '5S', '6s': '6S', '+': ' Plus'}
                for test in fix_casing:
                    real_name = name.replace(test, fix_casing[test])

        # prompt user for which firmware they want to get info for
        firmware = await self.prompt_for_firmware(ctx, the_device)
        
        await ctx.respond(f"{real_name}, {firmware}")
            
    async def find_device_from_ipsw_me(self, device):
        """Get device metadata for a given device from IPSW.me API

        Parameters
        ----------
        device : str
            "Name of the device we want metadata for (i.e iPhone 12)"

        Returns
        -------
        dict
            "Dictionary with the relavent metadata
        """

        device = device.lower()
        async with aiohttp.ClientSession() as session:
            async with session.get(self.devices_url) as resp:
                if resp.status == 200:
                    data = await resp.text()
                    devices = json.loads(data)
                    devices.append(
                        {'name': 'iPhone SE 2', 'identifier': 'iPhone12,8'})

                    # try to find a device with the name given in command
                    for d in devices:
                        # remove regional version info of device i.e iPhone SE (CDMA) -> iPhone SE
                        name = re.sub(r'\((.*?)\)', "", d["name"])
                        # get rid of '[ and ']'
                        name = name.replace('[', '')
                        name = name.replace(']', '')
                        name = name.strip()

                        # are the names equal?
                        if name.lower() == device:
                            d["name"] = name
                            return d
    
    async def prompt_for_firmware(self, ctx, the_device):
        """Prompt user for the firmware they want to use in their name

        Parameters
        ----------
        the_device : dict
           "Metadata of the device we want firmware for. Must ensure this is a valid firmware for this device."

        Returns
        -------
        str
            "firmware version we want to use, or None if we want to cancel"
        """

        # retrieve list of available firmwares for the given device
        firmwares = await self.find_firmwares_from_ipsw_me(the_device)
        firmwares_list = sorted(
            list(set([f["version"] for f in firmwares])), reverse=True)

        return await FirmwareDropdown(firmwares_list).start(ctx)

    async def find_firmwares_from_ipsw_me(self, the_device):
        """Get list of all valid firmwares for a given device from IPSW.me

        Parameters
        ----------
        the_device : dict
            "Metadata of the device we want firmwares for"

        Returns
        -------
        list[dict]
            "list of all the firmwares"
        """

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.firmwares_url}/{the_device['identifier']}") as resp:
                if resp.status == 200:
                    firmwares = json.loads(await resp.text())["firmwares"]

        if len(firmwares) == 0:
            raise commands.BadArgument(
                "Unforunately I don't have version history for this device.")

        return firmwares

def setup(bot):
    bot.add_cog(CanIJailbreak(bot))
