from pyrogram import Client, StopPropagation, filters
from pyrogram.errors import UserNotParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import Config, Script
from bot.plugins.on_start_file import get_file
from bot.utils import get_admins, is_user_in_request_join, timeit
from database import db


# @Client.on_message(filters.private & filters.incoming, group=-1)
@timeit
async def forcesub(c: Client, m: Message):
    admins = await get_admins()
    if m.text and not m.text.startswith("/") and m.chat.id not in admins:
        return await m.reply(Script.NOT_ALLOWED_TEXT, quote=True)

    command = m.text.split()[1] if m.text and len(m.text.split()) > 1 else ""
    if m.chat.id in admins:
        return True
    if m.text and m.text.split()[0] != "/start":
        return await m.reply(Script.ARROGANT_REPLY, quote=True)

    try:
        out = await m.reply("Loading...")
    except Exception as e:
        print(e)
        return False

    force_sub = (await db.config.get_config("force_sub_config")) or {}
    force_sub = force_sub.get("value", {})

    if not force_sub:
        await out.delete()
        return True
    channel_status = await check_channels(c, m.from_user.id, force_sub)
    if [ch for ch in channel_status if not ch["joined"]]:
        text = await create_channel_status_file(channel_status)
        buttons = [
            InlineKeyboardButton(text=f"Join Channel {i}", url=channel["link"])
            for i, channel in enumerate(channel_status, start=1)
            if not channel["joined"]
        ]
        markup = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]

        markup.append(
            [InlineKeyboardButton(text="Try Again", callback_data=f"refresh_{command}")]
        )
        text += "\n𝖧𝖾𝗅𝗅𝗈 {mention} 𝗒𝗈𝗎 𝗁𝖺𝗏𝖾 𝗍𝗈 𝗃𝗈𝗂𝗇 𝗆𝗒 𝖼𝗁𝖺𝗇𝗇𝖾𝗅𝗌 𝗍𝗈 𝗀𝖾𝗍 𝗒𝗈𝗎𝗋 𝖿𝗂𝗅𝖾𝗌. 𝖪𝗂𝗇𝖽𝗅𝗒 𝗃𝗈𝗂𝗇 𝗍𝗁𝖾 𝖼𝗁𝖺𝗇𝗇𝖾𝗅𝗌 𝖺𝗇𝖽 𝗍𝗋𝗒 𝖺𝗀𝖺𝗂𝗇."
        await m.reply(
            text=text.format(mention=m.from_user.mention),
            reply_markup=InlineKeyboardMarkup(markup),
            quote=True,
        )
        await out.delete()
        raise StopPropagation

    await out.delete()
    return True


