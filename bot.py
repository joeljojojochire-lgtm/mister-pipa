import os
import random
import asyncio

from telegram import Update
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

# =========================================================
# SISTEMA DE REACCIONES (Físicas de Telegram)
# =========================================================
async def set_reaction(context, chat_id, message_id, reaction_type):
    """Añade una reacción visual al mensaje del tablero"""
    reactions = {
        "roll": "🎲",
        "win": "🎉",
        "buy": "💰",
        "fire": "🔥",
        "bad": "😱",
        "wait": "⏳",
        "shock": "☢️"
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
# COMANDOS DE INICIO
# =========================================================

async def unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id not in rooms: rooms[chat_id] = []
    if any(p["id"] == user.id for p in rooms[chat_id]):
        return await update.message.reply_text("⚠️ Ya estás en la pista.")

    user_emoji = random.choice(PLAYER_EMOJIS)
    rooms[chat_id].append({"id": user.id, "name": user.first_name, "emoji": user_emoji})
    await update.message.reply_text(f"✅ **{user.first_name}** se unió con {user_emoji}")

async def jugar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in rooms or len(rooms[chat_id]) < 1:
        return await update.message.reply_text("❌ No hay corredores.")

    game = MisterPipaGame(chat_id, rooms[chat_id])
    games[chat_id] = game
    del rooms[chat_id]

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=render_game(game, "¡Mister Pipa da el pistoletazo de salida! 🚩", "default"),
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML
    )
    game.message_id = msg.message_id

# =========================================================
# LÓGICA DE BOTONES (DADOS Y COMPRA DIRECTA)
# =========================================================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    data = query.data

    if chat_id not in games: return
    game = games[chat_id]
    if game.processing: return
    game.processing = True

    try:
        if game.current_player_id() != user_id:
            return await query.answer("❌ No es tu turno.", show_alert=True)

        player = game.current_player()

        # --- TIRAR DADO ---
        if data == "roll":
            dice = random.randint(1, 6)
            # Aplicar BOOST si el jugador lo tiene activado
            if player.get("boost"):
                dice *= 2
                player["boost"] = False # Se gasta
            
            player["pos"] += dice
            player["pos"] = safe_pos(player["pos"], game.max_pos)
            
            if dice >= 5:
                txt, mood, react = f"🚀 ¡QUÉ VELOCIDAD! {player['name']} voló {dice} casillas.", "boost", "fire"
            elif dice <= 2:
                txt, mood, react = f"🐢 {player['name']} va muy lento... solo {dice} casillas.", "joke", "bad"
            else:
                txt, mood, react = f"😄 {player['name']} avanza {dice} casillas.", "roll", "roll"

            if player["pos"] >= game.max_pos:
                await query.edit_message_text(
                    text=render_game(game, f"🏆 ¡{player['name']} GANA EL SHOW! 🏆", "result"),
                    parse_mode=ParseMode.HTML
                )
                await set_reaction(context, chat_id, game.message_id, "win")
                del games[chat_id]
                return

            game.give_money(player)
            game.next_turn()
            await query.edit_message_text(
                text=render_game(game, txt, mood),
                reply_markup=main_keyboard(),
                parse_mode=ParseMode.HTML
            )
            await set_reaction(context, chat_id, game.message_id, react)

        # --- TIENDA ---
        elif data == "shop":
            await query.edit_message_text(
                text=render_game(game, "Mister Pipa abre su maletín... ¿Qué quieres comprar? 💰", "vote"),
                reply_markup=shop_keyboard(game, player),
                parse_mode=ParseMode.HTML
            )

        # --- COMPRA Y ACTIVACIÓN AUTOMÁTICA ---
        elif data.startswith("buy_"):
            item_id = int(data.split("_")[1])
            item = ITEMS[item_id]
            
            if player["coins"] >= item["precio"]:
                player["coins"] -= item["precio"]
                del game.shop[item_id]
                game.shop_cooldowns[item_id] = SHOP_RESPAWN[item_id]
                
                txt, mood, react = "", "boost", "buy"

                if item["tipo"] == "move": # Pony
                    player["pos"] = safe_pos(player["pos"] + item["valor"], game.max_pos)
                    txt = f"🐴 ¡{player['name']} compró un Pony y galopó {item['valor']}m!"
                
                elif item["tipo"] == "boost": # Turbo
                    player["boost"] = True
                    txt = f"🔥 ¡Turbo activado! @{player['name']} duplicará su próximo dado."
                    react = "fire"

                elif item["tipo"] == "trap": # Banana (Al líder)
                    leader_id = max((pid for pid in game.players if pid != user_id), key=lambda pid: game.players[pid]["pos"])
                    leader = game.players[leader_id]
                    leader["pos"] = safe_pos(leader["pos"] + item["valor"], game.max_pos)
                    txt = f"🍌 ¡ZAS! {player['name']} lanzó una Banana a {leader['name']}."
                    mood, react = "sabotage", "bad"

                elif item["tipo"] == "skip": # Dron (Al líder)
                    leader_id = max((pid for pid in game.players if pid != user_id), key=lambda pid: game.players[pid]["pos"])
                    game.players[leader_id]["skip"] += 1
                    txt = f"🚁 ¡Dron en camino! {game.players[leader_id]['name']} pierde su turno."
                    mood, react = "sabotage", "wait"

                elif item["tipo"] == "random": # Bebida
                    efecto = random.randint(-10, 15)
                    player["pos"] = safe_pos(player["pos"] + efecto, game.max_pos)
                    txt = f"☢️ {player['name']} bebió algo raro... ¡Se movió {efecto}m!"
                    mood, react = "joke", "shock"

                await query.edit_message_text(
                    text=render_game(game, txt, mood),
                    reply_markup=main_keyboard(),
                    parse_mode=ParseMode.HTML
                )
                await set_reaction(context, chat_id, game.message_id, react)

        elif data == "back":
            await query.edit_message_text(
                text=render_game(game, "De vuelta a la pista.", "default"),
                reply_markup=main_keyboard(),
                parse_mode=ParseMode.HTML
            )

    finally:
        game.processing = False

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("unirse", unirse))
    app.add_handler(CommandHandler("jugar", jugar))
    app.add_handler(CallbackQueryHandler(buttons))
    app.run_polling()
