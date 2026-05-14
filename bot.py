import os
import random
import asyncio
import time # Necesario para los temporizadores

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
from dialogos import DIALOGOS # Importamos tu nuevo guion

# =========================================================
# CASILLAS ESPECIALES (IMPORTACIÓN SEGURA)
# =========================================================
try:
    from events import SPECIAL_CELLS
except ImportError:
    SPECIAL_CELLS = {
        5: ("¡Mister Pipa te regala un batido energético!", 10),
        19: ("¡Atajo por las alcantarillas!", 35),
        34: ("¡Lodo pegajoso!", 27),
        94: ("¡Un bache gigante!", 85),
    }

TOKEN = os.getenv("TELEGRAM_TOKEN")

games = {}
rooms = {}

# =========================================================
# GESTIÓN DE DIÁLOGOS
# =========================================================

async def obtener_comentario(categoria):
    """Selecciona una frase al azar de tu archivo dialogos.py"""
    return random.choice(DIALOGOS.get(categoria, ["..."]))

# =========================================================
# REACCIONES
# =========================================================

async def set_reaction(context, chat_id, message_id, reaction_type):
    reactions = {
        "roll": "🎲", "win": "🎉", "boost": "⚡", "fire": "🔥", 
        "bad": "😱", "sabotage": "💢", "vote": "🗳️"
    }
    try:
        emoji = reactions.get(reaction_type, "✨")
        from telegram import ReactionTypeEmoji
        await context.bot.set_message_reaction(
            chat_id=chat_id, message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji)]
        )
    except Exception as e:
        print(f"REACTION LOG: {e}")

# =========================================================
# VIGILANTE DE INACTIVIDAD (20 SEGUNDOS)
# =========================================================

async def check_inactivity(context: ContextTypes.DEFAULT_TYPE):
    """Victoria por abandono si pasan 20s sin tocar botones"""
    current_time = time.time()
    to_delete = []

    for chat_id, game in list(games.items()):
        if hasattr(game, 'last_action_time') and (current_time - game.last_action_time) > 20:
            leader_id = max(game.players, key=lambda p: game.players[p]['pos'])
            leader_name = game.players[leader_id]['name']
            
            frase_azar = await obtener_comentario("comentario_azar")
            texto_final = (
                f"⏰ <b>¡TIEMPO AGOTADO!</b>\n\n"
                f"🧐 <i>{frase_azar}</i>\n\n"
                f"Como alguien se quedó dormido, Mister Pipa declara ganador a <b>{leader_name}</b> por abandono. 🏆"
            )
            
            try:
                text_completo = render_game(game, texto_final, "joke")
                await context.bot.send_message(chat_id=chat_id, text=text_completo, parse_mode=ParseMode.HTML)
            except: pass
            to_delete.append(chat_id)

    for chat_id in to_delete:
        if chat_id in games: del games[chat_id]

# =========================================================
# EVENTOS
# =========================================================

async def apply_random_event(game, player):
    # 1. Casillas Especiales
    if player["pos"] in SPECIAL_CELLS:
        msg, new_pos = SPECIAL_CELLS[player["pos"]]
        player["pos"] = safe_pos(new_pos, game.max_pos)
        return f"\n✨ {msg}", "boost" if new_pos > player["pos"] else "bad", None

    # 2. Objetos (25%)
    if random.random() < 0.25:
        item = ITEMS[random.randint(1, 4)]
        game.pending_action = {
            "type": "use_item",
            "item": item,
            "attacker_id": game.current_player_id(),
            "expire_time": time.time() + 4
        }
        victims = [[InlineKeyboardButton(f"🎯 {p['name']}", callback_data=f"target_{pid}")] 
                   for pid, p in game.players.items() if pid != game.current_player_id()]
        
        frase = await obtener_comentario("sabotaje")
        return f"\n🎁 {frase}\n¡Tienes un **{item['name']}**! ¿A quién atacas? (4s)", "sabotage", InlineKeyboardMarkup(victims)

    # 3. Votación (15%)
    if random.random() < 0.15:
        target_id = random.choice(game.order)
        game.pending_vote = {"target": target_id, "votes": {}}
        for pid, pdata in game.players.items():
            if pdata.get("is_npc"): game.pending_vote["votes"][pid] = random.choice([True, False])
        
        frase = await obtener_comentario("votacion_abierta")
        return f"\n🗳️ {frase}\n¿Hacemos que {game.players[target_id]['name']} retroceda 10m?", "vote", None

    return "", "default", None

