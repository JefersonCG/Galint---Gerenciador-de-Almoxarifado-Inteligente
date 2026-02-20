from galint_flask import create_app
from galint_flask.models import Usuario

app = create_app()

with app.app_context():
    user = Usuario.query.filter_by(matricula='9840737226325').first()
    if not user:
        print('USER_NOT_FOUND')
    else:
        print(f"matricula: {user.matricula}")
        print(f"nome: {user.nome}")
        print(f"is_admin: {user.is_admin}")
        print(f"cargo: {user.cargo}")
        print(f"setor: {user.setor}")
