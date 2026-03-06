from galint_flask import create_app

app = create_app()
with app.app_context():
    scheduler = app.extensions.get('scheduler')
    if not scheduler:
        print('Scheduler não encontrado no app.extensions')
    else:
        print('Executando limpeza agora...')
        scheduler.run_cleanup_now(app, days=180)
        print('Pronto.')
