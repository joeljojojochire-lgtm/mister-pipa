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

# CAMBIO QUIRÚRGICO: Se añadió vote_keyboard y se limpiaron duplicados
from game import MisterPipaGame
from ui import render_game, main_keyboard, vote_keyboard
from items import ITEMS
from utils import safe_pos
from config import MAX_PLAYERS, PLAYER_EMOJIS

TOKEN = os.getenv("TELEGRAM_TOKEN")

games = {}
rooms = {}

# =========================================================
# REACCIONES (Versión Corregida)
# =========================================================

async def set_reaction(context, chat_id, message_id, reaction_type):
    reactions = {
        "roll": "🎲",
        "win": "🎉",
        "boost": "⚡",
        "fire": "🔥",
        "bad": "😱",
        "sabotage": "💢",
        "vote": "🗳️"
    }

    try:
        emoji = reactions.get(reaction_type, "✨")
        from telegram import ReactionTypeEmoji
        
        await context.bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji)]
        )
    except Exception as e:
        print(f"REACTION LOG: {e}")

# =========================================================
# EVENTOS
# =========================================================

async def apply_random_event(game, player):
    # 1. Probabilidad de que Mister Pipa use un objeto (25%)
    if random.random() < 0.25:
        item = ITEMS[random.randint(1, 5)]
        resultado = random.choice(["CARA", "CRUZ"])
        pasa_algo = (resultado == "CARA")
        
        msg_moneda = f"\n🪙 **Mister Pipa lanza una moneda... ¡{resultado}!**"
        
        if item["tipo"] in ["trap", "move", "boost"]:
            if random.random() > 0.5:
                target_id = random.choice(game.order)
                target = game.players[target_id]
            else:
                target = player

            if pasa_algo:
                target["pos"] = safe_pos(target["pos"] + item.get("valor", 5), game.max_pos)
                return f"{msg_moneda}\n¿Usar {item['name']} en {target['name']}? ¿Y por qué no? ({item.get('valor')}m)", "sabotage"
            else:
                return f"{msg_moneda}\n¿Usar {item['name']}? Pipa se lo pensó mejor. 'Hoy no'.", "joke"
    
    # 2. ACTIVACIÓN DE VOTACIÓN (15%) - Corrección vital
    if random.random() < 0.15:
        target_id = random.choice(game.order)
        game.pending_vote = {
            "target": target_id,
            "votes": {}
        }
        
        for pid, pdata in game.players.items():
            if pdata.get("is_npc"):
                game.pending_vote["votes"][pid] = random.choice([True, False])
        
        target_name = game.players[target_id]['name']
        return f"\n🗳️ **¡Mister Pipa abre una votación!**\n¿Hacemos que {target_name} retroceda 10m?", "vote"
    
    return "", "default"

async def check_npc_turn(context, game):
    if game.chat_id not in games or game.processing:
        return

    # Si hay votación, el NPC vota y espera (No tira dado todavía)
    if game.pending_vote:
        npc_id = game.current_player_id()
        if str(npc_id).startswith("npc_") and npc_id not in game.pending_vote["votes"]:
            game.pending_vote["votes"][npc_id] = random.choice([True, False])
        return 

    if not str(game.current_player_id()).startswith("npc_"):
        return

    game.processing = True
    try:
        player = game.current_player()
        await asyncio.sleep(1.5)

        dice = random.randint(1, 6)
        total_move = dice + player.get("modifier", 0)
        player["modifier"] = 0
        player["pos"] = safe_pos(player["pos"] + total_move, game.max_pos)

        event_msg = f"🤖 {player['name']} lanzó el dado y avanzó {total_move}m."
        mood = "roll"

        extra_msg, extra_mood = await apply_random_event(game, player)
        if extra_msg:
            event_msg += extra_msg
            mood = extra_mood

        if player["pos"] >= game.max_pos:
            text = render_game(game, f"🏆 ¡{player['name']} HA GANADO! 🏆", "win")
            await context.bot.edit_message_text(chat_id=game.chat_id, message_id=game.message_id, text=text, parse_mode=ParseMode.HTML)
            if game.chat_id in games: del games[chat_id]
            return

        game.next_turn()
        text = render_game(game, event_msg, mood)
        
        markup = vote_keyboard() if game.pending_vote else main_keyboard()

        await context.bot.edit_message_text(
            chat_id=game.chat_id,
            message_id=game.message_id,
            text=text,
            reply_markup=markup,
            parse_mode=ParseMode.HTML
        )
        await set_reaction(context, game.chat_id, game.message_id, mood)

    except Exception as e:
        print("NPC ERROR:", e)
    finally:
        game.processing = False

    await asyncio.sleep(2)
    if game.chat_id in games and str(game.current_player_id()).startswith("npc_"):
        await check_npc_turn(context, game)

