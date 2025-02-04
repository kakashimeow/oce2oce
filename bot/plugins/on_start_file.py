import asyncio
import datetime
import traceback
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from pyrogram.enums import ParseMode
from bot.utils import human_readable_time, decode, get_messages
from database import db
from asyncio import sleep
from bot.config import Config


async def get_file(bot: Client, message: Message):
    user_chat_id = message.from_user.id

    message_delete_time = await get_config_value("message_delete_time")
    file_delete_time = await get_config_value("file_delete_time")

    command = message.command[1]
    text = message.text

    if command.startswith("download_"):
        file_id = command.split("_", 1)[1]
        file = await db.files.col.find_one({"_id": file_id})

        if not file:
            await message.reply_text("File Not Found")
            return
        await db.users.update_user(user_chat_id, {"files_received": 1}, "inc")
        file_message = await handle_file(
            bot, user_chat_id, file, message_delete_time, file_delete_time
        )
        if not file_message:
            await message.reply_text("File Not Found")

    elif command.startswith("batch_"):
        await batch_handler(bot, message, message_delete_time, file_delete_time)
    elif len(text) > 7:
        await custom_send(bot, message, file_delete_time, message_delete_time)

    await schedule_deletion(message.chat.id, message.id, file_delete_time)


async def get_config_value(key: str, default: int = 0):
    config = await db.config.get_config(key)
    return config.get("value", default)


async def schedule_deletion(chat_id: int, message_id: int, delete_time: int):
    if delete_time > 0:
        time = datetime.datetime.now() + datetime.timedelta(seconds=delete_time)
        await db.del_schedule.add_schedule(chat_id, message_id, time)


async def handle_file(
    bot: Client,
    user_chat_id: int,
    file: dict,
    message_delete_time: int,
    file_delete_time: int,
):
    message_id, chat_id = map(int, file["log"].split("-", 1))
    message = await bot.get_messages(chat_id, message_id)

    if message.empty:
        return None

    caption = message.caption.html if message.caption else ""
    file_message = await copy_message(
        message, user_chat_id, caption=caption[:1000], reply_markup=None
    )

    temp_message = await file_message.reply_text(
        f"⏳𝖡𝖾𝖿𝗈𝗋𝖾 𝖽𝗈𝗐𝗇𝗅𝗈𝖺𝖽𝗂𝗇𝗀 𝗍𝗁𝖾 𝖿𝗂𝗅𝖾𝗌, 𝗉𝗅𝖾𝖺𝗌𝖾 𝗍𝗋𝖺𝗇𝗌𝖿𝖾𝗋 𝗍𝗁𝖾𝗆 𝗍𝗈 𝖺𝗇𝗈𝗍𝗁𝖾𝗋 𝗅𝗈𝖼𝖺𝗍𝗂𝗈𝗇 𝗈𝗋 𝗌𝖺𝗏𝖾 𝗍𝗁𝖾𝗆 𝗂𝗇 𝖲𝖺𝗏𝖾𝖽 𝖬𝖾𝗌𝗌𝖺𝗀𝖾𝗌, 𝖳𝗁𝖾𝗒 𝗐𝗂𝗅𝗅 𝖻𝖾 𝖽𝖾𝗅𝖾𝗍𝖾𝖽 𝗂𝗇 {human_readable_time(message_delete_time)}."
    )

    await schedule_deletion(temp_message.chat.id, temp_message.id, message_delete_time)
    await schedule_deletion(file_message.chat.id, file_message.id, file_delete_time)

    return file_message


