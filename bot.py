import os
import random
import asyncio

from telegram import Update
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from game import MisterPipaGame
from ui import render_game
from ui import main_keyboard
from ui import shop_keyboard
from ui import inventory_keyboard

from items import ITEMS
from items import SHOP_RESPAWN

from events import SPECIAL_CELLS
from events import FREE_ITEM_CELLS

from utils import safe_pos
from utils import safe_edit

from config import MAX_PLAYERS
from config import MAX_RONDAS
from config import VOTE_TIMEOUT

TOKEN = os.getenv("TELEGRAM_TOKEN")

games = {}
rooms = {}


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(

        "🏝️ MISTER PIPA SHOW\n\n"
        "/crear\n"
        "/unirse\n"
        "/jugar"

    )


# =========================================================
# CREATE
# =========================================================

async def crear(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat_id = update.effective_chat.id

    rooms[chat_id] = []

    await update.message.reply_text(
        "✅ Sala creada"
    )


# =========================================================
# JOIN
# =========================================================

async def unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat_id = update.effective_chat.id

    if chat_id not in rooms:

        await update.message.reply_text(
            "⚠️ Usa /crear"
        )

        return

    user = update.effective_user

    room = rooms[chat_id]

    if any(p["id"] == user.id for p in room):
        return

    if len(room) >= MAX_PLAYERS:

        await update.message.reply_text(
            "⚠️ Sala llena"
        )

        return

    room.append({

        "id": user.id,
        "name": user.username or user.first_name

    })

    await update.message.reply_text(

        f"✅ @{user.username or user.first_name} entró\n"
        f"👥 {len(room)}/{MAX_PLAYERS}"

    )


# =========================================================
# PLAY
# =========================================================

async def jugar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat_id = update.effective_chat.id

    if chat_id in games:

        await update.message.reply_text(
            "⚠️ Ya hay partida"
        )

        return

    if chat_id not in rooms or len(rooms[chat_id]) < 2:

        await update.message.reply_text(
            "⚠️ Mínimo 2 jugadores"
        )

        return

    game = MisterPipaGame(
        chat_id,
        rooms[chat_id]
    )

    games[chat_id] = game

    msg = await update.message.reply_text(

        render_game(game, "🔥 EL SHOW COMIENZA"),

        reply_markup=main_keyboard()

    )

    game.message_id = msg.message_id


# =========================================================
# BUTTONS
# =========================================================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    chat_id = query.message.chat.id
    user_id = query.from_user.id

    if chat_id not in games:
        return

    game = games[chat_id]

    if game.processing:
        return

    game.processing = True

    try:

        data = query.data

        if (
            user_id != game.current_player_id()
            and not data.startswith("vote_")
        ):
            return

        # =================================================
        # ROLL
        # =================================================

        if data == "roll":

            player = game.current_player()

            if player["skip"] > 0:

                player["skip"] -= 1

                txt = (
                    f"💫 @{player['name']} pierde turno"
                )

                game.next_turn()

                await safe_edit(
                    query,
                    render_game(game, txt),
                    main_keyboard()
                )

                return

            dice = random.randint(1, 6)

            if player["boost"]:

                dice *= 2
                player["boost"] = False

            player["pos"] += dice

            txt = (
                f"🎲 @{player['name']} sacó {dice}"
            )

            money_txt = game.give_money(player)

            if money_txt:
                txt += f"\n{money_txt}"

            if player["pos"] in SPECIAL_CELLS:

                msg, new_pos = SPECIAL_CELLS[player["pos"]]

                player["pos"] = new_pos

                txt += f"\n⚠️ {msg}"

            if player["pos"] in FREE_ITEM_CELLS:

                item_id = random.choice(list(ITEMS.keys()))

                player["items"].append(item_id)

                txt += (
                    f"\n🎁 Encontró "
                    f"{ITEMS[item_id]['name']}"
                )

            player["pos"] = safe_pos(
                player["pos"],
                game.max_pos
            )

            if player["pos"] >= game.max_pos:

                await safe_edit(
                    query,
                    f"🏆 @{player['name']} ganó el show"
                )

                del games[chat_id]

                return

            if random.random() < 0.08:

                loser = min(
                    game.players.items(),
                    key=lambda x: x[1]["pos"]
                )

                loser[1]["pos"] += 10

                txt += (
                    f"\n🎁 El público ayuda a "
                    f"@{loser[1]['name']}"
                )

            game.next_turn()

            await safe_edit(
                query,
                render_game(game, txt),
                main_keyboard()
            )

        # =================================================
        # SHOP
        # =================================================

        elif data == "shop":

            await safe_edit(
                query,
                "🛒 TIENDA",
                shop_keyboard(
                    game,
                    game.current_player()
                )
            )

        # =================================================
        # INVENTORY
        # =================================================

        elif data == "inventory":

            await safe_edit(
                query,
                "🎒 INVENTARIO",
                inventory_keyboard(
                    game.current_player()
                )
            )

        # =================================================
        # BUY
        # =================================================

        elif data.startswith("buy_"):

            item_id = int(
                data.replace("buy_", "")
            )

            player = game.current_player()

            if item_id not in game.shop:
                return

            item = ITEMS[item_id]

            if player["coins"] < item["precio"]:
                return

            player["coins"] -= item["precio"]

            player["items"].append(item_id)

            del game.shop[item_id]

            game.shop_cooldowns[item_id] = \
                SHOP_RESPAWN[item_id]

            await safe_edit(
                query,
                render_game(
                    game,
                    f"🛒 @{player['name']} compró {item['name']}"
                ),
                main_keyboard()
            )

        # =================================================
        # USE ITEM
        # =================================================

        elif data.startswith("use_"):

            player = game.current_player()

            if player["used_item_turn"]:
                return

            item_id = int(
                data.replace("use_", "")
            )

            if item_id not in player["items"]:
                return

            item = ITEMS[item_id]

            player["used_item_turn"] = True

            # =============================================
            # TARGET ITEMS
            # =============================================

            if item["tipo"] in ["skip", "trap"]:

                keyboard = []

                for pid, p in game.players.items():

                    if pid == user_id:
                        continue

                    keyboard.append([

                        InlineKeyboardButton(
                            f"@{p['name']}",
                            callback_data=f"target_{item_id}_{pid}"
                        )
                    ])

                await safe_edit(
                    query,
                    "🎯 Escoge objetivo",
                    InlineKeyboardMarkup(keyboard)
                )

                return

            txt = ""

            if item["tipo"] == "move":

                player["pos"] += item["valor"]

                txt = "🐴 Avanzas 6"

            elif item["tipo"] == "boost":

                player["boost"] = True

                txt = "🔥 Próximo dado x2"

            elif item["tipo"] == "random":

                if random.random() < 0.5:

                    player["pos"] += 10

                    txt = "☢️ +10 casillas"

                else:

                    player["pos"] -= 5

                    txt = "💀 -5 casillas"

            player["pos"] = safe_pos(
                player["pos"],
                game.max_pos
            )

            player["items"].remove(item_id)

            await safe_edit(
                query,
                render_game(game, txt),
                main_keyboard()
            )

        # =================================================
        # TARGET
        # =================================================

        elif data.startswith("target_"):

            split = data.split("_")

            item_id = int(split[1])
            target_id = int(split[2])

            player = game.current_player()
            target = game.players[target_id]

            item = ITEMS[item_id]

            txt = ""

            if item["tipo"] == "skip":

                target["skip"] += 1

                txt = (
                    f"🚁 @{target['name']} pierde turno"
                )

            elif item["tipo"] == "trap":

                target["pos"] -= 8

                target["pos"] = safe_pos(
                    target["pos"],
                    game.max_pos
                )

                txt = (
                    f"🍌 @{target['name']} resbaló"
                )

            player["items"].remove(item_id)

            await safe_edit(
                query,
                render_game(game, txt),
                main_keyboard()
            )

        # =================================================
        # BACK
        # =================================================

        elif data == "back":

            await safe_edit(
                query,
                render_game(game),
                main_keyboard()
            )

    finally:

        game.processing = False


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("crear", crear))
    app.add_handler(CommandHandler("unirse", unirse))
    app.add_handler(CommandHandler("jugar", jugar))

    app.add_handler(
        CallbackQueryHandler(buttons)
    )

    print("BOT RUNNING...")

    app.run_polling()
