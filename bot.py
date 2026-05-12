import os
import random
import asyncio

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

from game import MisterPipaGame
from ui import render_game, main_keyboard, shop_keyboard, inventory_keyboard
from items import ITEMS
from utils import safe_pos
from config import MAX_PLAYERS, PLAYER_EMOJIS, PIPA_EMOJIS

TOKEN = os.getenv("TELEGRAM_TOKEN")

games = {}
rooms = {}

# =========================================================
# SISTEMA DE REACCIONES (Físicas de Telegram)
# =========================================================
async def set_reaction(context, chat_id, message_id, reaction_type):
    """Añade una reacción visual al mensaje del tablero"""
    # Mapeo de tipos de eventos a emojis de reacción de Telegram
    reactions = {
        "roll": "🎲",
        "win": "🎉",
        "buy": "💰",
        "item": "🔥",
        "bad": "😱",
        "wait": "⏳"
    }
    emoji = reactions.get(reaction_type, "👍")
    try:
        # Esto pone el emoji directamente sobre el mensaje del bot
        await context.bot.set_message_reaction(
            chat_id=chat_id, 
            message_id=message_id, 
            reaction=[{"type": "emoji", "emoji": emoji}]
        )
    except:
        pass

# =========================================================
# COMANDOS DE INICIO
# =========================================================

async def unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id not in rooms:
        rooms[chat_id] = []
    
    if any(p["id"] == user.id for p in rooms[chat_id]):
        return await update.message.reply_text("⚠️ Ya estás en la pista.")

    # Asignar emoji único al azar
    user_emoji = random.choice(PLAYER_EMOJIS)
    rooms[chat_id].append({
        "id": user.id,
        "name": user.first_name,
        "emoji": user_emoji
    })
    
    await update.message.reply_text(f"✅ **{user.first_name}** se unió con el emoji {user_emoji}")

async def jugar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in rooms or len(rooms[chat_id]) < 1:
        return await update.message.reply_text("❌ No hay corredores.")

    game = MisterPipaGame(chat_id, rooms[chat_id])
    games[chat_id] = game
    del rooms[chat_id]

    # Iniciamos con un mensaje de texto plano (Consola)
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=render_game(game, "¡Mister Pipa da el pistoletazo de salida! 🚩", "default"),
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML
    )
    game.message_id = msg.message_id

# =========================================================
# LÓGICA DE JUEGO (DADOS Y EVENTOS)
# =========================================================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    data = query.data

    if chat_id not in games: return
    game = games[chat_id]

    if game.processing: return
    game.processing = True

    try:
        if game.current_player_id() != user_id:
            return await query.answer("❌ No es tu turno.", show_alert=True)

        player = game.current_player()

        if data == "roll":
            dice = random.randint(1, 6)
            player["pos"] += dice
            player["pos"] = safe_pos(player["pos"], game.max_pos)
            
            # Narrativa dinámica según el resultado
            if dice >= 5:
                txt = f"🚀 ¡QUÉ VELOCIDAD! {player['name']} voló {dice} casillas."
                mood = "boost"
                reaction = "fire"
            elif dice <= 2:
                txt = f"🐢 {player['name']} va a paso de tortuga... solo {dice} casillas."
                mood = "joke"
                reaction = "bad"
            else:
                txt = f"😄 {player['name']} avanza con paso firme {dice} casillas."
                mood = "roll"
                reaction = "roll"

            # Actualizar tablero
            if player["pos"] >= game.max_pos:
                await query.edit_message_text(
                    text=render_game(game, f"🏆 ¡{player['name']} GANA EL SHOW! 🏆", "result"),
                    parse_mode=ParseMode.HTML
                )
                await set_reaction(context, chat_id, game.message_id, "win")
                del games[chat_id]
                return

            game.give_money(player)
            game.next_turn()
            
            await query.edit_message_text(
                text=render_game(game, txt, mood),
                reply_markup=main_keyboard(),
                parse_mode=ParseMode.HTML
            )
            await set_reaction(context, chat_id, game.message_id, reaction)

        elif data == "shop":
            await query.edit_message_text(
                text=render_game(game, "Mister Pipa abre su maletín de ofertas... 💰", "default"),
                reply_markup=shop_keyboard(game, player),
                parse_mode=ParseMode.HTML
            )

        elif data == "back":
            await query.edit_message_text(
                text=render_game(game, "De vuelta a la pista.", "default"),
                reply_markup=main_keyboard(),
                parse_mode=ParseMode.HTML
            )

    finally:
        game.processing = False

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("unirse", unirse))
    app.add_handler(CommandHandler("jugar", jugar))
    app.add_handler(CallbackQueryHandler(buttons))
    app.run_polling()
