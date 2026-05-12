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
