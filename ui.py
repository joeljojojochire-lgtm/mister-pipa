import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import PIPA_EMOJIS

def render_game(game, event_text="", pipa_mood="default"):
    """
    NUEVA INTERFAZ 2.0: 
    - Pista limpia con corredores y metas.
    - Panel de estados (🤩/😣 Nombre Emoji Posición/Meta).
    - Mantiene al Gato y al Mister Pipa comentador.
    """
    
    # 1. CABECERA (El Gato se queda igual, es nuestra marca)
    banner = (
        "<code>"
        "  ──▄▀▄─────▄▀▄──\n"
        "  ─▄█░░▀▀▀▀▀░░█▄─\n"
        "  ─█░░░░░░░░░░░█─\n"
        "  ─█░░▀░░┬░░▀░░█─\n"
        "  ☆•.¸★ 🄼🄸🅂🅃🄴🅁 🄿🄸🄿🄰 ★⡀.•☆</code>"
    )
    
    # 2. PISTA DE CARRERAS (Diseño horizontal limpio)
    # Añadimos un pequeño movimiento de "balanceo" al azar para simular que corren
    track_width = 12
    race_visual = "<code>"
    for pid in game.order:
        p = game.players[pid]
        # Posición proporcional a la meta
        pos_relativa = int((p['pos'] / game.max_pos) * track_width)
        pos_relativa = max(0, min(track_width, pos_relativa))
        
        # Efecto de movimiento: si no está en la meta, baila un poco
        offset = " " if (random.random() > 0.5 and pos_relativa < track_width) else ""
        
        carril = " " * pos_relativa + p['emoji'] + offset + " " * (track_width - pos_relativa)
        race_visual += f"{carril} 🥅\n"
    race_visual += "</code>"

    # 3. PANEL DE ESTADOS (Lo que dibujaste: 🤩Joel 🙉 8/40)
    stats_panel = ""
    for pid in game.order:
        p = game.players[pid]
        
        # Lógica de ánimos automática
        if game.current_player_id() == pid:
            mood = "⚡" # Es su turno
        elif p['pos'] >= game.max_pos * 0.8:
            mood = "🤩" # Cerca de ganar
        elif p['pos'] < 5:
            mood = "😏" # Empezando
        else:
            mood = random.choice(["🏃", "💪", "🔥"]) # En movimiento
            
        # Formateo: Estado + Nombre + Emoji + Progreso
        stats_panel += f"{mood} <b>{p['name']}</b> {p['emoji']} | <code>{p['pos']}/{game.max_pos}m</code>\n"

    # 4. NARRATIVA DE MISTER PIPA (Comentador)
    pipa_icon = PIPA_EMOJIS.get(pipa_mood, "😀")
    narrative = f"\n{pipa_icon} <b>MISTER PIPA DICE:</b>\n<i>{event_text}</i>"

    return f"{banner}\n\n{race_visual}\n{stats_panel}{narrative}"

# =========================================================
# TECLADOS (Sin cambios para mantener estabilidad)
# =========================================================

def main_keyboard():
    keyboard = [[InlineKeyboardButton("🎲 Tirar dado", callback_data="roll")]]
    return InlineKeyboardMarkup(keyboard)

def vote_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ SÍ", callback_data="vote_yes"),
            InlineKeyboardButton("❌ NO", callback_data="vote_no")
        ]
    ])
