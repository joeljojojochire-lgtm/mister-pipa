from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from items import ITEMS
from config import MARQUEE_TEXT, PIPA_EMOJIS

def render_game(game, event_text="", pipa_mood="default"):
    # 1. Banner Animado
    shift = game.rounds % 4
    marquee = (" " * shift) + MARQUEE_TEXT
    
    # --- LÓGICA DE CÁMARA MÓVIL ---
    view_range = 14  # Cuántas casillas se ven en pantalla
    center = view_range // 2
    board = "<code>"
    board += "╔══════════════════════════════╗\n"
    
    # Definimos el escenario fijo (puedes mover esto a config.py luego)
    escenario = {5: "🌵", 12: "🌵", 18: "🐦", 25: "⛰️", 35: "🌵", 45: "🐦"}
    
    for pid in game.order:
        p = game.players[pid]
        emoji = p.get("emoji", "🏃")
        pos = p['pos']
        
        # El carril se construye relativo a la posición del jugador
        lane_list = ["."] * view_range
        
        # Calculamos qué parte del mundo cae dentro de nuestra ventana
        # La ventana empieza en (pos - centro) y termina en (pos + centro)
        inicio_v = pos - center
        
        # Dibujar obstáculos y meta que entren en la ventana
        for i in range(view_range):
            mundo_pos = inicio_v + i
            
            # Dibujar Meta
            if mundo_pos == game.max_pos:
                lane_list[i] = "🥅"
            # Dibujar Escenario
            elif mundo_pos in escenario:
                lane_list[i] = escenario[mundo_pos]
        
        # El jugador SIEMPRE está en el centro (o cerca si está al puro inicio)
        player_idx = center if pos >= center else pos
        if player_idx < view_range:
            lane_list[player_idx] = emoji
            
        lane = "".join(lane_list)
        name_display = (p['name'][:6] + "..") if len(p['name']) > 8 else p['name'].ljust(8)
        board += f"║ {name_display}: {lane} ║\n"
        
    board += "╚══════════════════════════════╝</code>"

    # Resto de la función (Mister Pipa dice, etc.) se queda igual
    pipa_icon = PIPA_EMOJIS.get(pipa_mood, "😀")
    narrative = f"{pipa_icon} **MISTER PIPA DICE:**\n_{event_text}_"
    current = game.current_player()
    stats = f"\n\n🪙 **Monedas:** {current['coins']} | 📍 **Posición:** {current['pos']}/{game.max_pos}m"
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
