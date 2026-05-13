import os
import random
import asyncio
import time # Necesario para el temporizador de 4 segundos

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
# EVENTOS (ACTUALIZADO CON ELECCIÓN Y DIÁLOGOS)
# =========================================================

async def apply_random_event(game, player):
    # 1. Probabilidad de Objeto con ELECCIÓN (25%)
    if random.random() < 0.25:
        item = ITEMS[random.randint(1, 4)] # Ítems de ataque/movimiento
        
        # Guardamos la acción pendiente para esperar la elección del jugador
        game.pending_action = {
            "type": "use_item",
            "item": item,
            "attacker_id": game.current_player_id(),
            "expire_time": time.time() + 4 # 4 segundos exactos
        }
        
        # Crear botones de víctimas
        victims = []
        for pid, pdata in game.players.items():
            if pid != game.current_player_id():
                victims.append([InlineKeyboardButton(f"🎯 {pdata['name']}", callback_data=f"target_{pid}")])
        
        markup = InlineKeyboardMarkup(victims)
        frase = await obtener_comentario("sabotaje")
        return f"\n🎁 {frase}\n¡Tienes un **{item['name']}**! ¿A quién atacas? (4s)", "sabotage", markup

    # 2. ACTIVACIÓN DE VOTACIÓN (15%) con tus diálogos
    if random.random() < 0.15:
        target_id = random.choice(game.order)
        game.pending_vote = {"target": target_id, "votes": {}}
        
        for pid, pdata in game.players.items():
            if pdata.get("is_npc"):
                game.pending_vote["votes"][pid] = random.choice([True, False])
        
        frase = await obtener_comentario("votacion_abierta")
        target_name = game.players[target_id]['name']
        return f"\n🗳️ {frase}\n¿Hacemos que {target_name} retroceda 10m?", "vote", None

    # 3. Comentario aleatorio de Mister Pipa (10%)
    if random.random() < 0.10:
        frase = await obtener_comentario("comentario_azar")
        return f"\n🧐 {frase}", "default", None
    
    return "", "default", None

async def check_npc_turn(context, game):
    if game.chat_id not in games or game.processing: return
    if game.pending_vote or game.pending_action: # NPCs esperan si hay acción pendiente
        return 

    if not str(game.current_player_id()).startswith("npc_"): return

    game.processing = True
    try:
        player = game.current_player()
        await asyncio.sleep(1.5)
        dice = random.randint(1, 6)
        
        # Diálogo según el dado
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
        text = render_game(game, event_msg, mood)
        markup = main_keyboard() # Los NPCs no activan menús de elección para humanos

        await context.bot.edit_message_text(
            chat_id=game.chat_id, message_id=game.message_id,
            text=text, reply_markup=markup, parse_mode=ParseMode.HTML
        )
        await set_reaction(context, game.chat_id, game.message_id, mood)
    finally:
        game.processing = False

    await asyncio.sleep(2)
    if game.chat_id in games and str(game.current_player_id()).startswith("npc_"):
        await check_npc_turn(context, game)

# =========================================================
# BOTONES (MODIFICADO PARA EL TEMPORIZADOR Y ATAQUES)
# =========================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    if chat_id not in games: return
    game = games[chat_id]

    # --- LÓGICA DE ATAQUE DIRIGIDO ---
    if query.data.startswith("target_"):
        if not game.pending_action or game.pending_action["attacker_id"] != user_id:
            return
        
        target_id = query.data.replace("target_", "")
        item = game.pending_action["item"]
        
        # Verificar si expiró el tiempo
        if time.time() > game.pending_action["expire_time"]:
            # Elección aleatoria por tardón
            target_id = random.choice([pid for pid in game.order if pid != user_id])
            pipa_msg = "¡Muy lento! Pipa eligió por ti."
        else:
            pipa_msg = "¡Blanco fijado!"

        target = game.players[target_id]
        target["pos"] = safe_pos(target["pos"] + item.get("valor", -5), game.max_pos)
        
        game.pending_action = None
        game.next_turn()
        
        text = render_game(game, f"💢 {pipa_msg}\nUsaste {item['name']} contra {target['name']}.", "sabotage")
        await query.edit_message_text(text, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
        await asyncio.sleep(2)
        await check_npc_turn(context, game)
        return

    # --- VOTACIONES ---
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
                res_txt = "✅ SÍ" if res else "❌ NO"
                await query.edit_message_text(render_game(game, f"📊 Votación: {res_txt}...", "vote"), parse_mode=ParseMode.HTML)
                await asyncio.sleep(0.8)
                await query.edit_message_text(render_game(game, f"📊 {res_txt}\n{pipa_msg}", "result"), reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
                await asyncio.sleep(2)
                await check_npc_turn(context, game)
        return

    # --- DADO ---
    if game.processing or game.current_player_id() != user_id or query.data != "roll": return

    game.processing = True
    try:
        player = game.current_player()
        dice = random.randint(1, 6)
        
        comentario_dado = ""
        if dice == 6: comentario_dado = f"\n⚡ {await obtener_comentario('sacar_6')}"
        elif dice == 1: comentario_dado = f"\n🐢 {await obtener_comentario('sacar_1')}"

        player["pos"] = safe_pos(player["pos"] + dice, game.max_pos)
        event_msg = f"🎲 Lanzaste un {dice}.{comentario_dado}"
        
        if player["pos"] >= game.max_pos:
            text = render_game(game, f"🏆 ¡{player['name']} HA GANADO! 🏆", "win")
            await query.edit_message_text(text, parse_mode=ParseMode.HTML)
            if chat_id in games: del games[chat_id]
            return

        # Aplicar evento
        extra_msg, mood, extra_markup = await apply_random_event(game, player)
        event_msg += extra_msg
        
        # Si NO hay una acción de elegir víctima, pasamos el turno
        if not game.pending_action:
            game.next_turn()
            markup = vote_keyboard() if game.pending_vote else main_keyboard()
        else:
            markup = extra_markup # Mostramos los botones de víctimas

        await query.edit_message_text(render_game(game, event_msg, mood), reply_markup=markup, parse_mode=ParseMode.HTML)
    finally:
        game.processing = False
    
    if not game.pending_action:
        await check_npc_turn(context, game)

# (Los comandos unirse, jugar y el bloque main se mantienen idénticos a tu código original)
