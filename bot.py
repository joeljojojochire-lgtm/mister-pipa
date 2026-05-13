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
from ui import render_game, main_keyboard, shop_keyboard
from items import ITEMS, SHOP_RESPAWN
from utils import safe_pos
from config import MAX_PLAYERS, PLAYER_EMOJIS, PIPA_EMOJIS

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
        "roll": "🎲", "win": "🎉", "buy": "🤑", "fire": "🔥",
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
        # Eliminamos el "if not game.pending_vote" para que el tablero NO se detenga
        try:
            txt = getattr(game, 'last_event_text', "El show continúa...")
            mood = getattr(game, 'last_mood', "default")
            
            # Solo manejamos el teclado si NO hay votación activa
            if not game.pending_vote:
                if not game.current_player().get("is_npc") and getattr(game, 'waiting_continue', False):
                    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Continuar Turno", callback_data="continue")]])
                elif getattr(game, 'ui_state', 'main') == 'shop':
                    keyboard = shop_keyboard(game, game.current_player())
                else:
                    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Abrir Tienda", callback_data="shop")]])
                
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=game.message_id,
                    text=render_game(game, txt, mood),
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML
                )
        except Exception: 
            pass # Si hay error (como el de Conflict), el loop sigue intentando
            
        await asyncio.sleep(0.6) # Un poquito más lento para que Render no tire el error de Conflict
# =========================================================
# LÓGICA DE FLUJO AUTOMÁTICO (DADO + ITEMS + NPCs)
# =========================================================
async def execute_auto_turn(context, game):
    if game.chat_id not in games: return
    
    player = game.current_player()
    game.waiting_continue = False

    # 1. Probabilidad de Evento Vital (Votación) - SOLO EN TURNOS DE HUMANOS
    if not player.get("is_npc") and random.random() < 0.15 and len(game.players) > 1:
        game.pending_vote = {"votos": {}}
        botones = [[InlineKeyboardButton(f"🍴 Sacrificar a {p['name']}", callback_data=f"vote_{pid}")] for pid, p in game.players.items()]
        
        # Detenemos el loop visual editando manualmente para mostrar la votación
        await context.bot.edit_message_text(
            chat_id=game.chat_id,
            message_id=game.message_id,
            text=render_game(game, VOTACIONES["liebre"]["pregunta"], "vote"),
            reply_markup=InlineKeyboardMarkup(botones),
            parse_mode=ParseMode.HTML
        )
        await set_reaction(context, game.chat_id, game.message_id, "vote")
        return 

    await asyncio.sleep(1.5) 

    # 2. Lanzamiento de Dado Automático
    dice = random.randint(1, 6)
    bono = player.get("modifier", 0)
    total_move = dice + bono
    player["modifier"] = 0
    player["pos"] = safe_pos(player["pos"] + total_move, game.max_pos)
    
    game.last_event_text = f"🎲 **{player['name']}** sacó un {dice}" + (f" (+{bono} extra)" if bono > 0 else "")
    game.last_mood = "roll"
    await set_reaction(context, game.chat_id, game.message_id, "roll")

    # 3. Casillas de Objetos Automáticas
    if player["pos"] > 0 and (player["pos"] % 5 == 0 or player["pos"] % 7 == 0):
        item = random.choice(list(ITEMS.values()))
        game.last_event_text += f"\n🎁 ¡Casilla especial! Obtiene: {item['name']}"
        if item["tipo"] == "move":
            player["pos"] = safe_pos(player["pos"] + item["valor"], game.max_pos)
        elif item["tipo"] == "trap":
            target_id = random.choice([pid for pid in game.order if pid != game.current_player_id()])
            game.players[target_id]["pos"] = safe_pos(game.players[target_id]["pos"] - 5, game.max_pos)
            game.last_event_text += f"\n¡Y sabotea a {game.players[target_id]['name']}!"

    # 4. Verificar Victoria
    if player["pos"] >= game.max_pos:
        game.last_event_text = f"🏆 ¡{player['name']} HA GANADO EL SHOW! 🏆"
        game.last_mood = "result"
        await set_reaction(context, game.chat_id, game.message_id, "win")
        return

    # 5. Siguiente Paso
    if player.get("is_npc"):
        await asyncio.sleep(2.5) 
        game.next_turn()
        await execute_auto_turn(context, game)
    else:
        game.waiting_continue = True 

