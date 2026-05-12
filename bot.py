async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    user_id = query.from_user.id

    if chat_id not in games:
        return

    game = games[chat_id]
    
    # Bloqueo de seguridad para evitar spam de clics
    if game.processing:
        return

    game.processing = True

    try:
        data = query.data
        # Solo el jugador actual puede interactuar
        if user_id != game.current_player_id():
            return

        if data == "roll":
            player = game.current_player()
            # Lógica de saltar turno
            if player["skip"] > 0:
                player["skip"] -= 1
                game.next_turn()
                await safe_edit(query, render_game(game, f"💫 @{player['name']} pierde turno"), main_keyboard())
                return

            dice = random.randint(1, 6)
            if player.get("boost"):
                dice *= 2
                player["boost"] = False

            player["pos"] += dice
            txt = f"🎲 @{player['name']} sacó {dice}"
            
            # Dinero por turno
            player["coins"] += random.randint(3, 8)

            # Celdas especiales
            if player["pos"] in SPECIAL_CELLS:
                msg, new_pos = SPECIAL_CELLS[player["pos"]]
                player["pos"] = new_pos
                txt += f"\n⚠️ {msg}"

            # Items gratis
            if player["pos"] in FREE_ITEM_CELLS:
                item_id = random.choice(list(ITEMS.keys()))
                player["items"].append(item_id)
                txt += f"\n🎁 ¡Encontraste {ITEMS[item_id]['name']}!"

            player["pos"] = safe_pos(player["pos"], game.max_pos)

            if player["pos"] >= game.max_pos:
                await safe_edit(query, f"🏆 @{player['name']} ha ganado el Mister Pipa Show!")
                del games[chat_id]
                return

            game.next_turn()
            await safe_edit(query, render_game(game, txt), main_keyboard())

        elif data == "shop":
            await safe_edit(query, "🛒 TIENDA DE PIPA", shop_keyboard(game, game.current_player()))

        elif data == "inventory":
            if not game.current_player()["items"]:
                await query.answer("Tu inventario está vacío 📭", show_alert=True)
                return
            await safe_edit(query, "🎒 TU INVENTARIO", inventory_keyboard(game.current_player()))

        elif data.startswith("buy_"):
            item_id = int(data.split("_")[1])
            player = game.current_player()
            if item_id in game.shop and player["coins"] >= ITEMS[item_id]["precio"]:
                player["coins"] -= ITEMS[item_id]["precio"]
                player["items"].append(item_id)
                # El item desaparece de la tienda hasta la siguiente ronda
                del game.shop[item_id] 
                await safe_edit(query, render_game(game, f"🛒 Compraste {ITEMS[item_id]['name']}"), main_keyboard())

        elif data.startswith("use_"):
            item_id = int(data.split("_")[1])
            player = game.current_player()
            
            if item_id in player["items"]:
                item = ITEMS[item_id]
                # Aquí puedes añadir la lógica específica de cada item
                # Por ahora, simplemente lo removemos como ejemplo de uso
                player["items"].remove(item_id)
                await safe_edit(query, render_game(game, f"✨ Usaste {item['name']}"), main_keyboard())

        elif data == "back":
            await safe_edit(query, render_game(game), main_keyboard())

    except Exception as e:
        print(f"Error crítico en botones: {e}")
    finally:
        # IMPORTANTE: Siempre liberamos el procesamiento
        game.processing = False
