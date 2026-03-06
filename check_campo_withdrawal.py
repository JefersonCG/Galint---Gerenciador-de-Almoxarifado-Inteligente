from galint_flask import create_app
from galint_flask.extensions import db
from sqlalchemy import inspect

app = create_app()
with app.app_context():
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('telegram_users')]
    
    if 'can_withdraw_via_telegram' in columns:
        print('\n[OK] Campo can_withdraw_via_telegram EXISTE no banco!')
        exit(0)
    else:
        print('\n[ERRO] Campo can_withdraw_via_telegram NAO encontrado')
        print('Colunas encontradas:', columns)
        exit(1)
