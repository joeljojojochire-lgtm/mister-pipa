import os
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# Importamos TUS archivos tal cual están en tu ZIP
from game import MisterPipaGame
from ui import render_game, main_keyboard, shop_keyboard, inventory_keyboard
from items import ITEMS
from events import SPECIAL_CELLS, FREE_ITEM_CELLS
from utils import safe_pos, safe_edit

TOKEN = os.getenv("TELEGRAM_TOKEN")
games = {}
rooms = {}

# --- COMANDOS (Respetando tu flujo) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏝️ MISTER PIPA SHOW\n/crear | /unirse | /jugar")

async def crear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    rooms[chat_id] = []
    await update.message.reply_text("✅ Sala creada.")

async def unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id in rooms and not any(p['id'] == user.id for p in rooms[chat_id]):
        rooms[chat_id].append({"id": user.id, "name": user.first_name})
        await update.message.reply_text(f"✅ @{user.first_name} entró.")

async def jugar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in rooms or len(rooms[chat_id]) < 2:
        await update.message.reply_text("❌ Faltan jugadores.")
        return
    game = MisterPipaGame(chat_id, rooms[chat_id])
    games[chat_id] = game
    await update.message.reply_text(render_game(game), reply_markup=main_keyboard())

# --- LÓGICA DE BOTONES (Sin omitir nada) ---
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    if chat_id not in games: return
    game = games[chat_id]

    data = query.data

    # 1. EVENTO DE VOTACIÓN (Público y narrativo)
    if data.startswith("votefor_"):
        target_id = int(data.split("_")[1])
        voter_name = query.from_user.first_name
        target_name = game.players[target_id]["name"]
        impacto = random.choice([3, -3]) # Avanza o retrocede 3
        game.players[target_id]["pos"] = safe_pos(game.players[target_id]["pos"] + impacto, game.max_pos)
        
        res = f"📢 {voter_name} votó por {target_name}. "
        res += "¡Avanza 3!" if impacto > 0 else "¡Retrocede 3!"
        
        game.pending_vote = None
        game.next_turn()
        await safe_edit(query, render_game(game, res), main_keyboard())
        return

    # 2. ACCIONES DE TURNO (Solo jugador actual)
    if game.processing or user_id != game.current_player_id(): return
    game.processing = True

    try:
        if data == "roll":
            player = game.current_player()
            dice = random.randint(1, 6)
            player["pos"] = safe_pos(player["pos"] + dice, game.max_pos)
            txt = f"🎲 @{player['name']} sacó {dice}."

            # MONEDAS (Evento aleatorio simple)
            if random.random() < 0.3:
                plus = random.randint(5, 10)
                player["coins"] += plus
                txt += f"\n🪙 ¡Encontraste {plus} monedas!"

            # EVENTOS ESCRITOS (De tu archivo events.py)
            if player["pos"] in SPECIAL_CELLS:
                msg, n_pos = SPECIAL_CELLS[player["pos"]]
                player["pos"] = n_pos
                txt += f"\n⚠️ {msg}"

            # ACTIVAR VOTACIÓN (Evento aleatorio de presión)
            if random.random() < 0.15: # 15% de probabilidad tras mover
                game.pending_vote = True
                btns = [[InlineKeyboardButton(f"Elegir a {p['name']}", callback_data=f"votefor_{pid}")] 
                        for pid, p in game.players.items() if pid != user_id]
                await safe_edit(query, render_game(game, "⚖️ ¡EVENTO! Elige a quién afectar:"), InlineKeyboardMarkup(btns))
                return

            if player["pos"] >= game.max_pos:
                await safe_edit(query, f"🏆 @{player['name']} ganó!")
                del games[chat_id]
                return

            game.next_turn()
            await safe_edit(query, render_game(game, txt), main_keyboard())

        elif data == "shop":
            await safe_edit(query, "🛒 TIENDA", shop_keyboard(game, game.current_player()))

        elif data.startswith("buy_"):
            item_id = int(data.split("_")[1])
            player = game.current_player()
            if player["coins"] >= ITEMS[item_id]["precio"]:
                player["coins"] -= ITEMS[item_id]["precio"]
                player["items"].append(item_id)
                await safe_edit(query, render_game(game, f"🛒 Compraste {ITEMS[item_id]['name']}"), main_keyboard())

        elif data == "inventory":
            await safe_edit(query, "🎒 MOCHILA", inventory_keyboard(game.current_player()))

        elif data == "back":
            await safe_edit(query, render_game(game), main_keyboard())

    finally:
        game.processing = False

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("crear", crear))
    app.add_handler(CommandHandler("unirse", unirse))
    app.add_handler(CommandHandler("jugar", jugar))
    app.add_handler(CallbackQueryHandler(buttons))
    print("✅ BOT ACTIVO")
    app.run_polling()
