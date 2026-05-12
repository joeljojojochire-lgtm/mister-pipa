from telegram import InlineKeyboardMarkup


def safe_pos(value, max_pos):
    return max(0, min(max_pos, value))


async def safe_edit(query, text, keyboard=None):

    try:

        if isinstance(keyboard, InlineKeyboardMarkup):
            await query.edit_message_text(
                text,
                reply_markup=keyboard
            )
        else:
            await query.edit_message_text(text)

    except Exception:
        pass
