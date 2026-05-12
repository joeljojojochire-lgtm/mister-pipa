if item_id not in player["items"]:
                return

            item = ITEMS[item_id]

            player["used_item_turn"] = True

            # =============================================
            # TARGET ITEMS
            # =============================================

            if item["tipo"] in ["skip", "trap"]:

                keyboard = []

                for pid, p in game.players.items():

                    if pid == user_id:
                        continue

                    keyboard.append([

                        InlineKeyboardButton(
                            f"@{p['name']}",
                            callback_data=f"target_{item_id}_{pid}"
                        )
                    ])

                await safe_edit(
                    query,
                    "🎯 Escoge objetivo",
                    InlineKeyboardMarkup(keyboard)
                )

                return

            txt = ""

            if item["tipo"] == "move":

                player["pos"] += item["valor"]

                txt = "🐴 Avanzas 6"

            elif item["tipo"] == "boost":

                player["boost"] = True

                txt = "🔥 Próximo dado x2"

            elif item["tipo"] == "random":

                if random.random() < 0.5:

                    player["pos"] += 10

                    txt = "☢️ +10 casillas"

                else:

                    player["pos"] -= 5

                    txt = "💀 -5 casillas"

            player["pos"] = safe_pos(
                player["pos"],
                game.max_pos
            )

            player["items"].remove(item_id)

            await safe_edit(
                query,
                render_game(game, txt),
                main_keyboard()
            )

        # =================================================
        # TARGET
        # =================================================

        elif data.startswith("target_"):

            split = data.split("_")

            item_id = int(split[1])
            target_id = int(split[2])

            player = game.current_player()
            target = game.players[target_id]

            item = ITEMS[item_id]

            txt = ""

            if item["tipo"] == "skip":

                target["skip"] += 1

                txt = (
                    f"🚁 @{target['name']} pierde turno"
                )

            elif item["tipo"] == "trap":

                target["pos"] -= 8

                target["pos"] = safe_pos(
                    target["pos"],
                    game.max_pos
                )

                txt = (
                    f"🍌 @{target['name']} resbaló"
                )

            player["items"].remove(item_id)

            await safe_edit(
                query,
                render_game(game, txt),
                main_keyboard()
            )

        # =================================================
        # BACK
        # =================================================

        elif data == "back":

            await safe_edit(
                query,
                render_game(game),
                main_keyboard()
            )

    finally:

        game.processing = False


# =========================================================
# MAIN
# =========================================================

if name == "main":

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("crear", crear))
    app.add_handler(CommandHandler("unirse", unirse))
    app.add_handler(CommandHandler("jugar", jugar))

    app.add_handler(
        CallbackQueryHandler(buttons)
    )

    print("BOT RUNNING...")

    app.run_polling()