import os
import sys
from datetime import datetime, date

# Add the project root to sys.path
sys.path.append(os.getcwd())

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, Saida, Entrada, InventarioEvento, Usuario

app = create_app()

with app.app_context():
    item_code = '7898259251860'
    # Use full matricula 2119407736820 as requested, or check both
    matriculas = ['1041362870312', '2119407736820']
    since_date = datetime(2026, 5, 15)

    item = Item.query.get(item_code)
    if not item:
        print(f"Item {item_code} not found.")
    else:
        print("--- ITEM INFO ---")
        print(f"Codigo: {item.codigo}")
        print(f"Descricao: {item.descricao}")
        print(f"Unidade: {item.unidade}")
        print(f"Quantidade Total Embalagem: {getattr(item, 'quantidade_total_embalagem', 'N/A')}")
        
        # Balance/Saldo
        if hasattr(item, 'get_saldo'):
            try:
                print(f"Saldo (get_saldo): {item.get_saldo()}")
            except:
                print("Saldo (get_saldo): Error calling method")
        elif hasattr(item, 'saldo'):
            print(f"Saldo: {item.saldo}")
        
        # Product Units relationship
        if hasattr(item, 'product_units'):
            print(f"Product Units: {len(item.product_units)} relationships found")
            for pu in item.product_units:
                print(f"  - {pu}")

    print("\n--- SAIDAS (Since 2026-05-15) ---")
    saidas = Saida.query.filter(
        Saida.codigo_item == item_code,
        Saida.matricula_usuario.in_(matriculas),
        Saida.data_saida >= since_date
    ).all()
    
    for s in saidas:
        print(f"ID: {s.id}")
        print(f"  Data Saida: {s.data_saida}")
        print(f"  Quantidade: {getattr(s, 'quantidade', 'N/A')}")
        print(f"  Qtd Total Embalagem: {getattr(s, 'quantidade_total_embalagem', 'N/A')}")
        print(f"  Qtd Retirada Litros: {getattr(s, 'quantidade_retirada_em_litros', 'N/A')}")
        print(f"  Qtd Retirada Quilos: {getattr(s, 'quantidade_retirada_em_quilos', 'N/A')}")
        print(f"  Qtd Restante: {getattr(s, 'quantidade_restante', 'N/A')}")
        print(f"  Usou Fracao: {getattr(s, 'usou_fracao', 'N/A')}")
        print(f"  Local Servico: {getattr(s, 'local_servico', 'N/A')}")
        print(f"  Observacao: {getattr(s, 'observacao', 'N/A')}")
        print(f"  Tipo Custodia: {getattr(s, 'tipo_custodia', 'N/A')}")
        print("-" * 20)

    print("\n--- ENTRADAS (Since 2026-05-15) ---")
    entradas = Entrada.query.filter(
        Entrada.codigo_item == item_code,
        Entrada.data_entrada >= since_date
    ).all()
    for e in entradas:
        print(f"ID: {e.id}, Data: {e.data_entrada}, Qtd: {getattr(e, 'quantidade', 'N/A')}")

    print("\n--- INVENTARIO EVENTOS (Since 2026-05-15) ---")
    eventos = InventarioEvento.query.filter(
        InventarioEvento.codigo_item == item_code,
        InventarioEvento.data_evento >= since_date
    ).all()
    for ev in eventos:
        print(f"ID: {ev.id}, Data: {ev.data_evento}, Tipo: {getattr(ev, 'tipo_evento', 'N/A')}")

    # Try to find devolucao expressa logic
    try:
        from galint_flask.views.inventory import _build_devolucao_expressa_item_payload
        print("\n--- DEVOLUCAO EXPRESSA PAYLOAD ---")
        # Just demonstrating if we can call it or similar
        # payload = _build_devolucao_expressa_item_payload(item_code, matriculas[1])
        # print(payload)
    except ImportError:
        pass

