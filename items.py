# items.py

ITEMS = {
    1: {
        "name": "Pony",
        "emoji": "🐴",
        "precio": 25,
        "tipo": "move",
        "valor": 6,
    },
    2: {
        "name": "Dron",
        "emoji": "🚁",
        "precio": 75,
        "tipo": "skip",
        "valor": 1,
    },
    3: {
        "name": "Turbo",
        "emoji": "🔥",
        "precio": 55,
        "tipo": "boost",
        "valor": 2,
    },
    4: {
        "name": "Banana",
        "emoji": "🍌",
        "precio": 40,
        "tipo": "trap",
        "valor": -8,
    },
    5: {
        "name": "Bebida",
        "emoji": "☢️",
        "precio": 30,
        "tipo": "random",
    }
}

SHOP_RESPAWN = {
    1: 2,  # Vuelve en 2 rondas
    2: 4,  # Vuelve en 4 rondas
    3: 3,
    4: 2,
    5: 1
}
