import random
from items import ITEMS, SHOP_RESPAWN
from config import MAP_SIZES

class MisterPipaGame:
    def __init__(self, chat_id, players):
        self.chat_id = chat_id
        # Usamos .get para evitar errores si el número de jugadores no está en el config
        self.max_pos = MAP_SIZES.get(len(players), 100)
        self.players = {
            p["id"]: {
                "name": p["name"],
                "pos": 0,
                "coins": 20,
                "items": [],
                "skip": 0,
                "boost": False,
                "modifier": 0,  # <--- CORRECCIÓN TÉCNICA: Vital para que funcionen los ítems sin dar error
                "used_item_turn": False,
                "emoji": p.get("emoji", "🏃")
            }
            for p in players
        }
        self.order = [p["id"] for p in players]
        self.current_idx = 0
        self.rounds = 1
        self.shop = ITEMS.copy()
        self.shop_cooldowns = {}
        self.pending_vote = None
        self.processing = False
        self.turn_version = 0
        self.message_id = None

    def current_player_id(self):
        return self.order[self.current_idx]

    def current_player(self):
        return self.players[self.current_player_id()]

    def next_turn(self):
        """Avanza al siguiente turno y gestiona las rondas"""
        self.turn_version += 1
        self.current_idx = (self.current_idx + 1) % len(self.order)
        
        # Si volvemos al primer jugador, aumenta la ronda
        if self.current_idx == 0:
            self.rounds += 1
            self.refresh_shop()
        
        # Resetear flag de objeto usado para el nuevo jugador
        self.current_player()["used_item_turn"] = False

    def refresh_shop(self):
        """Gestiona el tiempo de espera de los objetos en la tienda"""
        restore = []
        # Convertimos a lista las llaves para poder borrar mientras iteramos (Evita RuntimeError en Render)
        for item_id in list(self.shop_cooldowns.keys()):
            self.shop_cooldowns[item_id] -= 1
            if self.shop_cooldowns[item_id] <= 0:
                restore.append(item_id)
        
        for item_id in restore:
            if item_id in ITEMS:
                self.shop[item_id] = ITEMS[item_id]
            if item_id in self.shop_cooldowns:
                del self.shop_cooldowns[item_id]

    def give_money(self, player):
        """Sistema de recompensa de monedas e impuestos"""
        gain = random.randint(3, 8)
        player["coins"] += gain
        
        # 10% de probabilidad de impuesto nuclear
        if random.random() < 0.10:
            tax = random.randint(5, 12)
            player["coins"] = max(0, player["coins"] - tax)
            return f" 💸 ¡Impuesto nuclear! Mister Pipa te quita {tax} monedas."
        return ""
