from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from items import ITEMS
from config import MARQUEE_TEXT, PIPA_EMOJIS

def render_game(game, event_text="", pipa_mood="default"):
    """
    Renderiza la interfaz visual 2.0 del juego (Solo Texto).
    """
    # 1. Banner Animado (Marquee)
    shift = game.rounds % 4
    marquee = (" " * shift) + MARQUEE_TEXT
    
    # 2. El Tablero Visual (Pista de Carreras)
    track_width = 15 
    board = "<code>"
    board += "╔═══════════════════════════╗\n"
    
    for pid in game.order:
        p = game.players[pid]
        emoji = p.get("emoji", "🏃")
        
        # Posición visual calculada
        pos_visual = int((p['pos'] / game.max_pos) * track_width)
        pos_visual = max(0, min(track_width, pos_visual))
        
        # Formatear nombre
        name_display = (p['name'][:6] + "..") if len(p['name']) > 8 else p['name'].ljust(8)
        
        # Dibujar carril (Puntos para el camino, Emojis para los corredores)
        lane = "." * pos_visual + emoji + "." * (track_width - pos_visual)
        board += f"║ {name_display}: {lane}🥅 ║\n"
        
    board += "╚═══════════════════════════╝</code>"

    # 3. Narrativa de Mister Pipa
    pipa_icon = PIPA_EMOJIS.get(pipa_mood, "😀")
    
    if not event_text:
        event_text = "¡El Show continúa! Nadie se rinde."

    narrative = f"{pipa_icon} **MISTER PIPA DICE:**\n_{event_text}_"

    # 4. Info de Economía y Turno
    current = game.current_player()
    stats = f"\n\n🪙 **Tus Monedas:** {current['coins']} | 🏁 **Meta:** {game.max_pos}m"
    footer = f"\n👉 Turno de: **{current['name']}**"

    return f"{marquee}\n\n{board}\n{narrative}{stats}{footer}"


# =========================================================
# TECLADOS (SIMPLIFICADOS: Sin Inventario)
# =========================================================

def main_keyboard():
    """Menú principal: Solo Dado y Tienda"""
    keyboard = [
        [InlineKeyboardButton("🎲 Tirar dado", callback_data="roll")],
        [InlineKeyboardButton("🛒 Abrir Tienda", callback_data="shop")]
    ]
    return InlineKeyboardMarkup(keyboard)

def shop_keyboard(game, player):
    """Teclado de la tienda: Los ítems se activan al pulsar"""
    keyboard = []
    
    # Solo mostramos ítems que están en stock (no en cooldown)
    for item_id, item in game.shop.items():
        # Indicador de si puede pagarlo
        can_buy = "✅" if player["coins"] >= item["precio"] else "❌"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{item['emoji']} {item['name']} ({item['precio']}🪙) {can_buy}",
                callback_data=f"buy_{item_id}"
            )
        ])
        
    keyboard.append([InlineKeyboardButton("⬅️ Volver a la Pista", callback_data="back")])
    return InlineKeyboardMarkup(keyboard)
