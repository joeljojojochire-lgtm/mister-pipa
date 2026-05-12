# game.py
import random
from items import ITEMS, SHOP_RESPAWN
from config import MAP_SIZES

class MisterPipaGame:
    def __init__(self, chat_id, players):
        self.chat_id = chat_id
        self.max_pos = MAP_SIZES.get(len(players), 100)
        self.players = {
            p["id"]: {
                "name": p["name"],
                "pos": 0,
                "coins": 20,
                "items": [],
                "skip": 0,
                "boost": False,
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
        self.turn_version += 1
        self.current_idx = (self.current_idx + 1) % len(self.order)
        if self.current_idx == 0:
            self.rounds += 1
            self.refresh_shop()
        self.current_player()["used_item_turn"] = False

    def refresh_shop(self):
        restore = []
        for item_id in list(self.shop_cooldowns.keys()):
            self.shop_cooldowns[item_id] -= 1
            if self.shop_cooldowns[item_id] <= 0:
                restore.append(item_id)
        for item_id in restore:
            self.shop[item_id] = ITEMS[item_id]
            del self.shop_cooldowns[item_id]
