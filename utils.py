from telegram import InlineKeyboardMarkup

def safe_pos(value, max_pos):
    """Asegura que el jugador no se salga del tablero."""
    return max(0, min(max_pos, value))

async def safe_edit(query, text, keyboard=None):
    """Edita mensajes de forma segura evitando errores por contenido idéntico."""
    try:
        if isinstance(keyboard, InlineKeyboardMarkup):
            await query.edit_message_text(
                text,
                reply_markup=keyboard
            )
        else:
            await query.edit_message_text(text)
    except Exception as e:
        # Esto evita que el bot se detenga si Telegram da error de "Message is not modified"
        print(f"Log: Error menor en safe_edit (ignorable): {e}")
        pass
