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

# Importamos solo el diccionario si existe, si no, lo definimos para evitar el ImportError
try:
    from events import SPECIAL_CELLS
except ImportError:
    SPECIAL_CELLS = {
        5: ("¡Mister Pipa te regala un batido energético!", 10),
        12: ("Te detienes a firmar autógrafos y pierdes el ritmo.", 8),
        19: ("¡Atajo por las alcantarillas! Apareces mucho más adelante.", 35),
        28: ("Un viento fuerte te empuja hacia atrás.", 20),
        34: ("¡Lodo pegajoso! Te cuesta salir de aquí.", 27),
        46: ("Un fan emocionado te carga en hombros.", 55),
        58: ("Te equivocas de camino en la selva.", 50),
        65: ("¡Encuentras un patinete abandonado!", 75),
        82: ("¡Turbo ilegal activado! ¡Vuela!", 95),
        94: ("¡Un bache gigante! Retrocedes por el golpe.", 85),
        105: ("Recta final: ¡La adrenalina te hace correr!", 115),
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

    for chat_id, game in games.items():
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
# LÓGICA DE EVENTOS INTEGRADA (PARA EVITAR IMPORT ERROR)
# =========================================================

async def apply_random_event(game, player):
    event_text = ""
    mood = "default"
    markup = None

    # 1. Comprobar Casillas Especiales (Prioridad 1)
    current_pos = player["pos"]
    if current_pos in SPECIAL_CELLS:
        msg, new_pos = SPECIAL_CELLS[current_pos]
        player["pos"] = safe_pos(new_pos, game.max_pos)
        event_text = f"\n✨ <b>CASILLA ESPECIAL:</b> {msg}"
        mood = "boost" if new_pos > current_pos else "bad"
        return event_text, mood, None

    # 2. Probabilidad de Objeto con ELECCIÓN (25%)
    if random.random() < 0.25:
        item = ITEMS[random.randint(1, 4)]
        game.pending_action = {
            "type": "use_item",
            "item": item,
            "attacker_id": game.current_player_id(),
            "expire_time": time.time() + 4
        }
        victims = []
        for pid, pdata in game.players.items():
            if pid != game.current_player_id():
                victims.append([InlineKeyboardButton(f"🎯 {pdata['name']}", callback_data=f"target_{pid}")])
        
        markup = InlineKeyboardMarkup(victims)
        frase = await obtener_comentario("sabotaje")
        return f"\n🎁 {frase}\n¡Tienes un **{item['name']}**! ¿A quién atacas? (4s)", "sabotage", markup

    # 3. Votaciones (15%)
    if random.random() < 0.15:
        target_id = random.choice(game.order)
        game.pending_vote = {"target": target_id, "votes": {}}
        for pid, pdata in game.players.items():
            if pdata.get("is_npc"):
                game.pending_vote["votes"][pid] = random.choice([True, False])
        
        frase = await obtener_comentario("votacion_abierta")
        target_name = game.players[target_id]['name']
        return f"\n🗳️ {frase}\n¿Hacemos que {target_name} retroceda 10m?", "vote", None

    # 4. Comentario Random (10%)
    if random.random() < 0.10:
        frase = await obtener_comentario("comentario_azar")
        return f"\n🧐 {frase}", "default", None
    
    return "", "default", None

async def check_npc_turn(context, game):
    if game.chat_id not in games or game.processing: return
    
    if game.pending_action:
        if time.time() > game.pending_action.get("expire_time", 0):
            game.pending_action = None
            game.next_turn()
            text = render_game(game, "⏰ ¡Tiempo agotado para el ataque! El objeto se ha perdido.", "joke")
            await context.bot.edit_message_text(
                chat_id=game.chat_id, message_id=game.message_id,
                text=text, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML
            )
        else:
            return 

    if game.pending_vote: return 
    if not str(game.current_player_id()).startswith("npc_"): return

    game.processing = True
    try:
        player = game.current_player()
        await asyncio.sleep(1.5)
        dice = random.randint(1, 6)
        
        comentario_dado = ""
        if dice == 6: comentario_dado = f"\n⚡ {await obtener_comentario('sacar_6')}"
        elif dice == 1: comentario_dado = f"\n🐢 {await obtener_comentario('sacar_1')}"

        player["pos"] = safe_pos(player["pos"] + dice, game.max_pos)
        event_msg = f"🤖 {player['name']} avanzó {dice}m.{comentario_dado}"
        mood = "roll"

        extra_msg, extra_mood, _ = await apply_random_event(game, player)
        if extra_msg:
            event_msg += extra_msg
            mood = extra_mood

        if player["pos"] >= game.max_pos:
            text = render_game(game, f"🏆 ¡{player['name']} HA GANADO! 🏆", "win")
            await context.bot.edit_message_text(chat_id=game.chat_id, message_id=game.message_id, text=text, parse_mode=ParseMode.HTML)
            if game.chat_id in games: del games[game.chat_id]
            return

        game.next_turn()
        game.last_action_time = time.time()
        text = render_game(game, event_msg, mood)
        await context.bot.edit_message_text(
            chat_id=game.chat_id, message_id=game.message_id,
            text=text, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML
        )
        await set_reaction(context, game.chat_id, game.message_id, mood)
    finally:
        game.processing = False

    await asyncio.sleep(2)
    if game.chat_id in games and str(game.current_player_id()).startswith("npc_"):
        await check_npc_turn(context, game)

# =========================================================
# COMANDOS
# =========================================================

async def unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id in games:
        await update.message.reply_text("❌ Partida en curso.")
        return
    if chat_id not in rooms: rooms[chat_id] = []
    if any(p["id"] == user.id for p in rooms[chat_id]):
        await update.message.reply_text("✅ Ya estás dentro.")
        return
    if len(rooms[chat_id]) >= MAX_PLAYERS:
        await update.message.reply_text("❌ Sala llena.")
        return
    rooms[chat_id].append({"id": user.id, "name": user.first_name, "emoji": random.choice(PLAYER_EMOJIS)})
    await update.message.reply_text(f"🎮 {user.first_name} se unió ({len(rooms[chat_id])}/{MAX_PLAYERS})")

async def jugar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games: return
    players = rooms.get(chat_id, [])
    if len(players) < 1:
        await update.message.reply_text("❌ Mínimo 1 jugador.")
        return
    while len(players) < 2:
        npc_id = f"npc_{random.randint(1000, 9999)}"
        players.append({"id": npc_id, "name": f"Bot_{npc_id[-3:]}", "emoji": "🤖"})

    game = MisterPipaGame(chat_id, players)
    game.last_action_time = time.time()
    games[chat_id] = game
    text = render_game(game, "🏁 ¡La carrera ha comenzado! 🏁")
    msg = await update.message.reply_text(text, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
    game.message_id = msg.message_id
    if chat_id in rooms: del rooms[chat_id]
    await check_npc_turn(context, game)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    if chat_id not in games: return
    game = games[chat_id]
    game.last_action_time = time.time()

    if query.data.startswith("target_"):
        if not game.pending_action or game.pending_action["attacker_id"] != user_id: return
        target_id = query.data.replace("target_", "")
        item = game.pending_action["item"]
        target = game.players[target_id]
        target["pos"] = safe_pos(target["pos"] + item.get("valor", -5), game.max_pos)
        game.pending_action = None
        game.next_turn()
        text = render_game(game, f"💢 ¡Blanco fijado!\nUsaste {item['name']} contra {target['name']}.", "sabotage")
        await query.edit_message_text(text, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
        await asyncio.sleep(2)
        await check_npc_turn(context, game)
        return

    if query.data in ["vote_yes", "vote_no"]:
        if game.pending_vote:
            game.pending_vote["votes"][user_id] = (query.data == "vote_yes")
            if len(game.pending_vote["votes"]) >= len(game.order):
                v_si = sum(1 for v in game.pending_vote["votes"].values() if v)
                v_no = sum(1 for v in game.pending_vote["votes"].values() if not v)
                res, pipa_msg = (v_si > v_no, "¡La mayoría ha decidido!") if v_si != v_no else game.resolve_vote_pipa()
                if res:
                    target = game.players[game.pending_vote["target"]]
                    target["pos"] = safe_pos(target["pos"] - 10, game.max_pos)
                game.pending_vote = None
                await query.edit_message_text(render_game(game, f"📊 Votación terminada...", "vote"), parse_mode=ParseMode.HTML)
                await asyncio.sleep(0.8)
                await query.edit_message_text(render_game(game, f"📊 Resultado: {pipa_msg}", "result"), reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
                await asyncio.sleep(2)
                await check_npc_turn(context, game)
        return

    if game.processing or game.current_player_id() != user_id or query.data != "roll": return
    game.processing = True
    try:
        player = game.current_player()
        dice = random.randint(1, 6)
        comentario_dado = f"\n⚡ {await obtener_comentario('sacar_6')}" if dice == 6 else (f"\n🐢 {await obtener_comentario('sacar_1')}" if dice == 1 else "")
        player["pos"] = safe_pos(player["pos"] + dice, game.max_pos)
        event_msg = f"🎲 Lanzaste un {dice}.{comentario_dado}"
        
        if player["pos"] >= game.max_pos:
            await query.edit_message_text(render_game(game, f"🏆 ¡{player['name']} HA GANADO! 🏆", "win"), parse_mode=ParseMode.HTML)
            if chat_id in games: del games[chat_id]
            return

        extra_msg, mood, extra_markup = await apply_random_event(game, player)
        event_msg += extra_msg
        if not game.pending_action:
            game.next_turn()
            markup = vote_keyboard() if game.pending_vote else main_keyboard()
        else:
            markup = extra_markup
        await query.edit_message_text(render_game(game, event_msg, mood), reply_markup=markup, parse_mode=ParseMode.HTML)
    finally:
        game.processing = False
    if not game.pending_action: await check_npc_turn(context, game)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("unirse", unirse))
    app.add_handler(CommandHandler("jugar", jugar))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.job_queue.run_repeating(check_inactivity, interval=5, first=5)
    print("Mister Pipa Online...")
    app.run_polling()
