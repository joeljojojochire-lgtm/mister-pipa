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
    """Añade una reacción visual al mensaje del tablero"""
    reactions = {
        "roll": "🎲",
        "win": "🎉",
        "buy": "🤑",
        "fire": "🔥",
        "bad": "😱",
        "wait": "⏳"
    }
    try:
        emoji = reactions.get(reaction_type, "✨")
        await context.bot.set_message_reaction(chat_id, message_id, [emoji])
    except Exception:
        pass

# =========================================================
# LÓGICA DE TURNOS NPC (ESTABILIZADA)
# =========================================================
async def check_npc_turn(context, game):
    """
    Controlador automático para turnos de NPC.
    Evita congelamientos mediante verificaciones de estado.
    """
    # 1. Verificación de salida: ¿Es realmente el turno de un NPC?
    if not str(game.current_player_id()).startswith("npc_"):
        return

    # 2. Verificación de bloqueo: ¿Hay procesos pendientes?
    if game.pending_vote or game.processing:
        return

    game.processing = True
    player = game.current_player()
    
    # Simulación de pensamiento del NPC
    await asyncio.sleep(1.5)
    
    # Lógica de movimiento (Dados)
    dice = random.randint(1, 6)
    old_pos = player["pos"]
    player["pos"] = safe_pos(old_pos + dice, game.max_pos)
    
    game.last_event_text = f"🤖 {player['name']} lanzó el dado y sacó {dice}."
    game.last_mood = "roll"
    
    # Verificar si el NPC ganó
    if player["pos"] >= game.max_pos:
        text = render_game(game, f"🏆 ¡EL NPC {player['name']} HA GANADO LA CARRERA! 🏆", "win")
        await context.bot.send_message(game.chat_id, text, parse_mode=ParseMode.HTML)
        if game.chat_id in games:
            del games[game.chat_id]
        return

    # Avanzar turno y actualizar UI
    game.next_turn()
    game.processing = False
    
    text = render_game(game, game.last_event_text, game.last_mood)
    await context.bot.edit_message_text(
        chat_id=game.chat_id,
        message_id=game.message_id,
        text=text,
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML
    )

    # --- REGLA DE ESTABILIDAD (CORRECCIÓN) ---
    # Solo vuelve a llamarse si la partida sigue activa y el SIGUIENTE también es NPC.
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
        await update.message.reply_text("❌ Ya hay una partida en curso.")
        return

    if chat_id not in rooms:
        rooms[chat_id] = []

    if any(p["id"] == user.id for p in rooms[chat_id]):
        await update.message.reply_text("✅ Ya estás en la sala.")
        return

    if len(rooms[chat_id]) >= MAX_PLAYERS:
        await update.message.reply_text("❌ Sala llena.")
        return

    rooms[chat_id].append({
        "id": user.id,
        "name": user.first_name,
        "emoji": random.choice(PLAYER_EMOJIS)
    })
    
    await update.message.reply_text(f"🎮 {user.first_name} se unió. ({len(rooms[chat_id])}/{MAX_PLAYERS})")

async def jugar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if chat_id in games:
        return

    players = rooms.get(chat_id, [])
    if len(players) < 1:
        await update.message.reply_text("❌ Se necesita al menos 1 jugador.")
        return

    # Autocompletar con NPCs si es necesario
    while len(players) < 2:
        npc_id = f"npc_{random.randint(1000, 9999)}"
        players.append({
            "id": npc_id,
            "name": f"Bot_{npc_id[-3:]}",
            "emoji": "🤖"
        })

    game = MisterPipaGame(chat_id, players)
    games[chat_id] = game
    
    text = render_game(game, "🏁 ¡La carrera de Mister Pipa ha comenzado! 🏁")
    msg = await update.message.reply_text(text, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
    game.message_id = msg.message_id
    
    # Limpiar sala
    if chat_id in rooms:
        del rooms[chat_id]

    # Activar bot si es su turno al inicio
    await check_npc_turn(context, game)

# =========================================================
# HANDLER DE BOTONES (CALLBACKS)
# =========================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    
    if chat_id not in games:
        await query.answer("Esta partida ya terminó.")
        return

    game = games[chat_id]
    data = query.data

    # Seguridad: solo el jugador actual puede actuar
    if game.current_player_id() != user_id:
        await query.answer("⚠️ No es tu turno.", show_alert=True)
        return

    if game.processing:
        return

    try:
        # --- LÓGICA DE DADO ---
        if data == "roll":
            game.processing = True
            player = game.current_player()
            dice = random.randint(1, 6)
            
            player["pos"] = safe_pos(player["pos"] + dice, game.max_pos)
            game.give_money(player)
            
            game.last_event_text = f"🎲 {player['name']} sacó un {dice}."
            game.last_mood = "roll"

            if player["pos"] >= game.max_pos:
                text = render_game(game, f"🏆 ¡{player['name']} HA GANADO! 🏆", "win")
                await query.edit_message_text(text, parse_mode=ParseMode.HTML)
                if chat_id in games:
                    del games[chat_id]
                return

            game.next_turn()
            text = render_game(game, game.last_event_text, game.last_mood)
            await query.edit_message_text(text, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
            await check_npc_turn(context, game)

        # --- LÓGICA DE TIENDA ---
        elif data == "shop":
            game.ui_state = "shop"
            text = render_game(game, "Bienvenido a la Pipa-Tienda 🛒", "default")
            await query.edit_message_text(text, reply_markup=shop_keyboard(game, game.current_player()), parse_mode=ParseMode.HTML)

        elif data.startswith("buy_"):
            item_id = int(data.split("_")[1])
            player = game.current_player()
            item = ITEMS.get(item_id)

            if item and player["coins"] >= item["precio"]:
                player["coins"] -= item["precio"]
                
                # Ejecutar efecto inmediato del ítem
                efecto_msg = ""
                if item["tipo"] == "move":
                    player["pos"] = safe_pos(player["pos"] + item["valor"], game.max_pos)
                    efecto_msg = f" Avanzaste {item['valor']}m."
                elif item["tipo"] == "boost":
                    player["modifier"] += item["valor"]
                    efecto_msg = f" +{item['valor']} de bono para tu próximo turno."
                elif item["tipo"] == "trap":
                    game.next_turn()
                    target = game.current_player()
                    target["pos"] = safe_pos(target["pos"] + item["valor"], game.max_pos)
                    efecto_msg = f" ¡Le lanzaste una trampa a {target['name']}!"
                    # Devolvemos el turno al comprador
                    game.current_idx = (game.current_idx - 1) % len(game.order)
                elif item["tipo"] == "random":
                    suerte = random.randint(-10, 15)
                    player["pos"] = safe_pos(player["pos"] + suerte, game.max_pos)
                    efecto_msg = " ¡Efecto aleatorio activado!"

                await query.answer(f"¡Compraste {item['name']}!")
                game.last_event_text = f"🛒 {player['name']} usó {item['name']}.{efecto_msg}"
                game.last_mood = "boost"
                game.ui_state = "main"
                await set_reaction(context, chat_id, game.message_id, "buy")
                
                # Actualizar pantalla tras compra
                text = render_game(game, game.last_event_text, game.last_mood)
                await query.edit_message_text(text, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
            else:
                await query.answer("No tienes suficientes monedas 💰", show_alert=True)

    finally:
        if chat_id in games:
            game.processing = False

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Handlers básicos
    app.add_handler(CommandHandler("unirse", unirse))
    app.add_handler(CommandHandler("jugar", jugar))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("Mister Pipa está encendido y listo...")
    app.run_polling()