@Client.on_callback_query(filters.regex("^refresh"))
async def refresh_cb(c: Client, m):
    command = m.data.split("_", 1)[1] if len(m.data.split("_")) > 1 else ""
    await m.message.edit("Loading...")
    force_sub = (await db.config.get_config("force_sub_config")) or {}
    force_sub = force_sub.get("value", [])

    channel_status = await check_channels(c, m.from_user.id, force_sub)
    if [ch for ch in channel_status if not ch["joined"]]:

        buttons = [
            InlineKeyboardButton(text=f"Join Channel {i}", url=channel["link"])
            for i, channel in enumerate(channel_status, start=1)
            if not channel["joined"]
        ]
        markup = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]

        markup.append(
            [InlineKeyboardButton(text="Try Again", callback_data=f"refresh_{command}")]
        )
        filename = await create_channel_status_file(channel_status)
        mention = m.from_user.mention
        await m.message.edit(
            text=f"𝖯𝗅𝖾𝖺𝗌𝖾 𝖩𝗈𝗂𝗇 𝖳𝗁𝖾 𝖥𝗈𝗅𝗅𝗈𝗐𝗂𝗇𝗀 𝖢𝗁𝖺𝗇𝗇𝖾𝗅𝗌 𝖳𝗈 𝖴𝗌𝖾 𝖳𝗁𝗂𝗌 𝖡𝗈𝗍:\n\n{filename}\n"
            f"𝖧𝖾𝗅𝗅𝗈 {mention} 𝗒𝗈𝗎 𝗁𝖺𝗏𝖾 𝗍𝗈 𝗃𝗈𝗂𝗇 𝗆𝗒 𝖼𝗁𝖺𝗇𝗇𝖾𝗅𝗌 𝗍𝗈 𝗀𝖾𝗍 𝗒𝗈𝗎𝗋 𝖿𝗂𝗅𝖾𝗌. 𝖪𝗂𝗇𝖽𝗅𝗒 𝗃𝗈𝗂𝗇 𝗍𝗁𝖾 𝖼𝗁𝖺𝗇𝗇𝖾𝗅𝗌 𝖺𝗇𝖽 𝗍𝗋𝗒 𝖺𝗀𝖺𝗂𝗇.",
            reply_markup=InlineKeyboardMarkup(markup),
        )
        return
    await m.message.edit("𝖸𝗈𝗎 𝖼𝖺𝗇 𝗎𝗌𝖾 𝗆𝖾 𝗇𝗈𝗐 𝗍𝗁𝖺𝗍 𝗉𝖾𝗋𝗆𝗂𝗌𝗌𝗂𝗈𝗇 𝗁𝖺𝗌 𝖻𝖾𝖾𝗇 𝗀𝗋𝖺𝗇𝗍𝖾𝖽 😎")

    if command:
        m.message.from_user = m.from_user
        m = m.message
        m.text = f"/start {command}"
        m.command = ["start", command]
        await get_file(c, m)


@timeit
async def create_channel_status_file(channel_status):
    text = "𝖢𝗁𝖺𝗇𝗇𝖾𝗅 𝖲𝗍𝖺𝗍𝗎𝗌 :-\n\n"
    for i, channel in enumerate(channel_status, start=1):
        text += f"{i}. 𝖢𝗁𝖺𝗇𝗇𝖾𝗅 {i} - {'✅ 𝖩𝗈𝗂𝗇𝖾𝖽' if channel['joined'] else '❌ 𝖭𝗈𝗍 𝖩𝗈𝗂𝗇𝖾𝖽'}\n"
    return text


@timeit
async def get_invite_link(bot: Client, channel_id, method):

    if Config.INVITE_LINKS.get(channel_id):
        return Config.INVITE_LINKS[channel_id]

    link = await bot.create_chat_invite_link(
        channel_id, creates_join_request=(method == "request")
    )
    Config.INVITE_LINKS[channel_id] = link.invite_link
    return link.invite_link


async def get_channel_status(channel_name, invite_link, joined):
    if isinstance(invite_link, str):
        invite_link = invite_link
    else:
        invite_link = invite_link.invite_link

    return {
        "name": channel_name,
        "joined": joined,
        "link": invite_link,
    }

@timeit
async def check_channels(bot: Client, user_id: int, force_sub: dict):

    channel_status = []

    for sub in force_sub.values():
        if not sub["status"]:
            continue

        channel_id = sub["channel_id"]
        channel_name = sub["title"]
        method = sub["method"]

        try:
            invite_link = await get_invite_link(bot, channel_id, method)
            if Config.CHAT_CACHE.get(channel_id):
                chat = Config.CHAT_CACHE[channel_id]
            else:
                chat = await bot.get_chat(channel_id)
                Config.CHAT_CACHE[channel_id] = chat
        except Exception as e:
            print(e)
            continue

        try:
            is_requested = await is_user_in_request_join(channel_id, user_id)
            if method == "request":
                joined = is_requested
            elif method == "direct":
                await bot.get_chat_member(channel_id, user_id)
                joined = True
        except UserNotParticipant:
            joined = False
        except Exception as e:
            print(e)
            joined = False

        channel_status.append(
            await get_channel_status(channel_name, invite_link, joined)
        )

    return channel_status