# =========================================================
# COMANDOS Y BOTONES
# =========================================================

async def unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id not in rooms: rooms[chat_id] = []
    if any(p["id"] == user.id for p in rooms[chat_id]):
        return await update.message.reply_text("⚠️ Ya estás en la pista.")
    user_emoji = random.choice(PLAYER_EMOJIS)
    rooms[chat_id].append({"id": user.id, "name": user.first_name, "emoji": user_emoji, "is_npc": False})
    await update.message.reply_text(f"✅ **{user.first_name}** se unió con {user_emoji}")

async def jugar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in rooms or len(rooms[chat_id]) < 1:
        return await update.message.reply_text("❌ No hay corredores.")
    
    jugadores = rooms[chat_id]
    if len(jugadores) == 1:
        jugadores.append({"id": 101, "name": "Primo de Pipa", "emoji": "🤡", "is_npc": True})
    if len(jugadores) < 3:
        jugadores.append({"id": 102, "name": "Pipa Senior", "emoji": "👴", "is_npc": True})

    game = MisterPipaGame(chat_id, jugadores)
    game.last_event_text = "¡Mister Pipa da el pistoletazo de salida! 🚩"
    game.ui_state = "main"
    games[chat_id] = game
    del rooms[chat_id]

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=render_game(game, game.last_event_text),
        parse_mode=ParseMode.HTML
    )
    game.message_id = msg.message_id
    asyncio.create_task(game_loop(context, chat_id))
    await execute_auto_turn(context, game)

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    data = query.data
    if chat_id not in games: return
    game = games[chat_id]

    # Lógica de Votos
    if data.startswith("vote_"):
        if not game.pending_vote: return
        # Registrar voto del humano
        game.pending_vote["votos"][user_id] = int(data.split("_")[1])
        
        # NPCs votan inmediatamente (Cerebro del Bot)
        for pid, p in game.players.items():
            if p.get("is_npc") and pid not in game.pending_vote["votos"]:
                game.pending_vote["votos"][pid] = random.choice(game.order)

        # Si todos han votado (incluyendo bots), resolvemos
        if len(game.pending_vote["votos"]) >= len([p for p in game.players.values() if not p.get("is_npc") or True]):
            votos_lista = list(game.pending_vote["votos"].values())
            victima_id = max(set(votos_lista), key=votos_lista.count)
            game.players[victima_id]["pos"] = safe_pos(game.players[victima_id]["pos"] - 15, game.max_pos)
            
            game.last_event_text = f"🗳 **¡VOTACIÓN CERRADA!**\n\n{game.players[victima_id]['name']} fue sacrificado."
            game.last_mood = "joke"
            game.pending_vote = None
            await set_reaction(context, chat_id, game.message_id, "bad")
            await asyncio.sleep(2)
            await execute_auto_turn(context, game)
        return

    if data == "continue":
        if game.current_player_id() == user_id:
            game.next_turn()
            await execute_auto_turn(context, game)
        else:
            await query.answer("No es tu turno de continuar.")
        return

    if data == "shop":
        game.ui_state = "shop"
        game.last_event_text = "Mister Pipa abre su maletín... 💰"
    elif data == "back":
        game.ui_state = "main"
    elif data.startswith("buy_"):
        item_id = int(data.split("_")[1])
        item = ITEMS.get(item_id)
        player = game.current_player()
        if player["coins"] >= item["precio"]:
            player["coins"] -= item["precio"]
            if item["tipo"] == "move": player["pos"] = safe_pos(player["pos"] + item["valor"], game.max_pos)
            elif item["tipo"] == "boost": player["modifier"] = item["valor"]
            game.last_event_text = f"🛒 {player['name']} compró {item['name']}."
            game.ui_state = "main"
            await set_reaction(context, chat_id, game.message_id, "buy")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("unirse", unirse))
    app.add_handler(CommandHandler("jugar", jugar))
    app.add_handler(CallbackQueryHandler(buttons))
    app.run_polling()
