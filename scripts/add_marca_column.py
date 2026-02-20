from app import create_app
from sqlalchemy import text

app = create_app()
with app.app_context():
    from galint_flask.extensions import db
    engine = db.engine
    try:
        # Try adding column; in many DBs this will succeed, in others raise if exists
        engine.execute(text("ALTER TABLE itens ADD COLUMN marca VARCHAR"))
        print("Coluna 'marca' adicionada com sucesso.")
    except Exception as exc:
        print("Não foi possível adicionar a coluna (provavelmente já existe):", exc)
        print("Verifique o esquema do banco. Nenhuma alteração foi aplicada.")
