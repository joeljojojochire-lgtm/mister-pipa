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
from telegram.constants import ParseMode

from game import MisterPipaGame
from ui import render_game
from items import ITEMS
from utils import safe_pos
from config import PLAYER_EMOJIS

TOKEN = os.getenv("TELEGRAM_TOKEN")

games = {}
rooms = {}

# --- Configuración de la Votación ---
VOTACIONES = {
    "liebre": {
        "pregunta": "🚨 ¡UNA LIEBRE SALVAJE ATACA! 🚨\n\nEl grupo está acorralado. Mister Pipa exige un sacrificio... ¿Quién será el 'héroe' que se arroje a la liebre para que los demás escapen?",
        "mood": "vote"
    }
}

# =========================================================
# SISTEMA DE REACCIONES
# =========================================================
async def set_reaction(context, chat_id, message_id, reaction_type):
    reactions = {
        "roll": "🎲", "win": "🎉", "fire": "🔥",
        "bad": "😱", "wait": "⏳", "shock": "⚡", "vote": "🗳️"
    }
    emoji = reactions.get(reaction_type, "👍")
    try:
        await context.bot.set_message_reaction(
            chat_id=chat_id, 
            message_id=message_id, 
            reaction=[{"type": "emoji", "emoji": emoji}]
        )
    except: pass

# =========================================================
# MOTOR VISUAL (2 FPS)
# =========================================================
async def game_loop(context, chat_id):
    while chat_id in games:
        game = games[chat_id]
        try:
            txt = getattr(game, 'last_event_text', "El show continúa...")
            mood = getattr(game, 'last_mood', "default")
            player = game.current_player()
            keyboard = None

            # INTERFAZ LIMPIA: Sin tienda. Solo votar o continuar.
            if not game.pending_vote:
                if not player.get("is_npc") and getattr(game, 'waiting_continue', False):
                    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Continuar Turno", callback_data="continue")]])
                else:
                    keyboard = None # NPCs y humanos en movimiento no ven botones

                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=game.message_id,
                    text=render_game(game, txt, mood),
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML
                )
        except Exception: pass
        await asyncio.sleep(0.6)

# =========================================================
# LÓGICA DE FLUJO AUTOMÁTICO
# =========================================================
async def execute_auto_turn(context, game):
    if game.chat_id not in games: return
    
    player = game.current_player()
    game.waiting_continue = False

    # 1. Votación aleatoria (Solo en turnos humanos)
    if not player.get("is_npc") and random.random() < 0.15 and len(game.players) > 1:
        game.pending_vote = {"votos": {}}
        botones = [[InlineKeyboardButton(f"🍴 Sacrificar a {p['name']}", callback_data=f"vote_{pid}")] for pid, p in game.players.items()]
        await context.bot.edit_message_text(
            chat_id=game.chat_id,
            message_id=game.message_id,
            text=render_game(game, VOTACIONES["liebre"]["pregunta"], "vote"),
            reply_markup=InlineKeyboardMarkup(botones),
            parse_mode=ParseMode.HTML
        )
        await set_reaction(context, game.chat_id, game.message_id, "vote")
        return 

    await asyncio.sleep(1.2) 

    # 2. Dado Automático
    dice = random.randint(1, 6)
    bono = player.get("modifier", 0)
    total_move = dice + bono
    player["modifier"] = 0
    player["pos"] = safe_pos(player["pos"] + total_move, game.max_pos)
    
    game.last_event_text = f"🎲 **{player['name']}** sacó un {dice}" + (f" (+{bono})" if bono > 0 else "")
    game.last_mood = "roll"
    await set_reaction(context, game.chat_id, game.message_id, "roll")

    # 3. Objetos Automáticos (Sin Tienda)
    if player["pos"] > 0 and (player["pos"] % 5 == 0 or player["pos"] % 7 == 0):
        item = random.choice(list(ITEMS.values()))
        game.last_event_text += f"\n🎁 ¡Casilla especial! Obtiene: {item['name']}"
        if item["tipo"] == "move":
            player["pos"] = safe_pos(player["pos"] + item["valor"], game.max_pos)
        elif item["tipo"] == "boost":
            player["modifier"] = item["valor"]
        elif item["tipo"] == "trap":
            target_id = random.choice([pid for pid in game.order if pid != game.current_player_id()])
            game.players[target_id]["pos"] = safe_pos(game.players[target_id]["pos"] - 5, game.max_pos)
            game.last_event_text += f"\n¡Lanzó la trampa a {game.players[target_id]['name']}!"

    # 4. Victoria
    if player["pos"] >= game.max_pos:
        game.last_event_text = f"🏆 ¡{player['name']} HA GANADO! 🏆"
        game.last_mood = "win"
        await set_reaction(context, game.chat_id, game.message_id, "win")
        return

    # 5. Control de Turno
    if player.get("is_npc"):
        await asyncio.sleep(2.0) 
        game.next_turn()
        asyncio.create_task(execute_auto_turn(context, game))
    else:
        game.waiting_continue = True 

# =========================================================
# COMANDOS Y BOTONES
# =========================================================
async def unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id not in rooms: rooms[chat_id] = []
    if any(p["id"] == user.id for p in rooms[chat_id]): return
    user_emoji = random.choice(PLAYER_EMOJIS)
    rooms[chat_id].append({"id": user.id, "name": user.first_name, "emoji": user_emoji, "is_npc": False})
    await update.message.reply_text(f"✅ {user.first_name} listo.")

async def jugar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in rooms or len(rooms[chat_id]) < 1: return
    
    jugadores = rooms[chat_id]
    if len(jugadores) == 1:
        jugadores.append({"id": 101, "name": "Primo de Pipa", "emoji": "🤡", "is_npc": True})
    if len(jugadores) < 3:
        jugadores.append({"id": 102, "name": "Pipa Senior", "emoji": "👴", "is_npc": True})

    game = MisterPipaGame(chat_id, jugadores)
    game.last_event_text = "¡Mister Pipa da la salida! 🚩"
    games[chat_id] = game
    del rooms[chat_id]

    msg = await context.bot.send_message(chat_id=chat_id, text=render_game(game, game.last_event_text), parse_mode=ParseMode.HTML)
    game.message_id = msg.message_id
    asyncio.create_task(game_loop(context, chat_id))
    asyncio.create_task(execute_auto_turn(context, game))

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    game = games.get(query.message.chat_id)
    if not game: return
    data = query.data

    if data.startswith("vote_"):
        game.pending_vote["votos"][query.from_user.id] = int(data.split("_")[1])
        for pid, p in game.players.items():
            if p.get("is_npc") and pid not in game.pending_vote["votos"]:
                game.pending_vote["votos"][pid] = random.choice(game.order)

        if len(game.pending_vote["votos"]) >= len(game.players):
            v_list = list(game.pending_vote["votos"].values())
            victima = max(set(v_list), key=v_list.count)
            game.players[victima]["pos"] = safe_pos(game.players[victima]["pos"] - 15, game.max_pos)
            game.last_event_text = f"🗳 SACRIFICIO: {game.players[victima]['name']} retrocede."
            game.pending_vote = None
            await asyncio.sleep(2)
            asyncio.create_task(execute_auto_turn(context, game))

    if data == "continue":
        if game.current_player_id() == query.from_user.id:
            game.next_turn()
            asyncio.create_task(execute_auto_turn(context, game))

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("unirse", unirse))
    app.add_handler(CommandHandler("jugar", jugar))
    app.add_handler(CallbackQueryHandler(buttons))
    app.run_polling()
