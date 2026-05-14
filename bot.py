import os
import random
import asyncio
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

from game import MisterPipaGame
from ui import render_game, main_keyboard, vote_keyboard
from items import ITEMS
from utils import safe_pos
from config import MAX_PLAYERS, PLAYER_EMOJIS
from dialogos import DIALOGOS

# =========================================================
# REACCIONES Y UTILIDADES (MANTENIDAS COMPLEMENTAMENTE INTACTAS)
# =========================================================
from events import SPECIAL_CELLS

async def obtener_comentario(categoria):
    return random.choice(DIALOGOS.get(categoria, ["..."]))

async def set_reaction(context, chat_id, message_id, reaction_type):
    reactions = {"roll": "🎲", "win": "🎉", "boost": "⚡", "fire": "🔥", "bad": "😱", "sabotage": "💢", "vote": "🗳️"}
    try:
        from telegram import ReactionTypeEmoji
        await context.bot.set_message_reaction(chat_id=chat_id, message_id=message_id, reaction=[ReactionTypeEmoji(reactions.get(reaction_type, "✨"))])
    except: pass

# =========================================================
# MODIFICACIÓN: EVENTOS CON TEMPORIZADOR DE 10s
# =========================================================
async def apply_random_event(game, player):
    if player["pos"] in SPECIAL_CELLS:
        msg, new_pos = SPECIAL_CELLS[player["pos"]]
        player["pos"] = safe_pos(new_pos, game.max_pos)
        return f"\n✨ <b>CASILLA:</b> {msg}", "boost" if new_pos > player["pos"] else "bad", None

    # Objeto: ahora incluye expire_time (10 segundos)
    if random.random() < 0.25:
        item = ITEMS[random.randint(1, 4)]
        game.pending_action = {
            "type": "use_item",
            "item": item,
            "attacker_id": game.current_player_id(),
            "expire_time": time.time() + 10 # REGLA: 10 SEGUNDOS
        }
        victims = [[InlineKeyboardButton(f"🎯 {p['name']}", callback_data=f"target_{pid}")] 
                   for pid, p in game.players.items() if pid != game.current_player_id()]
        frase = await obtener_comentario("sabotaje")
        return f"\n🎁 {frase}\n¡Tienes un <b>{item['name']}</b>! ¿A quién atacas? (10s)", "sabotage", InlineKeyboardMarkup(victims)

    # Votación: ahora incluye expire_time (10 segundos)
    if random.random() < 0.15:
        target_id = random.choice(game.order)
        game.pending_vote = {
            "target": target_id, 
            "votes": {},
            "expire_time": time.time() + 10 # REGLA: 10 SEGUNDOS
        }
        
        # MODIFICACIÓN EXCLUSIVA: Los NPCs votan de inmediato al azar al crearse la votación
        for pid, p in game.players.items():
            if p.get("is_npc"):
                game.pending_vote["votes"][pid] = random.choice([True, False])
                
        frase = await obtener_comentario("votacion_abierta")
        return f"\n🗳️ {frase}\n¿Retrocedemos a {game.players[target_id]['name']}? (10s)", "vote", vote_keyboard()

    return "", "default", None

