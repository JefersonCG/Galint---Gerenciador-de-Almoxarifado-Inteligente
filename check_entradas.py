"""Verifica entradas de hoje."""
from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Entrada, EntradaRegistro30Dias
from datetime import datetime, timezone

app = create_app()
with app.app_context():
    # Ciclo ativo
    cycle = db.session.query(EntradaRegistro30Dias).filter_by(ativo=True).first()
    
    if cycle:
        print(f"Ciclo ativo: ID={cycle.id}")
        print(f"Data inicio: {cycle.data_inicio}")
        print(f"Data fim: {cycle.data_fim}")
    else:
        print("NENHUM CICLO ATIVO!")
    
    # Entradas de hoje
    hoje_inicio = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    entradas_hoje = db.session.query(Entrada).filter(
        Entrada.data_entrada >= hoje_inicio
    ).all()
    
    print(f"\n--- ENTRADAS DE HOJE ({len(entradas_hoje)}) ---")
    for e in entradas_hoje[:5]:
        print(f"ID: {e.id_entrada} | {e.data_entrada} | {e.item.descricao if e.item else 'SEM ITEM'}")
    
    # Ultimas 5 entradas
    ultimas = db.session.query(Entrada).order_by(Entrada.data_entrada.desc()).limit(5).all()
    print(f"\n--- ULTIMAS 5 ENTRADAS ---")
    for e in ultimas:
        print(f"ID: {e.id_entrada} | {e.data_entrada} | {e.item.descricao if e.item else 'SEM ITEM'}")
    
    # Entradas dentro do ciclo
    if cycle:
        entradas_ciclo = db.session.query(Entrada).filter(
            Entrada.data_entrada >= cycle.data_inicio
        ).count()
        print(f"\n--- ENTRADAS NO CICLO ATIVO: {entradas_ciclo} ---")
