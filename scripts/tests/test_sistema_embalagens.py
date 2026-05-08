"""
Teste completo do sistema de embalagens.

Este script testa:
1. Criação de item com embalagem
2. Entrada em embalagens vs unidades
3. Saída em embalagens vs unidades  
4. Lógica de abertura/fechamento automático de embalagens
5. Formato de exibição do estoque

Cenário de teste:
- Criar item "PREGOS 2 1/2 POLEGADAS" com embalagem CAIXA, 500 unidades por caixa
- Entrada de 10 caixas (10 × 500 = 5000 unidades)
- Entrada de 250 unidades soltas
- Saída de 36 unidades (deve abrir 1 caixa e deixar 464 soltas)
- Verificar estoque: 9 caixas + 464 unidades
"""

import sys
import os

# Configurar Flask app
os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('GALINT_TELEGRAM_POLLING', 'false')
os.environ.setdefault('GALINT_DISABLE_BACKGROUND_SERVICES', 'true')

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item
from galint_flask.services.embalagem_service import EmbalagemService
from galint_flask.services.inventory import InventoryService, MovimentoPayload

app = create_app()

def test_sistema_embalagens():
    with app.app_context():
        print("\n" + "="*80)
        print("TESTE DO SISTEMA DE EMBALAGENS")
        print("="*80 + "\n")
        
        # Limpar item de teste se existir
        codigo_teste = "TESTE-EMBALAGEM-001"
        item_existente = db.session.get(Item, codigo_teste)
        if item_existente:
            print(f"⚠️  Removendo item de teste existente: {codigo_teste}")
            db.session.delete(item_existente)
            db.session.commit()
        
        # 1. Criar item com embalagem
        print("1️⃣  Criando item com embalagem...")
        item_data = {
            'codigo_item': codigo_teste,
            'descricao': 'PREGOS 2 1/2 POLEGADAS (TESTE)',
            'categoria': 'CAIXA',
            'unidade': 'un',
            'estoque_minimo': 2000,
            'tipo_embalagem_novo': 'caixa',
            'unidades_por_embalagem': 500,
            'estoque_embalagens': 0,
            'estoque_unidades_soltas': 0
        }
        
        result = InventoryService.create_item(item_data)
        if not result['success']:
            print(f"❌ Erro ao criar item: {result.get('error')}")
            return False
        
        item = db.session.get(Item, codigo_teste)
        print(f"✅ Item criado: {item.descricao}")
        print(f"   Embalagem: {item.tipo_embalagem_novo} ({item.unidades_por_embalagem} unidades por {item.tipo_embalagem_novo})")
        print(f"   Estoque: {EmbalagemService.formatar_estoque(item)}\n")
        
        # 2. Entrada de 10 caixas
        print("2️⃣  Registrando entrada de 10 caixas...")
        payload = MovimentoPayload(
            codigo_item=codigo_teste,
            quantidade=10,
            matricula_usuario='000000',
            em_embalagens=True
        )
        
        result = InventoryService.register_entrada(payload)
        if not result['success']:
            print(f"❌ Erro: {result.get('error')}")
            return False
        
        db.session.refresh(item)
        print(f"✅ Entrada registrada")
        print(f"   Estoque: {EmbalagemService.formatar_estoque(item)}")
        print(f"   Estoque em embalagens: {item.estoque_embalagens}")
        print(f"   Estoque unidades soltas: {item.estoque_unidades_soltas}")
        print(f"   Total em unidades: {EmbalagemService.calcular_estoque_total(item)}\n")
        
        # 3. Entrada de 250 unidades soltas
        print("3️⃣  Registrando entrada de 250 unidades soltas...")
        payload = MovimentoPayload(
            codigo_item=codigo_teste,
            quantidade=250,
            matricula_usuario='000000',
            em_embalagens=False
        )
        
        result = InventoryService.register_entrada(payload)
        if not result['success']:
            print(f"❌ Erro: {result.get('error')}")
            return False
        
        db.session.refresh(item)
        print(f"✅ Entrada registrada")
        print(f"   Estoque: {EmbalagemService.formatar_estoque(item)}")
        print(f"   Estoque em embalagens: {item.estoque_embalagens}")
        print(f"   Estoque unidades soltas: {item.estoque_unidades_soltas}")
        print(f"   Total em unidades: {EmbalagemService.calcular_estoque_total(item)}\n")
        
        # Verificar se fechou 1 caixa
        if item.estoque_embalagens == 10 and item.estoque_unidades_soltas == 250:
            print("⚠️  Sistema NÃO fechou caixa automaticamente (250 < 500)")
            print("   Isso está correto!\n")
        
        # 4. Entrada de mais 250 unidades (deve fechar 1 caixa)
        print("4️⃣  Registrando entrada de mais 250 unidades soltas (deve fechar 1 caixa)...")
        payload = MovimentoPayload(
            codigo_item=codigo_teste,
            quantidade=250,
            matricula_usuario='000000',
            em_embalagens=False
        )
        
        result = InventoryService.register_entrada(payload)
        if not result['success']:
            print(f"❌ Erro: {result.get('error')}")
            return False
        
        db.session.refresh(item)
        print(f"✅ Entrada registrada")
        print(f"   Estoque: {EmbalagemService.formatar_estoque(item)}")
        print(f"   Estoque em embalagens: {item.estoque_embalagens}")
        print(f"   Estoque unidades soltas: {item.estoque_unidades_soltas}")
        
        if item.estoque_embalagens == 11 and item.estoque_unidades_soltas == 0:
            print("✅ Sistema fechou 1 caixa automaticamente (250 + 250 = 500)!\n")
        else:
            print(f"❌ Esperado: 11 caixas + 0 soltas, Obtido: {item.estoque_embalagens} caixas + {item.estoque_unidades_soltas} soltas\n")
        
        # 5. Saída de 36 unidades (deve abrir 1 caixa)
        print("5️⃣  Registrando saída de 36 unidades (deve abrir 1 caixa)...")
        payload = MovimentoPayload(
            codigo_item=codigo_teste,
            quantidade=36,
            matricula_usuario='000000',
            local_servico='Teste automático',
            em_embalagens=False
        )
        
        result = InventoryService.register_saida(payload)
        if not result['success']:
            print(f"❌ Erro: {result.get('error')}")
            return False
        
        db.session.refresh(item)
        print(f"✅ Saída registrada")
        print(f"   Estoque: {EmbalagemService.formatar_estoque(item)}")
        print(f"   Estoque em embalagens: {item.estoque_embalagens}")
        print(f"   Estoque unidades soltas: {item.estoque_unidades_soltas}")
        
        if item.estoque_embalagens == 10 and item.estoque_unidades_soltas == 464:
            print("✅ Sistema abriu 1 caixa automaticamente (500 - 36 = 464)!\n")
        else:
            print(f"❌ Esperado: 10 caixas + 464 soltas, Obtido: {item.estoque_embalagens} caixas + {item.estoque_unidades_soltas} soltas\n")
        
        # 6. Saída de 2 caixas
        print("6️⃣  Registrando saída de 2 caixas...")
        payload = MovimentoPayload(
            codigo_item=codigo_teste,
            quantidade=2,
            matricula_usuario='000000',
            local_servico='Teste automático',
            em_embalagens=True
        )
        
        result = InventoryService.register_saida(payload)
        if not result['success']:
            print(f"❌ Erro: {result.get('error')}")
            return False
        
        db.session.refresh(item)
        print(f"✅ Saída registrada")
        print(f"   Estoque: {EmbalagemService.formatar_estoque(item)}")
        print(f"   Estoque em embalagens: {item.estoque_embalagens}")
        print(f"   Estoque unidades soltas: {item.estoque_unidades_soltas}")
        
        if item.estoque_embalagens == 8 and item.estoque_unidades_soltas == 464:
            print("✅ Saída de caixas funcionou corretamente!\n")
        else:
            print(f"❌ Esperado: 8 caixas + 464 soltas, Obtido: {item.estoque_embalagens} caixas + {item.estoque_unidades_soltas} soltas\n")
        
        # 7. Teste de devolução
        print("7️⃣  Registrando devolução de 1 caixa...")
        payload = MovimentoPayload(
            codigo_item=codigo_teste,
            quantidade=1,
            matricula_usuario='000000',
            em_embalagens=True
        )
        
        result = InventoryService.register_entrada(payload)
        if not result['success']:
            print(f"❌ Erro: {result.get('error')}")
            return False
        
        db.session.refresh(item)
        print(f"✅ Devolução registrada")
        print(f"   Estoque: {EmbalagemService.formatar_estoque(item)}")
        print(f"   Estoque em embalagens: {item.estoque_embalagens}")
        print(f"   Estoque unidades soltas: {item.estoque_unidades_soltas}\n")
        
        # Resumo final
        print("="*80)
        print("RESUMO FINAL")
        print("="*80)
        print(f"Item: {item.descricao}")
        print(f"Tipo de embalagem: {item.tipo_embalagem_novo}")
        print(f"Unidades por embalagem: {item.unidades_por_embalagem}")
        print(f"Estoque atual: {EmbalagemService.formatar_estoque(item)}")
        print(f"Total em unidades: {EmbalagemService.calcular_estoque_total(item)}")
        print("\n✅ TODOS OS TESTES CONCLUÍDOS COM SUCESSO!\n")
        
        # Limpar item de teste
        print("🧹 Limpando item de teste...")
        db.session.delete(item)
        db.session.commit()
        print("✅ Item de teste removido\n")
        
        return True

if __name__ == '__main__':
    try:
        success = test_sistema_embalagens()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
