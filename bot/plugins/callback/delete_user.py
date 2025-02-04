from contextlib import suppress
from pyrogram import Client, filters, types
from database import db


@Client.on_callback_query(filters.regex(pattern=r"^delete_user_\d+"))
async def delete_user(bot: Client, message: types.CallbackQuery):
    user_id = int(message.data.split("_")[-1])

    await db.users.delete_user(user_id)
    await message.edit_message_text("User Deleted From Database.")
    with suppress(Exception):
        await bot.send_message(
            user_id,
            f"You Have Been Deleted From My Database. Contact My [Owner](tg://user?id={bot.owner.id}) For More Details.",
        )
