import random
from items import ITEMS
from config import MAP_SIZES

class MisterPipaGame:
    def __init__(self, chat_id, players):
        self.chat_id = chat_id
        # Tamaño según jugadores
        self.max_pos = MAP_SIZES.get(len(players), 100)
        
        self.players = {
            p["id"]: {
                "name": p["name"],
                "pos": 0,
                "coins": 0,          # Ya no se usa, pero se deja para no romper referencias
                "items": [],         
                "skip": 0,
                "boost": False,
                "modifier": 0,
                "used_item_turn": False,
                "emoji": p.get("emoji", "🏃"),
                "is_npc": str(p["id"]).startswith("npc_")
            }
            for p in players
        }
        
        self.order = [p["id"] for p in players]
        self.current_idx = 0
        self.rounds = 1
        
        # SISTEMA DE VOTACIÓN (Para el 1/1 o 2/2)
        self.pending_vote = None  
        self.processing = False
        self.turn_version = 0
        self.message_id = None

    def current_player_id(self):
        return self.order[self.current_idx]

    def current_player(self):
        return self.players[self.current_player_id()]

    def next_turn(self):
        """Avanza el turno y limpia estados"""
        self.turn_version += 1
        self.current_idx = (self.current_idx + 1) % len(self.order)
        
        if self.current_idx == 0:
            self.rounds += 1
        
        # Reset de acción
        self.current_player()["used_item_turn"] = False

    def give_money(self, player):
        """Función vacía para eliminar la economía sin dar error"""
        return ""

    def resolve_vote_pipa(self):
        """Mister Pipa lanza la moneda para romper empates"""
        decision = random.choice([True, False])
        return decision, "¡Salió CARA! ¿Y por qué no?" if decision else "¡Salió CRUZ! Hoy no me apetece."
