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
from ui import render_game, main_keyboard
from items import ITEMS
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
    """Añade una reacción visual al mensaje del tablero"""
    reactions = {
        "roll": "🎲",
        "win": "🎉",
        "boost": "⚡",
        "fire": "🔥",
        "bad": "😱",
        "sabotage": "💢"
    }
    try:
        emoji = reactions.get(reaction_type, "✨")
        await context.bot.set_message_reaction(chat_id, message_id, [emoji])
    except Exception:
        pass

# =========================================================
# LÓGICA DE TURNOS NPC (ESTABILIZADA Y CON EVENTOS)
# =========================================================
async def check_npc_turn(context, game):
    """Controlador automático para turnos de NPC con eventos aleatorios."""
    if not str(game.current_player_id()).startswith("npc_"):
        return
    if game.pending_vote or game.processing:
        return

    game.processing = True
    player = game.current_player()
    await asyncio.sleep(1.5)
    
    # 1. Movimiento base
    dice = random.randint(1, 6)
    total_move = dice + player.get("modifier", 0)
    player["modifier"] = 0
    player["pos"] = safe_pos(player["pos"] + total_move, game.max_pos)
    
    event_msg = f"🤖 {player['name']} lanzó el dado y avanzó {total_move}m."
    mood = "roll"

    # 2. Evento Aleatorio para NPC (30% prob)
    if random.random() < 0.30:
        item_id = random.choice(list(ITEMS.keys()))
        item = ITEMS[item_id]
        if item["tipo"] in ["move", "boost", "random"]:
            if item["tipo"] == "move":
                player["pos"] = safe_pos(player["pos"] + item["valor"], game.max_pos)
                event_msg += f"\n🎁 ¡Pipa le da {item['name']}! Avanza {item['valor']}m."
            elif item["tipo"] == "boost":
                player["modifier"] = item["valor"]
                event_msg += f"\n⚡ ¡Pipa le da {item['name']}! +{item['valor']} para su próximo turno."
            mood = "boost"
        elif item["tipo"] == "trap":
            target_idx = (game.current_idx + 1) % len(game.order)
            target = game.players[game.order[target_idx]]
            target["pos"] = safe_pos(target["pos"] + item["valor"], game.max_pos)
            event_msg += f"\n💢 ¡Pipa lanzó {item['name']} a {target['name']}! Retrocede {abs(item['valor'])}m."
            mood = "sabotage"

    # 3. Verificar Victoria
    if player["pos"] >= game.max_pos:
        text = render_game(game, f"🏆 ¡EL NPC {player['name']} HA GANADO! 🏆", "win")
        await context.bot.send_message(game.chat_id, text, parse_mode=ParseMode.HTML)
        if game.chat_id in games: del games[game.chat_id]
        return

    # 4. Siguiente turno y UI
    game.next_turn()
    game.processing = False
    text = render_game(game, event_msg, mood)
    await context.bot.edit_message_text(
        chat_id=game.chat_id, message_id=game.message_id,
        text=text, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML
    )

    # RECURSIÓN SEGURA
    await asyncio.sleep(2)
    if game.chat_id in games and str(game.current_player_id()).startswith("npc_"):
        await check_npc_turn(context, game)

# =========================================================
# HANDLERS DE COMANDOS
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
    games[chat_id] = game
    text = render_game(game, "🏁 ¡La carrera ha comenzado! 🏁")
    msg = await update.message.reply_text(text, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
    game.message_id = msg.message_id
    if chat_id in rooms: del rooms[chat_id]
    await check_npc_turn(context, game)

# =========================================================
# HANDLER DE BOTONES (CALLBACKS) - LÓGICA AUTOMÁTICA
# =========================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    if chat_id not in games: return
    game = games[chat_id]

    if game.current_player_id() != user_id or game.processing:
        await query.answer("⚠️ No es tu turno o procesando...", show_alert=True)
        return

    if query.data == "roll":
        game.processing = True
        player = game.current_player()
        
        dice = random.randint(1, 6)
        total_move = dice + player.get("modifier", 0)
        player["modifier"] = 0
        player["pos"] = safe_pos(player["pos"] + total_move, game.max_pos)
        
        event_msg = f"🎲 {player['name']} lanzó el dado y avanzó {total_move}m."
        mood = "roll"

        # EVENTO ALEATORIO (Sustituye a la tienda)
        if random.random() < 0.30:
            item_id = random.choice(list(ITEMS.keys()))
            item = ITEMS[item_id]
            if item["tipo"] in ["move", "boost", "random"]:
                if item["tipo"] == "move":
                    player["pos"] = safe_pos(player["pos"] + item["valor"], game.max_pos)
                    event_msg += f"\n🎁 ¡Pipa te regala {item['name']}! +{item['valor']}m."
                elif item["tipo"] == "boost":
                    player["modifier"] = item["valor"]
                    event_msg += f"\n⚡ ¡Pipa te da {item['name']}! Bono para el próximo turno."
                mood = "boost"
            elif item["tipo"] == "trap":
                target_idx = (game.current_idx + 1) % len(game.order)
                target = game.players[game.order[target_idx]]
                target["pos"] = safe_pos(target["pos"] + item["valor"], game.max_pos)
                event_msg += f"\n💢 ¡Pipa lanzó {item['name']} a {target['name']}! Retrocede."
                mood = "sabotage"

        if player["pos"] >= game.max_pos:
            text = render_game(game, f"🏆 ¡{player['name']} HA GANADO! 🏆", "win")
            await query.edit_message_text(text, parse_mode=ParseMode.HTML)
            if chat_id in games: del games[chat_id]
            return

        game.next_turn()
        game.processing = False
        text = render_game(game, event_msg, mood)
        await query.edit_message_text(text, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
        await set_reaction(context, chat_id, game.message_id, mood)
        
        await asyncio.sleep(2)
        await check_npc_turn(context, game)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("unirse", unirse))
    app.add_handler(CommandHandler("jugar", jugar))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Mister Pipa v2 (Eventos Automáticos) Online...")
    app.run_polling()
