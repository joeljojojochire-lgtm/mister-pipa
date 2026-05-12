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

# Configuración inicial (Render usará el TOKEN de Environment)
TOKEN = os.getenv("TELEGRAM_TOKEN")
games = {}
rooms = {}

# =========================================================
# COMANDOS DE GESTIÓN DE SALA
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏝️ MISTER PIPA SHOW\n\n"
        "Compite por llegar al final, compra objetos y vota contra tus amigos.\n\n"
        "/crear - Nueva sala\n/unirse - Entrar a sala\n/jugar - Empezar partida"
    )

async def crear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    rooms[chat_id] = []
    await update.message.reply_text("✅ Sala creada. Los demás deben usar /unirse.")

async def unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id not in rooms:
        await update.message.reply_text("❌ No hay sala activa. Usa /crear.")
        return
    if not any(p['id'] == user.id for p in rooms[chat_id]):
        rooms[chat_id].append({"id": user.id, "name": user.first_name})
        await update.message.reply_text(f"✅ @{user.first_name} se unió al show.")

async def jugar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in rooms or len(rooms[chat_id]) < 2:
        await update.message.reply_text("❌ Necesitas al menos 2 jugadores para empezar.")
        return
    game = MisterPipaGame(chat_id, rooms[chat_id])
    games[chat_id] = game
    await update.message.reply_text(render_game(game), reply_markup=main_keyboard())

# =========================================================
# LÓGICA DE BOTONES (TIENDA, VOTOS Y DADO)
# =========================================================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    user_id = query.from_user.id

    if chat_id not in games: return
    game = games[chat_id]

    data = query.data

    # --- 1. PROCESAR VOTO DE EVENTO (PÚBLICO) ---
    if data.startswith("votefor_"):
        target_id = int(data.split("_")[1])
        voter_name = query.from_user.first_name
        target_name = game.players[target_id]["name"]
        
        # Efecto: 50% probabilidad de ayudar o perjudicar
        es_bueno = random.choice([True, False])
        if es_bueno:
            game.players[target_id]["pos"] = safe_pos(game.players[target_id]["pos"] + 2, game.max_pos)
            msg = f"🎁 {voter_name} eligió a {target_name}: ¡AVANZA 2!"
        else:
            game.players[target_id]["pos"] = safe_pos(game.players[target_id]["pos"] - 2, game.max_pos)
            msg = f"⚡ {voter_name} eligió a {target_name}: ¡RETROCEDE 2!"

        game.pending_vote = None
        game.next_turn()
        await safe_edit(query, render_game(game, msg), main_keyboard())
        return

    # Bloqueo de turno: solo el jugador actual puede actuar
    if game.processing or user_id != game.current_player_id(): return
    game.processing = True

    try:
        # --- 2. ACCIÓN: TIRAR DADO ---
        if data == "roll":
            player = game.current_player()
            dice = random.randint(1, 6)
            player["pos"] = safe_pos(player["pos"] + dice, game.max_pos)
            
            # Equilibrio: Monedas aleatorias en el suelo (30% prob)
            monedas = 0
            if random.random() < 0.30:
                monedas = random.randint(5, 15)
                player["coins"] += monedas

            txt = f"🎲 @{player['name']} sacó {dice}."
            if monedas > 0:
                txt += f"\n🪙 ¡Encontraste {monedas} monedas en esta casilla!"

            # ACTIVAR EVENTO DE VOTO (Si la casilla termina en 5 o 0)
            if player["pos"] > 0 and player["pos"] % 5 == 0:
                game.pending_vote = True
                btns = []
                for pid, pdata in game.players.items():
                    if pid != user_id:
                        btns.append([InlineKeyboardButton(f"Elegir a {pdata['name']}", callback_data=f"votefor_{pid}")])
                
                await safe_edit(query, render_game(game, "⚖️ EVENTO CERRADO: ¿A quién quieres afectar?"), InlineKeyboardMarkup(btns))
                return

            # Meta final
            if player["pos"] >= game.max_pos:
                await safe_edit(query, f"🏆 ¡Felicidades @{player['name']}! Has ganado el Mister Pipa Show.")
                del games[chat_id]
                return

            game.next_turn()
            await safe_edit(query, render_game(game, txt), main_keyboard())

        # --- 3. ACCIÓN: TIENDA ---
        elif data == "shop":
            await safe_edit(query, "🛒 TIENDA DE OBJETOS", shop_keyboard(game, game.current_player()))

        elif data.startswith("buy_"):
            item_id = int(data.split("_")[1])
            player = game.current_player()
            costo = ITEMS[item_id]["precio"]
            if player["coins"] >= costo:
                player["coins"] -= costo
                player["items"].append(item_id)
                await safe_edit(query, render_game(game, f"🛒 Compraste {ITEMS[item_id]['name']}"), main_keyboard())
            else:
                await query.answer("No tienes monedas suficientes... ¡A buscar en el suelo!", show_alert=True)

        # --- 4. ACCIÓN: INVENTARIO ---
        elif data == "inventory":
            if not game.current_player()["items"]:
                await query.answer("Tu mochila está vacía 🎒", show_alert=True)
                return
            await safe_edit(query, "🎒 TUS OBJETOS", inventory_keyboard(game.current_player()))

        elif data == "back":
            await safe_edit(query, render_game(game), main_keyboard())

    except Exception as e:
        print(f"Error en botones: {e}")
    finally:
        game.processing = False

# =========================================================
# MOTOR PRINCIPAL (PARA RENDER)
# =========================================================

if __name__ == "__main__":
    if not TOKEN:
        print("❌ Error: No se detectó la variable TELEGRAM_TOKEN")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("crear", crear))
        app.add_handler(CommandHandler("unirse", unirse))
        app.add_handler(CommandHandler("jugar", jugar))
        app.add_handler(CallbackQueryHandler(buttons))
        print("✅ BOT MISTER PIPA ONLINE")
        app.run_polling()
