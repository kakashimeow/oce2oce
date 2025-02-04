from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup
from bot.config import Script, Buttons
from bot.utils import check, handle_reply


@Client.on_message(filters.command("help") & filters.private & filters.incoming)
@Client.on_callback_query(filters.regex(pattern=r"^help$"))
@check
async def help(bot: Client, message: Message):
    text = Script.HELP_MESSAGE
    markup = InlineKeyboardMarkup(Buttons.BACK_BUTTON)
    await handle_reply(message, text, reply_markup=markup)
