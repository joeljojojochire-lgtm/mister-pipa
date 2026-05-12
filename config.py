import os

# --- CONFIGURACIÓN BÁSICA (Mantenida) ---
MAX_PLAYERS = 5
MAX_RONDAS = 50
VOTE_TIMEOUT = 15
MAX_ITEMS_PER_TURN = 1

MAP_SIZES = {
    2: 70,
    3: 85,
    4: 100,
    5: 110,
}

# --- NUEVA CONFIGURACIÓN VISUAL 2.0 ---

# Imagen de cabecera (puedes sustituir esta URL por la que prefieras)
HEADER_IMAGE = "https://i.ibb.co/vzYm8m8/mister-pipa-header.jpg"

# Texto del banner animado
MARQUEE_TEXT = "ღ(¯◕‿◕´¯) ♫ ♪ ♫ mister pipa ♫ ♪ ♫ (¯◕‿◕´¯)ღ"

# Estados de ánimo de Mister Pipa (según el evento)
PIPA_EMOJIS = {
    "default": "😀",
    "roll": "😄",
    "sabotage": "😆",
    "joke": "😂",
    "boost": "😇",
    "vote": "🧐",
    "result": "🫡"
}

# Pool de emojis para los jugadores (se asignan al azar al unirse)
PLAYER_EMOJIS = [
    "🚗", "🚲", "🦖", "🛸", "🏄", "👻", "🤖", "🐥", 
    "🐒", "🦄", "🏎️", "🚁", "🍕", "🧨", "⚽", "🐱"
]
