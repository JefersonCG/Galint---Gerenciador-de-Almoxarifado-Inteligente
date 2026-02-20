from sqlalchemy import func

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import EntradaRegistro30Dias, Entrada


def main() -> None:
    app = create_app()
    with app.app_context():
        cycle = (
            db.session.query(EntradaRegistro30Dias)
            .filter(EntradaRegistro30Dias.ativo.is_(True))
            .order_by(EntradaRegistro30Dias.id.desc())
            .first()
        )
        if cycle:
            print(
                "CYCLE",
                {
                    "id": cycle.id,
                    "inicio": cycle.data_inicio,
                    "fim": cycle.data_fim,
                    "pdf": cycle.pdf_gerado,
                    "ativo": cycle.ativo,
                },
            )
        else:
            print("CYCLE", None)

        total = db.session.query(func.count(Entrada.id_entrada)).scalar() or 0
        print("ENTRADAS_TOTAL", total)

        if cycle:
            entradas_cycle = (
                db.session.query(Entrada)
                .filter(func.date(Entrada.data_entrada) >= func.date(cycle.data_inicio))
                .order_by(Entrada.data_entrada.desc())
                .limit(5)
                .all()
            )
            print("ENTRADAS_CYCLE_COUNT", len(entradas_cycle))
            for entrada in entradas_cycle:
                print(
                    "-",
                    entrada.id_entrada,
                    entrada.codigo_item,
                    entrada.data_entrada,
                    entrada.quantidade,
                    entrada.nota_fiscal,
                )
        else:
            entradas_latest = (
                db.session.query(Entrada)
                .order_by(Entrada.data_entrada.desc())
                .limit(5)
                .all()
            )
            for entrada in entradas_latest:
                print(
                    "-",
                    entrada.id_entrada,
                    entrada.codigo_item,
                    entrada.data_entrada,
                    entrada.quantidade,
                    entrada.nota_fiscal,
                )


if __name__ == "__main__":
    main()
