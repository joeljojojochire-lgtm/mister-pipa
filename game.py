import random
from items import ITEMS
from config import MAP_SIZES

class MisterPipaGame:
    def __init__(self, chat_id, players):
        self.chat_id = chat_id
        # Define el tamaño del mapa según jugadores, por defecto 100
        self.max_pos = MAP_SIZES.get(len(players), 100)
        
        self.players = {
            p["id"]: {
                "name": p["name"],
                "pos": 0,
                "coins": 0,          # Residuo de economía (sin uso)
                "items": [],         # Residuo de inventario (sin uso)
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
        
        # SISTEMA DE VOTACIÓN Y FLUJO
        self.pending_vote = None  # Para votaciones 1/1 o 2/2
        self.processing = False
        self.turn_version = 0
        self.message_id = None

    def current_player_id(self):
        """Retorna el ID del jugador que tiene el turno"""
        return self.order[self.current_idx]

    def current_player(self):
        """Retorna el diccionario de datos del jugador actual"""
        return self.players[self.current_player_id()]

    def next_turn(self):
        """Avanza al siguiente jugador y gestiona rondas"""
        self.turn_version += 1
        self.current_idx = (self.current_idx + 1) % len(self.order)
        
        # Si volvemos al inicio de la lista, nueva ronda
        if self.current_idx == 0:
            self.rounds += 1
        
        # Reset de bandera de acción por turno
        self.current_player()["used_item_turn"] = False

    def give_money(self, player):
        """
        Mantenemos la función para evitar errores de referencia en bot.py, 
        pero ya no hace nada ni devuelve texto de dinero.
        """
        return ""