async def batch_handler(
    bot: Client, message: Message, message_delete_time: int, file_delete_time: int
):
    user_chat_id = message.from_user.id
    _, batch_id = message.command[1].split("_", 1)

    batch = await db.files.get_batch(batch_id)
    if not batch:
        await message.reply_text("Invalid Batch ID")
        return

    del_files = []
    total_files = len(batch["files"])
    await db.users.update_user(user_chat_id, {"files_received": total_files}, "inc")
    for file in batch["files"]:
        message_id, chat_id = file["message_id"], file["chat_id"]
        message = await bot.get_messages(chat_id, message_id)

        if message.empty:
            continue

        caption = message.caption.html if message.caption else ""
        caption = caption[:1000]
        try:
            file_message = await copy_message(
                message, user_chat_id, caption=caption, reply_markup=None
            )
        except FloodWait as e:
            await sleep(e.value)
            file_message = await copy_message(
                message, user_chat_id, caption=caption, reply_markup=None
            )

        del_files.append(file_message.id)
        await sleep(1)

    temp_message = await bot.send_message(
        user_chat_id,
        f"⏳𝖡𝖾𝖿𝗈𝗋𝖾 𝖽𝗈𝗐𝗇𝗅𝗈𝖺𝖽𝗂𝗇𝗀 𝗍𝗁𝖾 𝖿𝗂𝗅𝖾𝗌, 𝗉𝗅𝖾𝖺𝗌𝖾 𝗍𝗋𝖺𝗇𝗌𝖿𝖾𝗋 𝗍𝗁𝖾𝗆 𝗍𝗈 𝖺𝗇𝗈𝗍𝗁𝖾𝗋 𝗅𝗈𝖼𝖺𝗍𝗂𝗈𝗇 𝗈𝗋 𝗌𝖺𝗏𝖾 𝗍𝗁𝖾𝗆 𝗂𝗇 𝖲𝖺𝗏𝖾𝖽 𝖬𝖾𝗌𝗌𝖺𝗀𝖾𝗌, 𝖳𝗁𝖾𝗒 𝗐𝗂𝗅𝗅 𝖻𝖾 𝖽𝖾𝗅𝖾𝗍𝖾𝖽 𝗂𝗇 {human_readable_time(message_delete_time)}.",
    )

    await schedule_deletion(temp_message.chat.id, temp_message.id, message_delete_time)

    for file_message_id in del_files:
        await schedule_deletion(user_chat_id, file_message_id, file_delete_time)


async def custom_send(client: Client, message: Message, file_delete_time: int, message_delete_time: int):
    user_chat_id = message.from_user.id
    text = message.text
    try:
        base64_string = text.split(" ", 1)[1]
    except Exception:
        return

    string = await decode(base64_string)
    argument = string.split("-")
    if len(argument) == 3:
        try:
            start = int(int(argument[1]) / abs(Config.CHANNELS))
            end = int(int(argument[2]) / abs(Config.CHANNELS))
        except Exception:
            return
        if start <= end:
            ids = range(start, end + 1)
        else:
            ids = []
            i = start
            while True:
                ids.append(i)
                i -= 1
                if i < end:
                    break
    elif len(argument) == 2:
        try:
            ids = [int(int(argument[1]) / abs(Config.CHANNELS))]
        except Exception:
            return
    temp_msg = await message.reply("Please wait...")

    try:
        messages = await get_messages(client, ids)
    except Exception:
        traceback.print_exc()
        await message.reply_text("Something went wrong..!")
        return
    await temp_msg.delete()

    for msg in messages:
        msg: Message
        caption = msg.caption.html if msg.caption else ""
        try:
            log = await msg.copy(
                chat_id=message.from_user.id,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=None,
            )
            await asyncio.sleep(0.5)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            log = await msg.copy(
                chat_id=message.from_user.id,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=None,
            )
        except Exception as e:
            print(e)
            continue
        if log:
            await schedule_deletion(log.chat.id, log.id, file_delete_time)

    temp_message = await client.send_message(
        user_chat_id,
        f"⏳𝖡𝖾𝖿𝗈𝗋𝖾 𝖽𝗈𝗐𝗇𝗅𝗈𝖺𝖽𝗂𝗇𝗀 𝗍𝗁𝖾 𝖿𝗂𝗅𝖾𝗌, 𝗉𝗅𝖾𝖺𝗌𝖾 𝗍𝗋𝖺𝗇𝗌𝖿𝖾𝗋 𝗍𝗁𝖾𝗆 𝗍𝗈 𝖺𝗇𝗈𝗍𝗁𝖾𝗋 𝗅𝗈𝖼𝖺𝗍𝗂𝗈𝗇 𝗈𝗋 𝗌𝖺𝗏𝖾 𝗍𝗁𝖾𝗆 𝗂𝗇 𝖲𝖺𝗏𝖾𝖽 𝖬𝖾𝗌𝗌𝖺𝗀𝖾𝗌, 𝖳𝗁𝖾𝗒 𝗐𝗂𝗅𝗅 𝖻𝖾 𝖽𝖾𝗅𝖾𝗍𝖾𝖽 𝗂𝗇 {human_readable_time(message_delete_time)}.",
    )

    await schedule_deletion(temp_message.chat.id, temp_message.id, message_delete_time)

async def copy_message(message: Message, chat_id: int, **kwargs):
    return await message.copy(chat_id=chat_id, **kwargs)
