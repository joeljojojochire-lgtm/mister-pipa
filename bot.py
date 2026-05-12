import os
import random
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from game import MisterPipaGame
from ui import render_game, main_keyboard, shop_keyboard, inventory_keyboard
from items import ITEMS
from events import SPECIAL_CELLS, FREE_ITEM_CELLS
from utils import safe_pos, safe_edit

# Configuración
TOKEN = os.getenv("TELEGRAM_TOKEN")
games = {}
rooms = {}

# =========================================================
# COMANDOS
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏝️ MISTER PIPA SHOW\n\n/crear - Crear sala\n/unirse - Unirse a sala\n/jugar - Empezar partida"
    )

async def crear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    rooms[chat_id] = []
    await update.message.reply_text("✅ Sala creada. Dile a tus amigos que usen /unirse")

async def unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id not in rooms:
        await update.message.reply_text("❌ No hay ninguna sala creada. Usa /crear")
        return

    if any(p['id'] == user.id for p in rooms[chat_id]):
        await update.message.reply_text("⚠️ Ya estás en la sala.")
        return

    rooms[chat_id].append({"id": user.id, "name": user.first_name})
    await update.message.reply_text(f"✅ @{user.first_name} se ha unido.")

async def jugar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in rooms or len(rooms[chat_id]) < 2:
        await update.message.reply_text("❌ Necesitas al menos 2 jugadores.")
        return

    game = MisterPipaGame(chat_id, rooms[chat_id])
    games[chat_id] = game
    await update.message.reply_text(render_game(game), reply_markup=main_keyboard())

# =========================================================
# GESTIÓN DE BOTONES (LÓGICA DE JUEGO)
# =========================================================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    user_id = query.from_user.id

    if chat_id not in games: return
    game = games[chat_id]
    
    if game.processing: return
    game.processing = True

    try:
        data = query.data
        if user_id != game.current_player_id(): return

        if data == "roll":
            player = game.current_player()
            if player["skip"] > 0:
                player["skip"] -= 1
                game.next_turn()
                await safe_edit(query, render_game(game, f"💫 @{player['name']} pierde turno"), main_keyboard())
                return

            dice = random.randint(1, 6)
            player["pos"] += dice
            txt = f"🎲 @{player['name']} sacó {dice}"
            
            game.give_money(player)

            if player["pos"] in SPECIAL_CELLS:
                msg, n_pos = SPECIAL_CELLS[player["pos"]]
                player["pos"] = n_pos
                txt += f"\n⚠️ {msg}"

            player["pos"] = safe_pos(player["pos"], game.max_pos)

            if player["pos"] >= game.max_pos:
                await safe_edit(query, f"🏆 @{player['name']} ganó el show!")
                del games[chat_id]
                return

            game.next_turn()
            await safe_edit(query, render_game(game, txt), main_keyboard())

        elif data == "shop":
            await safe_edit(query, "🛒 TIENDA", shop_keyboard(game, game.current_player()))

        elif data == "inventory":
            await safe_edit(query, "🎒 INVENTARIO", inventory_keyboard(game.current_player()))

        elif data.startswith("buy_"):
            item_id = int(data.split("_")[1])
            player = game.current_player()
            if item_id in game.shop and player["coins"] >= ITEMS[item_id]["precio"]:
                player["coins"] -= ITEMS[item_id]["precio"]
                player["items"].append(item_id)
                del game.shop[item_id]
                await safe_edit(query, render_game(game, f"🛒 Compraste {ITEMS[item_id]['name']}"), main_keyboard())

        elif data == "back":
            await safe_edit(query, render_game(game), main_keyboard())

    except Exception as e:
        print(f"Error: {e}")
    finally:
        game.processing = False

# =========================================================
# ARRANQUE DEL BOT (ESTO ES LO QUE TE FALTA)
# =========================================================

if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERROR: Falta TELEGRAM_TOKEN en las variables de entorno.")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("crear", crear))
        app.add_handler(CommandHandler("unirse", unirse))
        app.add_handler(CommandHandler("jugar", jugar))
        app.add_handler(CallbackQueryHandler(buttons))

        print("✅ BOT INICIADO")
        app.run_polling()
