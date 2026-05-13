import random
from utils import safe_pos

# Diccionario de celdas especiales: {casilla: (mensaje, nueva_posicion)}
SPECIAL_CELLS = {
    5: ("¡Mister Pipa te regala un batido energético!", 10),
    12: ("Te detienes a firmar autógrafos y pierdes el ritmo.", 8),
    19: ("¡Atajo por las alcantarillas! Apareces mucho más adelante.", 35),
    28: ("Un viento fuerte te empuja hacia atrás.", 20),
    34: ("¡Lodo pegajoso! Te cuesta salir de aquí.", 27),
    46: ("Un fan emocionado te carga en hombros.", 55),
    58: ("Te equivocas de camino en la selva.", 50),
    65: ("¡Encuentras un patinete abandonado!", 75),
    82: ("¡Turbo ilegal activado! ¡Vuela!", 95),
    94: ("¡Un bache gigante! Retrocedes por el golpe.", 85),
    105: ("Recta final: ¡La adrenalina te hace correr!", 115),
}

async def apply_random_event(game, player):
    """
    Verifica si el jugador cayó en una celda especial y aplica el efecto.
    Retorna: (mensaje_extra, humor_pipa, markup_adicional)
    """
    pos = player["pos"]
    
    # 1. Verificar si cayó en una celda especial definida
    if pos in SPECIAL_CELLS:
        msg, new_pos = SPECIAL_CELLS[pos]
        player["pos"] = safe_pos(new_pos, game.max_pos)
        
        # Determinar si el efecto fue bueno o malo para el humor de Pipa
        mood = "boost" if new_pos > pos else "bad"
        return f"\n✨ <b>EVENTO:</b> {msg}", mood, None

    # 2. Evento aleatorio muy raro (opcional, 5% de probabilidad si no hay celda especial)
    if random.random() < 0.05:
        luck = random.randint(-5, 5)
        if luck > 0:
            player["pos"] = safe_pos(player["pos"] + luck, game.max_pos)
            return f"\n🍀 ¡Encontraste un trébol! Avanzas {luck}m.", "boost", None
        elif luck < 0:
            player["pos"] = safe_pos(player["pos"] + luck, game.max_pos)
            return f"\n☁️ Un nubarrón te distrae. Retrocedes {abs(luck)}m.", "bad", None

    return "", "default", None
