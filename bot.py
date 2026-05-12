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
# SISTEMA DE REACCIONES (Animaciones de Pantalla Completa)
# =========================================================
async def set_reaction(context, chat_id, message_id, reaction_type):
    """Añade una reacción visual al mensaje del tablero"""
    reactions = {
        "roll": "🎲",
        "win": "🎉",      # Fuegos artificiales
        "buy": "🤑",      # Lluvia de dinero
        "fire": "🔥",     # Animación de fuego
        "bad": "😱",      # Animación de susto
        "wait": "⏳",
        "shock": "⚡",     # Rayo
        "vote": "🗳️"
    }
    emoji = reactions.get(reaction_type, "👍")
    try:
        await context.bot.set_message_reaction(
            chat_id=chat_id, 
            message_id=message_id, 
            reaction=[{"type": "emoji", "emoji": emoji}]
        )
    except:
        pass

# =========================================================
# LÓGICA DE NPCs (Cerebro Automático)
# =========================================================
async def check_npc_turn(context, game):
    """Maneja el turno automático de los parientes de Mister Pipa"""
    player = game.current_player()
    
    # Si no es NPC o el juego terminó, salimos
    if not player.get("is_npc") or game.chat_id not in games:
        return

    await asyncio.sleep(2) # Pausa para simular que el bot piensa
    
    dice = random.randint(1, 6)
    player["pos"] = safe_pos(player["pos"] + dice, game.max_pos)
    
    txt = f"🤖 **{player['name']}** lanzó el dado y sacó un {dice}."
    
    if player["pos"] >= game.max_pos:
        await context.bot.edit_message_text(
            chat_id=game.chat_id, 
            message_id=game.message_id,
            text=render_game(game, f"🏆 ¡EL NPC {player['name']} HA GANADO EL SHOW! 🏆", "result"),
            parse_mode=ParseMode.HTML
        )
        await set_reaction(context, game.chat_id, game.message_id, "win")
        if game.chat_id in games: del games[game.chat_id]
        return

    game.give_money(player)
    game.next_turn()
    
    await context.bot.edit_message_text(
        chat_id=game.chat_id,
        message_id=game.message_id,
        text=render_game(game, txt, "roll"),
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await set_reaction(context, game.chat_id, game.message_id, "roll")

    # Re-chequear por si el siguiente turno también es de un NPC
    await check_npc_turn(context, game)

# =========================================================
# COMANDOS DE INICIO
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

    # --- Relleno de NPCs para asegurar número impar y mínimo 2 ---
    jugadores = rooms[chat_id]
    if len(jugadores) == 1:
        jugadores.append({"id": 101, "name": "Primo de Mister Pipa", "emoji": "🤡", "is_npc": True})
    
    if len(jugadores) % 2 == 0:
        jugadores.append({"id": 102, "name": "Mister Pipa Senior", "emoji": "👴", "is_npc": True})

    game = MisterPipaGame(chat_id, jugadores)
    games[chat_id] = game
    del rooms[chat_id]

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=render_game(game, "¡Mister Pipa da el pistoletazo de salida! 🚩", "default"),
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML
    )
    game.message_id = msg.message_id
    
    # Si el primer jugador es un NPC, que empiece a mover
    await check_npc_turn(context, game)

