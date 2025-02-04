import asyncio
import base64
import contextlib
import datetime
import functools
import logging
import math
from collections import OrderedDict
from time import time

from aiohttp import web
from async_lru import alru_cache
from pyrogram import Client, errors, types

from bot.config import Config, Script
from database import db

INTERVALS = OrderedDict(
    [
        ("millennium", 31536000000),  # 60 * 60 * 24 * 365 * 1000
        ("century", 3153600000),  # 60 * 60 * 24 * 365 * 100
        ("year", 31536000),  # 60 * 60 * 24 * 365
        ("month", 2592000),  # 60 * 60 * 24 * 28 (assuming 28 days in a month)
        ("week", 604800),  # 60 * 60 * 24 * 7
        ("day", 86400),  # 60 * 60 * 24
        ("hr", 3600),  # 60 * 60
        ("min", 60),
        ("sec", 1),
    ]
)


def timeit(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time()
        result = await func(*args, **kwargs)
        end = time()
        diff = end - start
        print(f"{func.__name__} took {diff:.2f} seconds") if Config.DEBUG else None
        return result

    return wrapper


async def start_webserver():
    routes = web.RouteTableDef()

    @routes.get("/", allow_head=True)
    async def root_route_handler(request):
        res = {
            "status": "running",
        }
        return web.json_response(res)

    async def web_server():
        web_app = web.Application(client_max_size=30000000)
        web_app.add_routes(routes)
        return web_app

    app = web.AppRunner(await web_server())
    await app.setup()
    await web.TCPSite(app, "0.0.0.0", 8000).start()
    logging.info("Web server started")


async def add_new_user(user_id):
    if not await db.users.col.find_one({"_id": user_id}):
        await db.users.add_user(user_id)
        return True


async def set_commands(app: Client):
    commands = [
        types.BotCommand("start", "Start bot"),
        types.BotCommand("batch", "Batch upload files"),
        types.BotCommand("addadmin", "Add an admin"),
        types.BotCommand("removeadmin", "Remove an admin"),
        types.BotCommand("admins", "Get a list of admins"),
        types.BotCommand("broadcast", "Broadcast a message"),
        types.BotCommand("delete", "Delete a file"),
        types.BotCommand("genlink", "Generate a link"),
        types.BotCommand("stats", "Get bot stats"),
        types.BotCommand("user", "Get user details"),
        types.BotCommand("help", "Help message"),
        types.BotCommand("admin", "Admin commands"),
    ]
    await app.set_bot_commands(commands)


async def handle_floodwait(func, *args, **kwargs):
    try:
        return await func(*args, **kwargs)
    except errors.FloodWait as e:
        await asyncio.sleep(e.value)
        return await handle_floodwait(func, *args, **kwargs)


async def handle_reply(message, text, **kwargs):
    kwargs.pop("caption", None)
    kwargs.pop("text", None)
    if isinstance(message, types.Message):
        await message.reply_text(text=text, **kwargs)

    elif isinstance(message, types.CallbackQuery):
        message: types.CallbackQuery
        kwargs.pop("quote", None)
        if message.message.photo:
            await message.message.delete()
            await message.message.reply(text=text, **kwargs)
        else:
            await message.edit_message_text(text=text, **kwargs)


@alru_cache(maxsize=1, ttl=60 * 60)
async def get_admins():
    config = await db.config.get_config("ADMINS")
    return config["value"] if config else []


async def add_admin(user_id):
    config = await db.config.get_config("ADMINS")
    if config:
        admins = config["value"]
        if user_id not in admins:
            admins.append(user_id)
            await db.config.update_config("ADMINS", admins)
            return True
    else:
        await db.config.add_config("ADMINS", [user_id])
        return True

    return False


async def remove_admin(user_id):
    config = await db.config.get_config("ADMINS")
    if config:
        admins = config["value"]
        if user_id in admins:
            admins.remove(user_id)
            await db.config.update_config("ADMINS", admins)
            return True
    return False


async def ensure_config_entry(key, default_value):
    if not await db.config.get_config(key):
        await db.config.add_config(key, default_value)


async def ensure_config():
    await ensure_config_entry("ADMINS", [])
    await ensure_config_entry("message_delete_time", 0)
    await ensure_config_entry("file_delete_time", 0)
    await ensure_config_entry("force_sub_config", {})
    await ensure_config_entry("request_joins", {})
    await ensure_config_entry("force_sub_cache", {})


async def add_force_sub_cache(user_id):
    force_sub_cache = await db.config.get_config("force_sub_cache")
    force_sub_cache = force_sub_cache.get("value", {})
    force_sub_cache[str(user_id)] = datetime.datetime.now() + datetime.timedelta(days=1)
    await db.config.update_config("force_sub_cache", force_sub_cache)


async def is_force_sub_cache_expired(user_id):
    force_sub_cache = await db.config.get_config("force_sub_cache")
    force_sub_cache = force_sub_cache.get("value", {})
    return (
        str(user_id) not in force_sub_cache
        or force_sub_cache[str(user_id)] < datetime.datetime.now()
    )


async def add_request_join(chat_id, user_id):
    request_joins = await db.config.get_config("request_joins")
    request_joins = request_joins.get("value", {})
    if str(chat_id) not in request_joins:
        request_joins[str(chat_id)] = []
    if user_id not in request_joins[str(chat_id)]:
        request_joins[str(chat_id)].append(user_id)
        await db.config.update_config("request_joins", request_joins)
        return True
    return False


@timeit
async def is_user_in_request_join(chat_id, user_id):
    result = await db.config.col.count_documents(
        {
            "name": "request_joins",
            f"value.{chat_id}": {"$elemMatch": {"$eq": user_id}},
        }
    )
    return bool(result)


async def process_delete_schedule(bot):
    await asyncio.sleep(10)
    while True:
        schedules = await db.del_schedule.filter_schedules(
            {"status": False, "time": {"$lte": datetime.datetime.now()}}
        )
        chats = {}
        for schedule in schedules:
            chat_id = schedule["chat_id"]
            if chat_id not in chats:
                chats[chat_id] = []
            chats[chat_id].append(schedule["message_id"])

        if not chats:
            continue

        # sorrt to have more than 200 messages in a chat
        chats = dict(sorted(chats.items(), key=lambda item: len(item[1]), reverse=True))
        for chat_id, message_ids in chats.items():
            for i in range(0, len(message_ids), 200):
                await process_delete_schedule_single(
                    bot, chat_id, message_ids[i : i + 200]
                )
                await asyncio.sleep(1)
        await asyncio.sleep(60)


async def process_delete_schedule_single(bot: Client, chat_id, message_ids=None):

    with contextlib.suppress(Exception):
        await bot.delete_messages(chat_id, message_ids)
        await asyncio.sleep(1)

    await db.del_schedule.delete_many(chat_id, message_ids)


async def encode(string):
    string_bytes = string.encode("ascii")
    base64_bytes = base64.urlsafe_b64encode(string_bytes)
    return (base64_bytes.decode("ascii")).strip("=")


async def decode(base64_string):
    base64_string = base64_string.strip(
        "="
    )  # links generated before this commit will be having = sign, hence striping them to handle padding errors.
    base64_bytes = (base64_string + "=" * (-len(base64_string) % 4)).encode("ascii")
    string_bytes = base64.urlsafe_b64decode(base64_bytes)
    return string_bytes.decode("ascii")


async def get_messages(client, message_ids):
    messages = []

    total_messages = 0
    while total_messages != len(message_ids):
        temb_ids = message_ids[total_messages : total_messages + 200]
        try:
            msgs = await client.get_messages(
                chat_id=Config.CHANNELS, message_ids=temb_ids
            )
        except errors.FloodWait as e:
            await asyncio.sleep(e.value)
            msgs = await client.get_messages(
                chat_id=Config.CHANNELS, message_ids=temb_ids
            )
        except Exception as e:
            print(e)
            continue
        total_messages += len(temb_ids)
        messages.extend(msgs)
    return messages


def get_caption(**kwargs):
    caption = Script.DEFAULT_CAPTION
    return caption.format(**kwargs)


def get_func(ins):
    if isinstance(ins, types.Message):
        return ins.reply_text
    else:
        return ins.edit_message_text


def get_channel_id(message, n=1, s=" "):
    if isinstance(message, types.Message):
        channel_id = None
    elif len(message.data.split(s)) > n:
        channel_id = message.data.split(s)[n]
        channel_id = None if channel_id == "None" else int(channel_id)
    else:
        channel_id = None
    return channel_id


def human_size(bytes):
    if bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(bytes, 1024)))
    p = math.pow(1024, i)
    s = round(bytes / p, 2)
    return f"{s} {size_name[i]}"


