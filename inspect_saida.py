import os
import sys

# Add the project root to sys.path
sys.path.append(os.getcwd())

from galint_flask import create_app
from galint_flask.models import Saida

app = create_app()
with app.app_context():
    print("Columns in Saida table:")
    for col in Saida.__table__.columns:
        print(col.name)
