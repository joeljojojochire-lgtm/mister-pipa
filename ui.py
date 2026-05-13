from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import PIPA_EMOJIS

def render_game(game, event_text="", pipa_mood="default"):
    """
    Renderiza la interfaz visual: Banner de Gato + Pista Clásica + Narrativa.
    No se ha eliminado ninguna lógica de juego, solo se simplificó la vista.
    """
    # 1. DISEÑO DE CABECERA (Banner del Gato corregido para móviles)
    banner = (
        "<code>"
        "  ──▄▀▄─────▄▀▄──\n"
        "  ─▄█░░▀▀▀▀▀░░█▄─\n"
        "  ─█░░░░░░░░░░░█─\n"
        "  ─█░░▀░░┬░░▀░░█─\n"
        "  ☆•.¸★ 🄼🄸🅂🅃🄴🅁 🄿🄸🄿🄰 ★⡀.•☆</code>"
    )
    
    # 2. EL TABLERO VISUAL (Pista Clásica de puntos)
    track_width = 15 
    board = "<code>"
    board += "╔═══════════════════════════╗\n"
    
    for pid in game.order:
        p = game.players[pid]
        emoji = p.get("emoji", "🏃")
        
        # Cálculo de posición visual en la pista de 15 puntos
        pos_visual = int((p['pos'] / game.max_pos) * track_width)
        pos_visual = max(0, min(track_width, pos_visual))
        
        # Nombre del jugador (máximo 8 caracteres para no romper la tabla)
        name_display = (p['name'][:6] + "..") if len(p['name']) > 8 else p['name'].ljust(8)
        
        # DIBUJO DEL CARRIL: El emoji avanza sobre los puntos
        lane = "." * pos_visual + emoji + "." * (track_width - pos_visual)
        board += f"║ {name_display}: {lane}🥅 ║\n"
        
    board += "╚═══════════════════════════╝</code>"

    # 3. NARRATIVA DE MISTER PIPA
    pipa_icon = PIPA_EMOJIS.get(pipa_mood, "😀")
    # Mostramos el texto del evento (caos, ataques, bromas)
    narrative = f"{pipa_icon} **MISTER PIPA DICE:**\n_{event_text}_"

    # 4. INFO DE POSICIÓN Y TURNO (Sin Tienda ni Monedas)
    current = game.current_player()
    stats = f"\n\n🏁 **Meta:** {game.max_pos}m | 📍 **Posición:** {current['pos']}m"
    footer = f"\n👉 Turno de: **{current['name']}**"

    return f"{banner}\n\n{board}\n{narrative}{stats}{footer}"

# =========================================================
# TECLADOS (SISTEMA IDEAL: Solo Acción)
# =========================================================

def main_keyboard():
    """
    Solo botón de Dado. 
    Se eliminó el botón de Tienda para cumplir con el 'Sistema Ideal'.
    """
    keyboard = [
        [InlineKeyboardButton("🎲 Tirar dado", callback_data="roll")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Nota: shop_keyboard ha sido eliminada para evitar que el jugador 
# acceda a la gestión compleja, favoreciendo los eventos automáticos.
