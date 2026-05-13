from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import PIPA_EMOJIS

def render_game(game, event_text="", pipa_mood="default"):
    """
    Renderiza la interfaz visual sin tienda ni economía.
    """
    # 1. DISEÑO DE CABECERA (Gato corregido para móviles)
    banner = (
        "<code>"
        "  ──▄▀▄─────▄▀▄──\n"
        "  ─▄█░░▀▀▀▀▀░░█▄─\n"
        "  ─█░░░░░░░░░░░█─\n"
        "  ─█░░▀░░┬░░▀░░█─\n"
        "  ☆•.¸★ 🄼🄸🅂🅃🄴🅁 🄿🄸🄿🄰 ★⡀.•☆</code>"
    )
    
    # 2. LÓGICA DE CÁMARA MÓVIL
    view_range = 14  
    center = view_range // 2
    board = "<code>"
    board += "╔══════════════════════════╗\n" 
    
    escenario = {5: "🌵", 12: "🌵", 18: "🐦", 25: "⛰️", 35: "🌵", 45: "🐦", 60: "🌋"}
    
    for pid in game.order:
        p = game.players[pid]
        emoji = p.get("emoji", "🏃")
        pos = p['pos']
        
        lane_list = ["."] * view_range
        inicio_v = pos - center
        
        for i in range(view_range):
            mundo_pos = inicio_v + i
            if mundo_pos == game.max_pos:
                lane_list[i] = "🥅"
            elif mundo_pos in escenario:
                lane_list[i] = escenario[mundo_pos]
        
        player_idx = center if pos >= center else pos
        if 0 <= player_idx < view_range:
            lane_list[player_idx] = emoji
            
        lane = "".join(lane_list)
        name_display = (p['name'][:6] + "..") if len(p['name']) > 8 else p['name'].ljust(8)
        board += f"║ {name_display}: {lane} ║\n"
        
    board += "╚══════════════════════════╝</code>"

    # 3. NARRATIVA Y ESTADOS (Sin Monedas)
    pipa_icon = PIPA_EMOJIS.get(pipa_mood, "😀")
    narrative = f"{pipa_icon} **MISTER PIPA DICE:**\n_{event_text}_"
    
    current = game.current_player()
    stats = f"\n\n📍 **Posición:** {current['pos']}/{game.max_pos}m"
    footer = f"\n👉 Turno de: **{current['name']}**"

    return f"{banner}\n\n{board}\n{narrative}{stats}{footer}"

# =========================================================
# TECLADOS (SISTEMA IDEAL: Sin Tienda)
# =========================================================

def main_keyboard():
    """Menú principal: Solo el botón de acción para mantener el flujo rápido"""
    keyboard = [
        [InlineKeyboardButton("🎲 Tirar dado", callback_data="roll")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Se elimina shop_keyboard ya que no será necesaria