async def check_npc_turn(context, game):
    if game.chat_id not in games or game.processing: return
    
    if game.pending_action and time.time() > game.pending_action.get("expire_time", 0):
        game.pending_action = None
        game.next_turn()
        await context.bot.edit_message_text(
            chat_id=game.chat_id, message_id=game.message_id,
            text=render_game(game, "⏰ ¡Tiempo agotado!", "joke"),
            reply_markup=main_keyboard(), parse_mode=ParseMode.HTML
        )

    if game.pending_vote or not str(game.current_player_id()).startswith("npc_"): return

    game.processing = True
    try:
        player = game.current_player()
        await asyncio.sleep(1.5)
        dice = random.randint(1, 6)
        player["pos"] = safe_pos(player["pos"] + dice, game.max_pos)
        event_msg = f"🤖 {player['name']} avanzó {dice}m."
        mood = "roll"

        extra_msg, extra_mood, _ = await apply_random_event(game, player)
        event_msg += extra_msg
        
        if player["pos"] >= game.max_pos:
            await context.bot.edit_message_text(chat_id=game.chat_id, message_id=game.message_id, text=render_game(game, f"🏆 ¡GANÓ {player['name']}!", "win"), parse_mode=ParseMode.HTML)
            if game.chat_id in games: del games[game.chat_id]
            return

        game.next_turn()
        game.last_action_time = time.time()
        await context.bot.edit_message_text(chat_id=game.chat_id, message_id=game.message_id, text=render_game(game, event_msg, extra_mood or mood), reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
    finally:
        game.processing = False
    await asyncio.sleep(2)
    await check_npc_turn(context, game)

# =========================================================
# COMANDOS Y BOTONES
# =========================================================

async def unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id in games: return
    if chat_id not in rooms: rooms[chat_id] = []
    if not any(p["id"] == user.id for p in rooms[chat_id]):
        rooms[chat_id].append({"id": user.id, "name": user.first_name, "emoji": random.choice(PLAYER_EMOJIS)})
        await update.message.reply_text(f"🎮 {user.first_name} unido ({len(rooms[chat_id])}/{MAX_PLAYERS})")

async def jugar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games or len(rooms.get(chat_id, [])) < 1: return
    players = rooms[chat_id]
    while len(players) < 2:
        nid = f"npc_{random.randint(1000,9999)}"
        players.append({"id": nid, "name": f"Bot_{nid[-3:]}", "emoji": "🤖"})
    game = MisterPipaGame(chat_id, players)
    games[chat_id] = game
    msg = await update.message.reply_text(render_game(game, "🏁 ¡INICIO!"), reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
    game.message_id = msg.message_id
    del rooms[chat_id]
    await check_npc_turn(context, game)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    game = games.get(query.message.chat_id)
    if not game: return
    game.last_action_time = time.time()

    if query.data.startswith("target_") and game.pending_action:
        target = game.players[query.data.replace("target_", "")]
        target["pos"] = safe_pos(target["pos"] - 5, game.max_pos)
        game.pending_action = None
        game.next_turn()
        await query.edit_message_text(render_game(game, f"💢 Ataque contra {target['name']}", "sabotage"), reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
        await check_npc_turn(context, game)

    elif query.data == "roll" and not game.processing and game.current_player_id() == query.from_user.id:
        game.processing = True
        player = game.current_player()
        dice = random.randint(1, 6)
        player["pos"] = safe_pos(player["pos"] + dice, game.max_pos)
        msg, mood, markup = await apply_random_event(game, player)
        if player["pos"] >= game.max_pos:
            await query.edit_message_text(render_game(game, "🏆 ¡GANASTE!", "win"), parse_mode=ParseMode.HTML)
            del games[game.chat_id]
        else:
            if not game.pending_action: game.next_turn()
            await query.edit_message_text(render_game(game, f"🎲 Sacaste {dice}.{msg}", mood), reply_markup=markup or main_keyboard(), parse_mode=ParseMode.HTML)
            game.processing = False
            if not game.pending_action: await check_npc_turn(context, game)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("unirse", unirse))
    app.add_handler(CommandHandler("jugar", jugar))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # --- CORRECCIÓN PARA RENDER: JobQueue seguro ---
    if app.job_queue:
        app.job_queue.run_repeating(check_inactivity, interval=5, first=5)
    else:
        print("ADVERTENCIA: JobQueue no disponible. El vigilante de inactividad no se activará.")
    
    print("Mister Pipa Online...")
    app.run_polling()
