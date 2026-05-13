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
# MOTOR VISUAL (2 REFRESCOS POR SEGUNDO)
# =========================================================
async def game_loop(context, chat_id):
    """Bucle de renderizado independiente para animaciones fluidas"""
    while chat_id in games:
        game = games[chat_id]
        
        # Si hay votación, el bucle NO sobreescribe para no borrar el menú de votos
        if not game.pending_vote:
            try:
                # Extraemos el estado actual almacenado en el objeto game
                txt = getattr(game, 'last_event_text', "El show continúa...")
                mood = getattr(game, 'last_mood', "default")
                
                # Determinamos qué teclado mostrar según el estado de la UI
                if getattr(game, 'ui_state', 'main') == 'shop':
                    keyboard = shop_keyboard(game, game.current_player())
                else:
                    keyboard = main_keyboard()

                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=game.message_id,
                    text=render_game(game, txt, mood),
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass # Ignorar errores de Flood Control si ocurren puntualmente

        # 0.5 segundos = 2 frames por segundo
        await asyncio.sleep(0.5)

# =========================================================
# LÓGICA DE NPCs (Cerebro Automático Actualizado)
# =========================================================
async def check_npc_turn(context, game):
    """Maneja el turno automático de los parientes de Mister Pipa con Compras"""
    if game.chat_id not in games:
        return

    player = game.current_player()
    if not player.get("is_npc"):
        return

    await asyncio.sleep(2) # Pausa para simular que el bot piensa
    
    # --- IA: DECISIÓN DE COMPRA ALEATORIA ---
    npc_buy_msg = ""
    if player["coins"] >= 35 and random.random() < 0.20:
        available = [i_id for i_id, it in game.shop.items() if it["precio"] <= player["coins"]]
        if available:
            item_id = random.choice(available)
            item = game.shop.pop(item_id)
            game.shop_cooldowns[item_id] = SHOP_RESPAWN.get(item_id, 3)
            player["coins"] -= item["precio"]
            
            if item["tipo"] == "move":
                player["pos"] = safe_pos(player["pos"] + item["valor"], game.max_pos)
            elif item["tipo"] == "boost":
                player["modifier"] = item["valor"]
            elif item["tipo"] == "trap":
                target_id = random.choice(game.order)
                game.players[target_id]["pos"] = safe_pos(game.players[target_id]["pos"] - 5, game.max_pos)
            
            npc_buy_msg = f"🛒 **{player['name']}** compró un {item['name']}. "
            await set_reaction(context, game.chat_id, game.message_id, "buy")
            await asyncio.sleep(1)

    dice = random.randint(1, 6)
    bono = player.get("modifier", 0)
    total_move = dice + bono
    player["modifier"] = 0
    
    player["pos"] = safe_pos(player["pos"] + total_move, game.max_pos)
    
    # IMPORTANTE: No editamos el mensaje aquí, solo actualizamos los datos para el loop
    game.last_event_text = f"{npc_buy_msg}🤖 **{player['name']}** lanzó el dado y sacó un {dice}."
    game.last_mood = "roll"
    
    if player["pos"] >= game.max_pos:
        game.last_event_text = f"🏆 ¡EL NPC {player['name']} HA GANADO EL SHOW! 🏆"
        game.last_mood = "result"
        await set_reaction(context, game.chat_id, game.message_id, "win")
        await asyncio.sleep(2)
        if game.chat_id in games: del games[game.chat_id]
        return

    game.give_money(player)
    game.next_turn()
    
    await set_reaction(context, game.chat_id, game.message_id, "roll")
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

    jugadores = rooms[chat_id]
    if len(jugadores) == 1:
        jugadores.append({"id": 101, "name": "Primo de Mister Pipa", "emoji": "🤡", "is_npc": True})
    
    if len(jugadores) % 2 == 0:
        jugadores.append({"id": 102, "name": "Mister Pipa Senior", "emoji": "👴", "is_npc": True})

    game = MisterPipaGame(chat_id, jugadores)
    game.last_event_text = "¡Mister Pipa da el pistoletazo de salida! 🚩"
    game.last_mood = "default"
    game.ui_state = "main"
    games[chat_id] = game
    del rooms[chat_id]

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=render_game(game, game.last_event_text, game.last_mood),
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML
    )
    game.message_id = msg.message_id
    
    # LANZAMOS EL MOTOR VISUAL
    asyncio.create_task(game_loop(context, chat_id))
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
    
    if data.startswith("vote_"):
        if not game.pending_vote: return await query.answer("La votación terminó.")
        if user_id not in game.pending_vote["votos"]:
            target_id = int(data.split("_")[1])
            game.pending_vote["votos"][user_id] = target_id
            
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
                
                game.last_event_text = f"🗳 **¡VOTACIÓN CERRADA!**\n\n{victima['name']} fue sacrificado."
                game.last_mood = "joke"
                game.pending_vote = None
                game.processing = False
                
                await set_reaction(context, chat_id, game.message_id, "bad")
                await check_npc_turn(context, game)
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
                # La votación se edita manualmente para detener el loop visual temporalmente
                await query.edit_message_text(
                    text=render_game(game, VOTACIONES["liebre"]["pregunta"], "vote"),
                    reply_markup=InlineKeyboardMarkup(botones),
                    parse_mode=ParseMode.HTML
                )
                await set_reaction(context, chat_id, game.message_id, "vote")
                return

            dice = random.randint(1, 6)
            bono = player.get("modifier", 0)
            total_move = dice + bono
            player["modifier"] = 0 
            
            if player.get("boost"):
                total_move *= 2
                player["boost"] = False 
            
            player["pos"] = safe_pos(player["pos"] + total_move, game.max_pos)
            msg_dice = f"sacó un {dice}" + (f" (+{bono} extra)" if bono > 0 else "")
            
            if total_move >= 5: 
                game.last_event_text, game.last_mood, react = f"🚀 ¡QUÉ VELOCIDAD! {player['name']} {msg_dice}.", "boost", "fire"
            elif total_move <= 2: 
                game.last_event_text, game.last_mood, react = f"🐢 {player['name']} {msg_dice}... va lento.", "joke", "bad"
            else: 
                game.last_event_text, game.last_mood, react = f"😄 {player['name']} avanza con un {total_move}.", "roll", "roll"

            if player["pos"] >= game.max_pos:
                game.last_event_text = f"🏆 ¡{player['name']} GANA EL SHOW! 🏆"
                game.last_mood = "result"
                await set_reaction(context, chat_id, game.message_id, "win")
                await asyncio.sleep(2)
                if chat_id in games: del games[chat_id]
                return

            game.give_money(player)
            game.next_turn()
            await set_reaction(context, chat_id, game.message_id, react)
            await check_npc_turn(context, game)

        elif data == "shop":
            game.ui_state = "shop"
            game.last_event_text = "Mister Pipa abre su maletín... 💰"
            game.last_mood = "vote"

        elif data == "back":
            game.ui_state = "main"
            game.last_event_text = "De vuelta a la pista."
            game.last_mood = "default"

        elif data.startswith("buy_"):
            item_id = int(data.split("_")[1])
            item = ITEMS.get(item_id)

            if player["coins"] >= item["precio"]:
                player["coins"] -= item["precio"]
                if item_id in game.shop:
                    del game.shop[item_id]
                    game.shop_cooldowns[item_id] = SHOP_RESPAWN.get(item_id, 3)

                efecto_msg = ""
                if item["tipo"] == "move":
                    player["pos"] = safe_pos(player["pos"] + item["valor"], game.max_pos)
                    efecto_msg = f" ¡Avanzaste {item['valor']} casillas!"
                elif item["tipo"] == "boost":
                    player["modifier"] = item["valor"]
                    efecto_msg = f" +{item['valor']} de bono para tu próximo turno."
                elif item["tipo"] == "trap":
                    game.next_turn()
                    target = game.current_player()
                    target["pos"] = safe_pos(target["pos"] + item["valor"], game.max_pos)
                    efecto_msg = f" ¡Le lanzaste una trampa a {target['name']}!"
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
            else:
                await query.answer("No tienes suficientes monedas 💰", show_alert=True)

    finally:
        if not game.pending_vote and chat_id in games:
            game.processing = False

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("unirse", unirse))
    app.add_handler(CommandHandler("jugar", jugar))
    app.add_handler(CallbackQueryHandler(buttons))
    app.run_polling()