# =========================================================
# LÓGICA DE DADO AUTOMÁTICO Y CONTINUIDAD (CORRECCIÓN QUIRÚRGICA)
# =========================================================
async def check_npc_turn(context, game):
    if game.chat_id not in games: return
    
    # 1. Resolver acciones expiradas (10s)
    if game.pending_action and time.time() > game.pending_action.get("expire_time", 0):
        potential_victims = [pid for pid in game.order if pid != game.pending_action["attacker_id"]]
        victim_id = random.choice(potential_victims)
        target = game.players[victim_id]
        target["pos"] = safe_pos(target["pos"] - 5, game.max_pos)
        game.pending_action = None
        game.next_turn()
        await context.bot.edit_message_text(chat_id=game.chat_id, message_id=game.message_id, 
            text=render_game(game, f"⏰ Tiempo agotado. Pipa atacó a {target['name']} al azar.", "joke"),
            reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)

    # 2. Resolver votaciones expiradas (10s) u obtenidas con votos completos
    if game.pending_vote:
        human_players = [pid for pid, p in game.players.items() if not p.get("is_npc")]
        all_humans_voted = all(pid in game.pending_vote["votes"] for pid in human_players)
        
        if time.time() > game.pending_vote.get("expire_time", 0) or all_humans_voted:
            res, pipa_msg = game.resolve_vote_pipa()
            if res:
                target = game.players[game.pending_vote["target"]]
                target["pos"] = safe_pos(target["pos"] - 10, game.max_pos)
            game.pending_vote = None
            
            if not game.pending_action:
                game.next_turn()
                
            await context.bot.edit_message_text(chat_id=game.chat_id, message_id=game.message_id,
                text=render_game(game, f"🗳️ Votación concluida. Pipa decidió: {pipa_msg}", "vote"),
                reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)

    # CORRECCIÓN DE RE-INVOCACIÓN: Si hay una acción/voto de un humano esperando tiempo, 
    # salimos liberando el flujo correctamente sin atascar game.processing.
    if game.pending_action or game.pending_vote:
        # SI el jugador actual es un NPC y tiene una acción de ítem pendiente, la ejecuta AL INSTANTE
        if game.current_player().get("is_npc") and game.pending_action:
            potential_victims = [pid for pid in game.order if pid != game.current_player_id()]
            victim_id = random.choice(potential_victims)
            target = game.players[victim_id]
            target["pos"] = safe_pos(target["pos"] - 5, game.max_pos)
            game.pending_action = None
            game.next_turn()
            await context.bot.edit_message_text(chat_id=game.chat_id, message_id=game.message_id, 
                text=render_game(game, f"🤖 El Bot decidió usar su ítem instantáneamente contra {target['name']}.", "sabotage"),
                reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
        
        await asyncio.sleep(1)
        asyncio.create_task(check_npc_turn(context, game))
        return

    # Si ya está procesando el tiro de dado, no hacemos nada más en este ciclo
    if game.processing: return

    # 3. ACTIVACIÓN AUTOMÁTICA DEL DADO
    game.processing = True
    try:
        await asyncio.sleep(2) 
        player = game.current_player()
        dice = random.randint(1, 6)
        player["pos"] = safe_pos(player["pos"] + dice, game.max_pos)
        
        comentario = await obtener_comentario("sacar_6" if dice == 6 else "sacar_1" if dice == 1 else "inicio")
        msg_extra, mood, markup = await apply_random_event(game, player)
        
        if player["pos"] >= game.max_pos:
            await context.bot.edit_message_text(chat_id=game.chat_id, message_id=game.message_id, 
                text=render_game(game, f"🏆 ¡GANÓ {player['name']}!", "win"), parse_mode=ParseMode.HTML)
            if game.chat_id in games: del games[game.chat_id]
            return

        if not game.pending_action and not game.pending_vote:
            game.next_turn()

        await context.bot.edit_message_text(chat_id=game.chat_id, message_id=game.message_id,
            text=render_game(game, f"🎲 {player['name']} sacó {dice}. {comentario}{msg_extra}", mood),
            reply_markup=markup or main_keyboard(), parse_mode=ParseMode.HTML)
    finally:
        game.processing = False

    await asyncio.sleep(1)
    if game.chat_id in games and not game.pending_action and not game.pending_vote:
        await check_npc_turn(context, game)

# =========================================================
# COMANDOS Y HANDLERS (REVISADOS Y CONSERVADOS FIELMENTE)
# =========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN")
games = {}
rooms = {}

async def unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id in games: return
    if chat_id not in rooms: rooms[chat_id] = []
    if not any(p["id"] == user.id for p in rooms[chat_id]):
        rooms[chat_id].append({"id": user.id, "name": user.first_name, "emoji": random.choice(PLAYER_EMOJIS)})
        await update.message.reply_text(f"🎮 {user.first_name} unido.")

async def jugar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games or not rooms.get(chat_id): return
    players = rooms[chat_id]
    while len(players) < 2:
        nid = f"npc_{random.randint(100,999)}"
        # ADICIÓN CRÍTICA: Se añade explícitamente "is_npc": True para que el motor reconozca al bot
        players.append({"id": nid, "name": f"Bot_{nid}", "emoji": "🤖", "is_npc": True})
    game = MisterPipaGame(chat_id, players)
    games[chat_id] = game
    msg = await update.message.reply_text(render_game(game, "🏁 ¡COMIENZA LA CARRERA AUTOMÁTICA!"), reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
    game.message_id = msg.message_id
    del rooms[chat_id]
    asyncio.create_task(check_npc_turn(context, game))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    game = games.get(query.message.chat_id)
    if not game: return

    # Registrar voto y forzar check_npc_turn para resolver de inmediato
    if query.data in ["vote_yes", "vote_no"] and game.pending_vote:
        user_id = query.from_user.id
        if user_id in game.players:
            game.pending_vote["votes"][user_id] = (query.data == "vote_yes")
            asyncio.create_task(check_npc_turn(context, game))
        return

    if query.data.startswith("target_") and game.pending_action:
        target = game.players[query.data.replace("target_", "")]
        target["pos"] = safe_pos(target["pos"] - 5, game.max_pos)
        game.pending_action = None
        game.next_turn()
        await query.edit_message_text(render_game(game, f"💢 {game.current_player()['name']} eligió atacar a {target['name']}"), reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
        asyncio.create_task(check_npc_turn(context, game))

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("unirse", unirse))
    app.add_handler(CommandHandler("jugar", jugar))
    app.add_handler(CallbackQueryHandler(button_handler))
    run_queue = app.run_polling()
