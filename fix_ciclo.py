"""Corrige data de inicio do ciclo."""
from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import EntradaRegistro30Dias
from datetime import datetime, timezone

app = create_app()
with app.app_context():
    cycle = db.session.query(EntradaRegistro30Dias).filter_by(ativo=True).first()
    
    if cycle:
        print(f"Ciclo atual: ID={cycle.id}")
        print(f"Data inicio ANTIGA: {cycle.data_inicio}")
        
        # Ajustar para inicio do dia 23/01/2026
        nova_data = datetime(2026, 1, 23, 0, 0, 0)
        cycle.data_inicio = nova_data
        
        db.session.commit()
        
        print(f"Data inicio NOVA: {cycle.data_inicio}")
        print("Ciclo atualizado com sucesso!")
    else:
        print("Nenhum ciclo ativo encontrado")
