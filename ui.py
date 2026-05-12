from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from items import ITEMS
from config import MARQUEE_TEXT, PIPA_EMOJIS

def render_game(game, event_text="", pipa_mood="default"):
    """
    Renderiza la interfaz visual 2.0 del juego.
    """
    # 1. Banner Animado (Marquee)
    # Cambia ligeramente la posición según la ronda para simular movimiento
    shift = game.rounds % 4
    marquee = (" " * shift) + MARQUEE_TEXT
    
    # 2. El Tablero Visual (Pista de Carreras en bloque de código)
    track_width = 15 # Longitud visual de la pista
    board = "<code>"
    board += "╔═══════════════════════════╗\n"
    
    # Renderizamos a los jugadores en el orden de la partida
    for pid in game.order:
        p = game.players[pid]
        emoji = p.get("emoji", "🏃") # Usa emoji personalizado o el default
        
        # Calcular posición visual (regla de 3 simple sobre el ancho de pista)
        pos_visual = int((p['pos'] / game.max_pos) * track_width)
        pos_visual = max(0, min(track_width, pos_visual))
        
        # Formatear nombre (máximo 8 caracteres para no romper el marco)
        name_display = (p['name'][:6] + "..") if len(p['name']) > 8 else p['name'].ljust(8)
        
        # Dibujar carril
        lane = "." * pos_visual + emoji + "." * (track_width - pos_visual)
        board += f"║ {name_display}: {lane}🥅 ║\n"
        
    board += "╚═══════════════════════════╝</code>"

    # 3. Narrativa de Mister Pipa
    # Elegimos el emoji de Pipa según el contexto (mood)
    pipa_icon = PIPA_EMOJIS.get(pipa_mood, "😀")
    
    if not event_text:
        event_text = "¡Bienvenidos al Show! La pista está que arde."

    narrative = f"{pipa_icon} **MISTER PIPA DICE:**\n_{event_text}_"

    # 4. Info de Economía y Turno
    current = game.current_player()
    stats = f"\n\n🪙 **Tus Monedas:** {current['coins']} | 🏁 **Meta:** {game.max_pos}m"
    footer = f"\n👉 Turno de: **{current['name']}**"

    # Combinamos todo para el Caption Multimedia
    return f"{marquee}\n\n{board}\n{narrative}{stats}{footer}"


# =========================================================
# TECLADOS (Se mantienen según REGLA DE ORO)
# ==========================

def main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎲 Tirar dado", callback_data="roll")],
        [
            InlineKeyboardButton("🛒 Tienda", callback_data="shop"),
            InlineKeyboardButton("🎒 Inventario", callback_data="inventory")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def shop_keyboard(game, player):
    keyboard = []
    for item_id, item in game.shop.items():
        if player["coins"] < item["precio"]:
            continue
        keyboard.append([
            InlineKeyboardButton(
                f"{item['emoji']} {item['name']} -{item['precio']}🪙",
                callback_data=f"buy_{item_id}"
            )
        ])
    keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="back")])
    return InlineKeyboardMarkup(keyboard)

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
    keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="back")])
    return InlineKeyboardMarkup(keyboard)