def get_file_details(message):
    media = getattr(message, message.media.value)
    filename = media.file_name if getattr(media, "file_name", None) else "Not Available"
    file_size = media.file_size
    file_unique_id = media.file_unique_id
    file_type = (
        media.mime_type if getattr(media, "mime_type", None) else "Not Available"
    )
    file_caption = message.caption.html if message.caption else ""
    file_extension = filename.split(".")[-1]
    duration = None
    if file_type.startswith("video") and getattr(media, "duration", None):
        duration = media.duration
        duration = datetime.timedelta(seconds=duration)
    return (
        filename,
        file_size,
        file_unique_id,
        file_type,
        file_caption,
        file_extension,
        duration,
    )


def check(func):
    """Check if user is admin or not"""

    @functools.wraps(func)
    async def wrapper(client: Client, message):
        chat_id = getattr(message.from_user, "id", None)
        admins = await get_admins()

        if chat_id not in admins:
            return

        banned_users = await db.users.get_all_banned_users()
        banned_users_ids = [user["_id"] for user in banned_users]
        if chat_id in banned_users_ids:
            return

        return await func(client, message)

    return wrapper


def owner_only(func):
    """Check if user is owner or not"""

    @functools.wraps(func)
    async def wrapper(client: Client, message):
        chat_id = getattr(message.from_user, "id", None)
        if chat_id != Config.OWNER_ID:
            return

        return await func(client, message)

    return wrapper


