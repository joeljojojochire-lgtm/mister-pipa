import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import PIPA_EMOJIS

def render_game(game, event_text="", pipa_mood="default"):
    """
    INTERFAZ MISTER PIPA RACE:
    - Cabecera del Gato (Marca Registrada).
    - Pista visual hasta 5 jugadores (Estilo Retro).
    - Narrativa de Mister Pipa con tus diálogos.
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
    
    # 2. PISTA DE CARRERAS (Estilo solicitado: 🐵──────🏃────────────🏁)
    track_len = 15 # Longitud visual de la pista
    race_visual = "\n"
    
    for pid in game.order:
        p = game.players[pid]
        # Calculamos posición relativa (0 a track_len)
        pos_rel = int((p['pos'] / game.max_pos) * track_len)
        pos_rel = max(0, min(track_len, pos_rel))
        
        # Construcción del carril
        line_before = "─" * pos_rel
        line_after = "─" * (track_len - pos_rel)
        
        # Si ya ganó, el emoji de corredor se vuelve una estrella o trofeo
        runner = "🏃" if p['pos'] < game.max_pos else "🏆"
        
        # Formato: Emoji_Jugador + Carril + Corredor + Carril + Meta
        race_visual += f"<code>{p['emoji']}{line_before}{runner}{line_after}🏁</code>\n"

    # 3. PANEL DE ESTADOS COMPACTO
    stats_panel = "\n"
    for pid in game.order:
        p = game.players[pid]
        current_mark = "▶️" if game.current_player_id() == pid else "  "
        stats_panel += f"{current_mark} <b>{p['name']}</b>: <code>{p['pos']}m</code>\n"

    # 4. NARRATIVA DE MISTER PIPA (Comentador)
    pipa_icon = PIPA_EMOJIS.get(pipa_mood, "😀")
    
    # Marco visual para el comentario
    narrative = (
        f"\n╔══ 🏝️ MISTER PIPA RACE ══╗\n"
        f"{race_visual}"
        f"{stats_panel}\n"
        f"{pipa_icon} <b>Pipa:</b> <i>{event_text}</i>\n"
        f"╚════════════════════════╝"
    )

    return f"{banner}\n{narrative}"

# =========================================================
# TECLADOS
# =========================================================

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Lanzar Dados", callback_data="roll")]
    ])

def vote_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ SÍ", callback_data="vote_yes"),
            InlineKeyboardButton("❌ NO", callback_data="vote_no")
        ]
    ])
