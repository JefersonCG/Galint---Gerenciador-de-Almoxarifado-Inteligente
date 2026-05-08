from datetime import datetime
from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Saida, Item, Usuario

app = create_app()
with app.app_context():
    since = datetime(2026, 2, 4, 11, 0, 0)
    rows = (
        db.session.query(Saida, Item, Usuario)
        .outerjoin(Item, Saida.codigo_item == Item.codigo_item)
        .outerjoin(Usuario, Saida.matricula == Usuario.matricula)
        .filter(Saida.data_saida >= since)
        .order_by(Saida.data_saida.asc())
        .all()
    )

    print(f"Saidas desde {since} UTC: {len(rows)}")
    for saida, item, usuario in rows:
        print(
            saida.id_saida,
            saida.data_saida,
            saida.codigo_item,
            (item.descricao if item else None),
            saida.quantidade,
            (usuario.nome if usuario else None),
        )