# =========================================================
# LÓGICA DE BOTONES
# =========================================================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    data = query.data

    if chat_id not in games: return
    game = games[chat_id]
    
    # --- SISTEMA DE VOTOS ---
    if data.startswith("vote_"):
        if not game.pending_vote: return await query.answer("La votación terminó.")
        if user_id not in game.pending_vote["votos"]:
            target_id = int(data.split("_")[1])
            game.pending_vote["votos"][user_id] = target_id
            
            # Los NPCs votan automáticamente al azar cuando hay una votación activa
            for pid, p in game.players.items():
                if p.get("is_npc") and pid not in game.pending_vote["votos"]:
                    game.pending_vote["votos"][pid] = random.choice(list(game.players.keys()))

            if len(game.pending_vote["votos"]) >= len(game.players):
                votos_lista = list(game.pending_vote["votos"].values())
                victima_id = max(set(votos_lista), key=votos_lista.count)
                victima = game.players[victima_id]
                
                victima["pos"] = safe_pos(victima["pos"] - 15, game.max_pos)
                for pid, p in game.players.items():
                    if pid != victima_id: p["pos"] = safe_pos(p["pos"] + 5, game.max_pos)
                
                txt = f"🗳 **¡VOTACIÓN CERRADA!**\n\n{victima['name']} fue sacrificado. Los NPCs también votaron."
                game.pending_vote = None
                game.processing = False
                
                await query.edit_message_text(
                    text=render_game(game, txt, "joke"),
                    reply_markup=main_keyboard(),
                    parse_mode=ParseMode.HTML
                )
                await set_reaction(context, chat_id, game.message_id, "bad")
                await check_npc_turn(context, game) # Ver si sigue un NPC
        return

    if game.processing: return
    game.processing = True

    try:
        if game.current_player_id() != user_id:
            game.processing = False
            return await query.answer("❌ No es tu turno.", show_alert=True)

        player = game.current_player()

        if data == "roll":
            if random.random() < 0.15 and len(game.players) > 1:
                game.pending_vote = {"votos": {}}
                botones = [[InlineKeyboardButton(f"🍴 Sacrificar a {p['name']}", callback_data=f"vote_{pid}")] for pid, p in game.players.items()]
                await query.edit_message_text(
                    text=render_game(game, VOTACIONES["liebre"]["pregunta"], "vote"),
                    reply_markup=InlineKeyboardMarkup(botones),
                    parse_mode=ParseMode.HTML
                )
                await set_reaction(context, chat_id, game.message_id, "vote")
                return

            dice = random.randint(1, 6)
            if player.get("boost"):
                dice *= 2
                player["boost"] = False 
            
            player["pos"] = safe_pos(player["pos"] + dice, game.max_pos)
            
            if dice >= 5: txt, mood, react = f"🚀 ¡QUÉ VELOCIDAD! {player['name']} voló.", "boost", "fire"
            elif dice <= 2: txt, mood, react = f"🐢 {player['name']} va muy lento...", "joke", "bad"
            else: txt, mood, react = f"😄 {player['name']} avanza {dice} casillas.", "roll", "roll"

            if player["pos"] >= game.max_pos:
                await query.edit_message_text(
                    text=render_game(game, f"🏆 ¡{player['name']} GANA EL SHOW! 🏆", "result"),
                    parse_mode=ParseMode.HTML
                )
                await set_reaction(context, chat_id, game.message_id, "win")
                if chat_id in games: del games[chat_id]
                return

            game.give_money(player)
            game.next_turn()
            await query.edit_message_text(
                text=render_game(game, txt, mood),
                reply_markup=main_keyboard(),
                parse_mode=ParseMode.HTML
            )
            await set_reaction(context, chat_id, game.message_id, react)
            
            # DESPUÉS DEL TURNO HUMANO: Ver si le toca al NPC
            await check_npc_turn(context, game)

        elif data == "shop":
            await query.edit_message_text(
                text=render_game(game, "Mister Pipa abre su maletín... 💰", "vote"),
                reply_markup=shop_keyboard(game, player),
                parse_mode=ParseMode.HTML
            )

        elif data.startswith("buy_"):
        item_id = data.split("_")[1]
        item = ITEMS.get(item_id)
        player = game.players[query.from_user.id]

        if player["coins"] >= item["costo"]:
            player["coins"] -= item["costo"]
            
            # --- Lógica reparada respetando tus mecánicas ---
            efecto_msg = ""
            if item["tipo"] == "movimiento":
                # Para el Pony o similares
                player["pos"] = min(player["pos"] + item["valor"], game.max_pos)
                efecto_msg = f"\n\n✨ ¡Avanzaste a la casilla {player['pos']}!"
            
            elif item["tipo"] == "dado_extra":
                # Para el Dron o Turbo
                player["modifier"] = item["valor"]
                efecto_msg = f"\n\n🚀 +{item['valor']} de bono para tu próximo turno."
                
            elif item["tipo"] == "proteccion":
                # Para el Caparazón
                player["protected"] = True
                efecto_msg = f"\n\n🛡️ ¡Estás protegido contra el próximo evento negativo!"

            await query.answer(f"¡Compraste {item['nombre']}!")
            await query.edit_message_text(
                f"🛒 *Tienda*: Has adquirido **{item['nombre']}**.{efecto_msg}\n\n{game.get_status()}",
                reply_markup=get_game_keyboard(game, query.from_user.id),
                parse_mode="Markdown"
            )
        else:
            await query.answer("No tienes suficientes monedas 💰", show_alert=True)
                # (Aquí iría el resto de tu lógica de items: Pony, Dron, etc.)
                # ...
                
                await query.edit_message_text(
                    text=render_game(game, txt, "boost"),
                    reply_markup=main_keyboard(),
                    parse_mode=ParseMode.HTML
                )
                await set_reaction(context, chat_id, game.message_id, "buy")

        elif data == "back":
            await query.edit_message_text(
                text=render_game(game, "De vuelta a la pista.", "default"),
                reply_markup=main_keyboard(),
                parse_mode=ParseMode.HTML
            )

    finally:
        if not game.pending_vote and chat_id in games:
            game.processing = False

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("unirse", unirse))
    app.add_handler(CommandHandler("jugar", jugar))
    app.add_handler(CallbackQueryHandler(buttons))
    app.run_polling()
