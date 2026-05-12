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
# SISTEMA DE REACCIONES (Corregido para v20+)
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
        "shock": "☢️",
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
# --- Relleno de NPCs ---
    jugadores = rooms[chat_id]
    if len(jugadores) == 1:
        jugadores.append({"id": 101, "name": "Primo de Mister Pipa", "emoji": "🤡", "is_npc": True})
    
    if len(jugadores) % 2 == 0:
        jugadores.append({"id": 102, "name": "Mister Pipa Senior", "emoji": "👴", "is_npc": True})
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
# LÓGICA DE BOTONES (DADOS, COMPRA Y VOTACIÓN)
# =========================================================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    data = query.data

    if chat_id not in games: return
    game = games[chat_id]
    
    # --- SISTEMA DE VOTOS (Acción Pública) ---
    if data.startswith("vote_"):
        if not game.pending_vote:
            return await query.answer("La votación ya terminó.")
        
        # Registrar voto si el usuario no ha votado aún
        if user_id not in game.pending_vote["votos"]:
            target_id = int(data.split("_")[1])
            game.pending_vote["votos"][user_id] = target_id
            
            # Si todos votaron o se alcanza el quórum
            if len(game.pending_vote["votos"]) >= len(game.players):
                votos_lista = list(game.pending_vote["votos"].values())
                victima_id = max(set(votos_lista), key=votos_lista.count)
                victima = game.players[victima_id]
                
                # Efecto: La víctima retrocede mucho, los demás avanzan un poco
                victima["pos"] = safe_pos(victima["pos"] - 15, game.max_pos)
                for pid, p in game.players.items():
                    if pid != victima_id:
                        p["pos"] = safe_pos(p["pos"] + 5, game.max_pos)
                
                txt = f"🗳 **¡VOTACIÓN CERRADA!**\n\n{victima['name']} ha sido sacrificado a la Liebre Salvaje. Retrocede 15m mientras los demás escapan aprovechando el caos."
                game.pending_vote = None
                game.processing = False # Desbloquear juego
                
                await query.edit_message_text(
                    text=render_game(game, txt, "joke"),
                    reply_markup=main_keyboard(),
                    parse_mode=ParseMode.HTML
                )
                await set_reaction(context, chat_id, game.message_id, "bad")
            else:
                await query.answer(f"Voto registrado por {query.from_user.first_name}")
        else:
            await query.answer("Ya has votado.", show_alert=True)
        return

    # Bloqueo de procesamiento para evitar doble clic en dados/tienda
    if game.processing: return
    game.processing = True

    try:
        if game.current_player_id() != user_id:
            game.processing = False
            return await query.answer("❌ No es tu turno.", show_alert=True)

        player = game.current_player()

        # --- TIRAR DADO ---
        if data == "roll":
            # PROBABILIDAD DE VOTACIÓN ALEATORIA (15% de probabilidad)
            if random.random() < 0.15 and len(game.players) > 1:
                game.pending_vote = {"votos": {}}
                
                botones_voto = []
                for pid, p in game.players.items():
                    botones_voto.append([InlineKeyboardButton(f"🍴 Sacrificar a {p['name']}", callback_data=f"vote_{pid}")])
                
                await query.edit_message_text(
                    text=render_game(game, VOTACIONES["liebre"]["pregunta"], "vote"),
                    reply_markup=InlineKeyboardMarkup(botones_voto),
                    parse_mode=ParseMode.HTML
                )
                await set_reaction(context, chat_id, game.message_id, "vote")
                # No liberamos 'processing' hasta que termine la votación para pausar el juego
                return

            dice = random.randint(1, 6)
            if player.get("boost"):
                dice *= 2
                player["boost"] = False 
            
            player["pos"] = safe_pos(player["pos"] + dice, game.max_pos)
            
            if dice >= 5:
                frases = [
                    f"🚀 ¡QUÉ VELOCIDAD! {player['name']} puso un cohete.",
                    f"🔥 {player['name']} corre como si el suelo quemara.",
                    f"⚡ ¡IMPRESIONANTE! {player['name']} vuela por la pista."
                ]
                txt, mood, react = random.choice(frases), "boost", "fire"
            elif dice <= 2:
                frases = [
                    f"🐢 {player['name']} va tan lento que parece una estatua.",
                    f"😴 Mister Pipa bosteza... {player['name']} apenas se movió.",
                    f"🐌 ¿Eso es todo, {player['name']}? ¡Muévete!"
                ]
                txt, mood, react = random.choice(frases), "joke", "bad"
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
                text=render_game(game, "Mister Pipa abre su maletín de ofertas... 💰", "vote"),
                reply_markup=shop_keyboard(game, player),
                parse_mode=ParseMode.HTML
            )

        # --- COMPRA Y ACTIVACIÓN ---
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
                    txt = f"🐴 ¡Arre! {player['name']} compró un Pony y galopó {item['valor']}m."
                
                elif item["tipo"] == "boost": # Turbo
                    player["boost"] = True
                    txt = f"🔥 ¡Turbo activado! {player['name']} duplicará su próximo dado."
                    react = "fire"

                elif item["tipo"] == "trap": # Banana
                    opponents = [pid for pid in game.players if pid != user_id]
                    leader_id = max(opponents, key=lambda pid: game.players[pid]["pos"])
                    leader = game.players[leader_id]
                    leader["pos"] = safe_pos(leader["pos"] + item["valor"], game.max_pos)
                    txt = f"🍌 ¡ZAS! {player['name']} lanzó una Banana a {leader['name']}."
                    mood, react = "sabotage", "bad"

                elif item["tipo"] == "skip": # Dron
                    opponents = [pid for pid in game.players if pid != user_id]
                    leader_id = max(opponents, key=lambda pid: game.players[pid]["pos"])
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
        # Solo liberamos el procesamiento si no hay una votación pausando el juego
        if not game.pending_vote:
            game.processing = False

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("unirse", unirse))
    app.add_handler(CommandHandler("jugar", jugar))
    app.add_handler(CallbackQueryHandler(buttons))
    app.run_polling()
async def check_npc_turn(context, game):
    """Maneja el turno automático de los parientes de Mister Pipa"""
    player = game.current_player()
    if not player.get("is_npc"): return

    await asyncio.sleep(2) # Pausa dramática para 'pensar'
    dice = random.randint(1, 6)
    player["pos"] = safe_pos(player["pos"] + dice, game.max_pos)
    
    txt = f"🤖 **{player['name']}** (NPC) lanzó el dado: ¡sacó un {dice}!"
    
    if player["pos"] >= game.max_pos:
        await context.bot.edit_message_text(
            chat_id=game.chat_id, message_id=game.message_id,
            text=render_game(game, f"🏆 ¡EL NPC {player['name']} HA GANADO! 🏆", "result"),
            parse_mode=ParseMode.HTML
        )
        if game.chat_id in games: del games[game.chat_id]
        return

    game.give_money(player)
    game.next_turn()
    await context.bot.edit_message_text(
        chat_id=game.chat_id, message_id=game.message_id,
        text=render_game(game, txt, "roll"),
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML
    )
    # Si el que sigue también es NPC, vuelve a ejecutarse solo
    await check_npc_turn(context, game)
