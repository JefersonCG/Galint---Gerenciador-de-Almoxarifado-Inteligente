"""Cria ou atualiza um usuário de teste (admin) com senha conhecida.

Uso:
    python scripts/ensure_test_admin.py [MATRICULA] [SENHA]

Se não passar args, cria matricula 9999999999991 com senha 'galintadmin'.
"""
import sys
from pathlib import Path
from werkzeug.security import generate_password_hash

# Ajustar sys.path quando executado como script
sys.path.insert(0, str(Path(__file__).parent.parent))

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Usuario


def main(argv):
    matricula = argv[1] if len(argv) > 1 else "9999999999991"
    senha = argv[2] if len(argv) > 2 else "galintadmin"

    app = create_app()
    with app.app_context():
        usuario = Usuario.query.get(matricula)
        if not usuario:
            usuario = Usuario(
                matricula=matricula,
                nome="Admin Test",
                setor="TI",
                cargo="Administrador",
                senha_hash=generate_password_hash(senha),
                is_admin=1,
                is_standard=1,
            )
            db.session.add(usuario)
            db.session.commit()
            print(f"Criado usuário de teste: matricula={matricula} senha={senha}")
        else:
            usuario.senha_hash = generate_password_hash(senha)
            usuario.is_admin = 1
            db.session.commit()
            print(f"Atualizado senha do usuário existente: matricula={matricula} senha={senha}")


if __name__ == "__main__":
    main(sys.argv)
