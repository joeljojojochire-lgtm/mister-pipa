from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup

from items import ITEMS


def render_game(game, event=""):

    txt = (
        f"🏝️ MISTER PIPA SHOW\n\n"
        f"📅 Ronda {game.rounds}\n\n"
    )

    ordered = sorted(
        game.players.items(),
        key=lambda x: x[1]["pos"],
        reverse=True
    )

    medals = ["🥇", "🥈", "🥉"]

    for i, (pid, p) in enumerate(ordered[:3]):

        medal = medals[i]

        txt += (
            f"{medal} @{p['name']} "
            f"📍{p['pos']} "
            f"🪙{p['coins']}\n"
        )

    if event:
        txt += f"\n{event}\n"

    current = game.current_player()

    txt += f"\n👉 Turno de @{current['name']}"

    return txt


# =========================================================


def main_keyboard():

    keyboard = [

        [
            InlineKeyboardButton(
                "🎲 Tirar dado",
                callback_data="roll"
            )
        ],

        [
            InlineKeyboardButton(
                "🛒 Tienda",
                callback_data="shop"
            ),

            InlineKeyboardButton(
                "🎒 Inventario",
                callback_data="inventory"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================


def shop_keyboard(game, player):

    keyboard = []

    for item_id, item in game.shop.items():

        if player["coins"] < item["precio"]:
            continue

        keyboard.append([

            InlineKeyboardButton(
                f"{item['emoji']} {item['name']} -{item['precio']}",
                callback_data=f"buy_{item_id}"
            )
        ])

    keyboard.append([

        InlineKeyboardButton(
            "⬅️ Volver",
            callback_data="back"
        )
    ])

    return InlineKeyboardMarkup(keyboard)


# =========================================================


def inventory_keyboard(player):

    keyboard = []

    for item_id in player["items"]:

        item = ITEMS[item_id]

        keyboard.append([

            InlineKeyboardButton(
                f"{item['emoji']} {item['name']}",
                callback_data=f"use_{item_id}"
            )
        ])

    keyboard.append([

        InlineKeyboardButton(
            "⬅️ Volver",
            callback_data="back"
        )
    ])

    return InlineKeyboardMarkup(keyboard)