import json
import re

import aiohttp
from discord.commands.context import AutocompleteContext
from utils.async_cache import async_cacher


@async_cacher()
async def get_devices():
    res_devices = []
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.ipsw.me/v4/devices") as resp:
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
                    if name not in res_devices:
                        res_devices.append(name)

    return res_devices

@async_cacher()
async def get_cij_devices():
    res_devices = []
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.ipsw.me/v4/devices") as resp:
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
                    # remove devices that can't be jailbroken / aren't in CIJ API
                    if name.startswith("Apple TV") or name.startswith("Apple Watch") or name.startswith("HomePod") or name.startswith("MacBook") or name.startswith("iMac") or name.startswith("Mac") or name.startswith("iBridge") or name == "Developer Transition Kit":
                        devices.remove(d)
                    else:
                        if name not in res_devices:
                            res_devices.append(name)

    return res_devices

async def device_autocomplete(ctx: AutocompleteContext):
    devices = await get_devices()
    devices.sort()
    return [device for device in devices if device.lower().startswith(ctx.value.lower())][:25]

async def cij_device_autocomplete(ctx: AutocompleteContext):
    devices = await get_cij_devices()
    devices.sort()
    return [device for device in devices if device.lower().startswith(ctx.value.lower())][:25]
