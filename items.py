ITEMS = {
    1: {
        "name": "Pony",
        "emoji": "🐴",
        "precio": 25,  # Antes 35 (Más accesible al inicio)
        "tipo": "move",
        "valor": 6,
    },

    2: {
        "name": "Dron",
        "emoji": "🚁",
        "precio": 75,  # Antes 90 (Facilita el sabotaje estratégico)
        "tipo": "skip",
        "valor": 1,
    },

    3: {
        "name": "Turbo",
        "emoji": "🔥",
        "precio": 55,  # Antes 70
        "tipo": "boost",
        "valor": 2,
    },

    4: {
        "name": "Banana",
        "emoji": "🍌",
        "precio": 40,  # Antes 60 (Para que haya más caos en la pista)
        "tipo": "trap",
        "valor": -8,
    },

    5: {
        "name": "Bebida",
        "emoji": "☢️",
        "precio": 30,  # Antes 45 (Ideal para arriesgarse)
        "tipo": "random",
    }
}

# RESPAWN: Cuántas rondas tarda en volver a la tienda tras ser comprado
SHOP_RESPAWN = {
    1: 2,  # Pony: Vuelve rápido (cada 2 rondas)
    2: 4,  # Dron: Es poderoso, tarda un poco más
    3: 3,  # Turbo: Equilibrio
    4: 2,  # Banana: Para que siempre haya peligro
    5: 2,  # Bebida: Rotación constante
}
