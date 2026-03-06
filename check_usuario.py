from galint_flask import create_app
from galint_flask.models import Usuario

app = create_app()
with app.app_context():
    u = Usuario.query.filter(Usuario.nome.ilike('%ESTEVÃO%')).first()
    if u:
        print(f'Nome: {u.nome}')
        print(f'Matricula: {u.matricula}')
        print(f'Setor: {u.setor}')
        print(f'Cargo: {u.cargo}')
    else:
        print("Usuário não encontrado")
