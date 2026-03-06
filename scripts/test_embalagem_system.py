"""Script de teste para o sistema de embalagens."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item
from galint_flask.services.embalagem_service import embalagem_service

def test_embalagem_system():
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("TESTE DO SISTEMA DE EMBALAGENS")
        print("=" * 60)
        
        # Criar item de teste
        codigo_teste = "TEST_EMBALAGEM_001"
        
        # Limpar item anterior se existir
        item_antigo = Item.query.get(codigo_teste)
        if item_antigo:
            db.session.delete(item_antigo)
            db.session.commit()
        
        # Criar novo item com embalagens
        item = Item(
            codigo_item=codigo_teste,
            descricao="Pregos 2 polegadas - TESTE",
            unidade="Unidade",
            categoria="Teste",
            setor="Teste",
            tipo_embalagem_novo="caixa",
            unidades_por_embalagem=500,
            estoque_embalagens=20,
            estoque_unidades_soltas=0
        )
        db.session.add(item)
        db.session.commit()
        
        print(f"\n✓ Item criado: {item.descricao}")
        print(f"  Tipo: {item.tipo_embalagem_novo}")
        print(f"  Unidades por embalagem: {item.unidades_por_embalagem}")
        print(f"  Estoque inicial: {item.estoque_embalagens} caixas + {item.estoque_unidades_soltas} unidades")
        print(f"  Total: {embalagem_service.calcular_estoque_total(item):.0f} unidades")
        
        # Teste 1: Saída de 36 unidades
        print("\n" + "=" * 60)
        print("TESTE 1: Saída de 36 unidades")
        print("=" * 60)
        
        novas_emb, novas_soltas, sucesso = embalagem_service.processar_saida(item, 36, em_embalagens=False)
        
        if sucesso:
            print(f"✓ Saída processada com sucesso!")
            print(f"  Antes: {item.estoque_embalagens:.0f} caixas + {item.estoque_unidades_soltas:.0f} unidades")
            item.estoque_embalagens = novas_emb
            item.estoque_unidades_soltas = novas_soltas
            print(f"  Depois: {item.estoque_embalagens:.0f} caixas + {item.estoque_unidades_soltas:.0f} unidades")
            print(f"  Total: {embalagem_service.calcular_estoque_total(item):.0f} unidades")
            print(f"  Formatado: {embalagem_service.formatar_estoque(item)}")
        else:
            print("✗ Falha na saída (estoque insuficiente)")
        
        # Teste 2: Saída de 2 caixas
        print("\n" + "=" * 60)
        print("TESTE 2: Saída de 2 caixas")
        print("=" * 60)
        
        novas_emb, novas_soltas, sucesso = embalagem_service.processar_saida(item, 2, em_embalagens=True)
        
        if sucesso:
            print(f"✓ Saída processada com sucesso!")
            print(f"  Antes: {item.estoque_embalagens:.0f} caixas + {item.estoque_unidades_soltas:.0f} unidades")
            item.estoque_embalagens = novas_emb
            item.estoque_unidades_soltas = novas_soltas
            print(f"  Depois: {item.estoque_embalagens:.0f} caixas + {item.estoque_unidades_soltas:.0f} unidades")
            print(f"  Total: {embalagem_service.calcular_estoque_total(item):.0f} unidades")
            print(f"  Formatado: {embalagem_service.formatar_estoque(item)}")
        else:
            print("✗ Falha na saída (estoque insuficiente)")
        
        # Teste 3: Devolução de 500 unidades (fecha 1 caixa)
        print("\n" + "=" * 60)
        print("TESTE 3: Devolução de 500 unidades")
        print("=" * 60)
        
        novas_emb, novas_soltas = embalagem_service.processar_devolucao(item, 500, em_embalagens=False)
        
        print(f"✓ Devolução processada com sucesso!")
        print(f"  Antes: {item.estoque_embalagens:.0f} caixas + {item.estoque_unidades_soltas:.0f} unidades")
        item.estoque_embalagens = novas_emb
        item.estoque_unidades_soltas = novas_soltas
        print(f"  Depois: {item.estoque_embalagens:.0f} caixas + {item.estoque_unidades_soltas:.0f} unidades")
        print(f"  Total: {embalagem_service.calcular_estoque_total(item):.0f} unidades")
        print(f"  Formatado: {embalagem_service.formatar_estoque(item)}")
        
        # Limpar item de teste
        db.session.delete(item)
        db.session.commit()
        
        print("\n" + "=" * 60)
        print("✅ TODOS OS TESTES PASSARAM!")
        print("=" * 60)

if __name__ == "__main__":
    test_embalagem_system()
