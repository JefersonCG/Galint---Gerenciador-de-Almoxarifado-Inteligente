from galint_flask import create_app
from galint_flask.extensions import db
from sqlalchemy import inspect

app = create_app()

with app.app_context():
    insp = inspect(db.engine)
    for table_name in ["itens", "saidas"]:
        cols = insp.get_columns(table_name)
        print(f"TABLE {table_name}")
        for col in cols:
            print(f" - {col['name']}: {col['type']}")
        print()