# =========================================================
# UNIRSE / JUGAR
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

    rooms[chat_id].append({
        "id": user.id,
        "name": user.first_name,
        "emoji": random.choice(PLAYER_EMOJIS)
    })
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
        players.append({
            "id": npc_id,
            "name": f"Bot_{npc_id[-3:]}",
            "emoji": "🤖"
        })

    game = MisterPipaGame(chat_id, players)
    games[chat_id] = game
    text = render_game(game, "🏁 ¡La carrera ha comenzado! 🏁")
    msg = await update.message.reply_text(text, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
    game.message_id = msg.message_id

    if chat_id in rooms: del rooms[chat_id]
    await check_npc_turn(context, game)

# =========================================================
# BOTONES
# =========================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user_id = query.from_user.id

    if chat_id not in games: return
    game = games[chat_id]

    # --- VOTACIONES ---
    if query.data in ["vote_yes", "vote_no"]:
        if game.pending_vote:
            game.pending_vote["votes"][user_id] = (query.data == "vote_yes")
            
            if len(game.pending_vote["votes"]) >= len(game.order):
                v_si = sum(1 for v in game.pending_vote["votes"].values() if v)
                v_no = sum(1 for v in game.pending_vote["votes"].values() if not v)
                
                if v_si == v_no:
                    resultado_final, pipa_msg = game.resolve_vote_pipa()
                else:
                    resultado_final = v_si > v_no
                    pipa_msg = "¡La mayoría ha decidido!"

                if resultado_final:
                    target = game.players[game.pending_vote["target"]]
                    target["pos"] = safe_pos(target["pos"] - 10, game.max_pos)

                game.pending_vote = None
                res_txt = "✅ SÍ" if resultado_final else "❌ NO"
                
                # CORRECCIÓN AQUÍ: Usamos render_game para no perder el tablero
                texto_con_tablero = render_game(
                    game, 
                    f"📊 Votación finalizada: {res_txt}\n{pipa_msg}", 
                    "result"
                )
                
                await query.edit_message_text(
                    texto_con_tablero, 
                    reply_markup=main_keyboard(), # Restauramos el botón de dado
                    parse_mode=ParseMode.HTML
                )
                
                await asyncio.sleep(2)
                await check_npc_turn(context, game)
        return

    # --- DADO ---
    if game.processing: return
    if game.current_player_id() != user_id:
        await query.answer("⚠️ No es tu turno.", show_alert=True)
        return
    if query.data != "roll": return

    game.processing = True
    try:
        player = game.current_player()
        dice = random.randint(1, 6)
        total_move = dice + player.get("modifier", 0)
        player["modifier"] = 0
        player["pos"] = safe_pos(player["pos"] + total_move, game.max_pos)

        event_msg = f"🎲 {player['name']} lanzó el dado y avanzó {total_move}m."
        mood = "roll"

        extra_msg, extra_mood = await apply_random_event(game, player)
        if extra_msg:
            event_msg += extra_msg
            mood = extra_mood

        if player["pos"] >= game.max_pos:
            text = render_game(game, f"🏆 ¡{player['name']} HA GANADO! 🏆", "win")
            await query.edit_message_text(text, parse_mode=ParseMode.HTML)
            if chat_id in games: del games[chat_id]
            return

        game.next_turn()
        text = render_game(game, event_msg, mood)
        markup = vote_keyboard() if game.pending_vote else main_keyboard()

        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        await set_reaction(context, chat_id, game.message_id, mood)

    except Exception as e:
        print("BUTTON ERROR:", e)
    finally:
        game.processing = False

    await asyncio.sleep(2)
    await check_npc_turn(context, game)

# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("unirse", unirse))
    app.add_handler(CommandHandler("jugar", jugar))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Mister Pipa Estabilizado Online...")
    app.run_polling()