def human_readable_time(seconds, decimals=0):
    """Human-readable time from seconds (ie. 5 days and 2 hours).

    Examples:
        >>> human_time(15)
        '15 seconds'
        >>> human_time(3600)
        '1 hour'
        >>> human_time(3720)
        '1 hour and 2 minutes'
        >>> human_time(266400)
        '3 days and 2 hours'
        >>> human_time(-1.5)
        '-1.5 seconds'
        >>> human_time(0)
        '0 seconds'
        >>> human_time(0.1)
        '100 milliseconds'
        >>> human_time(1)
        '1 second'
        >>> human_time(1.234, 2)
        '1.23 seconds'

    Args:
        seconds (int or float): Duration in seconds.
        decimals (int): Number of decimals.

    Returns:
        str: Human-readable time.
    """
    if (
        seconds < 0
        or seconds != 0
        and not 0 < seconds < 1
        and 1 < seconds < INTERVALS["min"]
    ):
        input_is_int = isinstance(seconds, int)
        return f"{str(seconds if input_is_int else round(seconds, decimals))} sec"
    elif seconds == 0:
        return "0 s"
    elif 0 < seconds < 1:
        # Return in milliseconds.
        ms = int(seconds * 1000)
        return "%i ms%s" % (ms, "s" if ms != 1 else "")
    res = []
    for interval, count in INTERVALS.items():
        quotient, remainder = divmod(seconds, count)
        if quotient >= 1:
            seconds = remainder
            if quotient > 1:
                # Plurals.
                if interval == "millennium":
                    interval = "millennia"
                elif interval == "century":
                    interval = "centuries"
                else:
                    interval += "s"
            res.append("%i %s" % (int(quotient), interval))
        if remainder == 0:
            break

    return f"{res[0]} {res[1]}" if len(res) >= 2 else res[0]
