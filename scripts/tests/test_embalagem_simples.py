"""
Teste simples do EmbalagemService.

Testa apenas a lógica de cálculo de embalagens sem usar banco de dados.
"""

import sys
import os

# Configurar Flask app
os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('GALINT_TELEGRAM_POLLING', 'false')
os.environ.setdefault('GALINT_DISABLE_BACKGROUND_SERVICES', 'true')

# Mock simples de Item
class MockItem:
    def __init__(self):
        self.tipo_embalagem_novo = 'caixa'
        self.unidades_por_embalagem = 500
        self.estoque_embalagens = 0
        self.estoque_unidades_soltas = 0
        self.unidade = 'un'
        self.descricao = 'PREGOS 2 1/2 POLEGADAS'
    
    def get_nome_embalagem(self):
        """Retorna nome da embalagem no singular."""
        return self.tipo_embalagem_novo
    
    def get_nome_embalagem_plural(self):
        """Retorna nome da embalagem no plural."""
        return self.tipo_embalagem_novo + 's'

from galint_flask.services.embalagem_service import EmbalagemService

def test_embalagem_service():
    print("\n" + "="*80)
    print("TESTE DO EMBALAGEM SERVICE")
    print("="*80 + "\n")
    
    item = MockItem()
    print(f"Item: {item.descricao}")
    print(f"Embalagem: {item.tipo_embalagem_novo} ({item.unidades_por_embalagem} unidades)")
    print(f"Estoque inicial: {EmbalagemService.formatar_estoque(item)}\n")
    
    # Teste 1: Entrada de 10 caixas
    print("1️⃣  Entrada de 10 caixas...")
    emb, soltas = EmbalagemService.processar_entrada(item, quantidade=10, em_embalagens=True)
    item.estoque_embalagens = emb
    item.estoque_unidades_soltas = soltas
    print(f"✅ Estoque: {EmbalagemService.formatar_estoque(item)}")
    print(f"   Embalagens: {item.estoque_embalagens}, Soltas: {item.estoque_unidades_soltas}")
    print(f"   Total: {EmbalagemService.calcular_estoque_total(item)} unidades\n")
    
    assert item.estoque_embalagens == 10
    assert item.estoque_unidades_soltas == 0
    
    # Teste 2: Entrada de 250 unidades soltas
    print("2️⃣  Entrada de 250 unidades soltas...")
    emb, soltas = EmbalagemService.processar_entrada(item, quantidade=250, em_embalagens=False)
    item.estoque_embalagens = emb
    item.estoque_unidades_soltas = soltas
    print(f"✅ Estoque: {EmbalagemService.formatar_estoque(item)}")
    print(f"   Embalagens: {item.estoque_embalagens}, Soltas: {item.estoque_unidades_soltas}")
    print(f"   Total: {EmbalagemService.calcular_estoque_total(item)} unidades\n")
    
    assert item.estoque_embalagens == 10
    assert item.estoque_unidades_soltas == 250
    
    # Teste 3: Entrada de mais 250 unidades soltas (deve fechar 1 caixa)
    print("3️⃣  Entrada de mais 250 unidades soltas (deve fechar 1 caixa)...")
    emb, soltas = EmbalagemService.processar_entrada(item, quantidade=250, em_embalagens=False)
    item.estoque_embalagens = emb
    item.estoque_unidades_soltas = soltas
    print(f"✅ Estoque: {EmbalagemService.formatar_estoque(item)}")
    print(f"   Embalagens: {item.estoque_embalagens}, Soltas: {item.estoque_unidades_soltas}")
    print(f"   Total: {EmbalagemService.calcular_estoque_total(item)} unidades\n")
    
    assert item.estoque_embalagens == 11
    assert item.estoque_unidades_soltas == 0
    print("✅ Sistema fechou 1 caixa automaticamente!\n")
    
    # Teste 4: Saída de 36 unidades (deve abrir 1 caixa)
    print("4️⃣  Saída de 36 unidades (deve abrir 1 caixa)...")
    emb, soltas, sucesso = EmbalagemService.processar_saida(item, quantidade=36, em_embalagens=False)
    item.estoque_embalagens = emb
    item.estoque_unidades_soltas = soltas
    print(f"✅ Estoque: {EmbalagemService.formatar_estoque(item)}")
    print(f"   Embalagens: {item.estoque_embalagens}, Soltas: {item.estoque_unidades_soltas}")
    print(f"   Total: {EmbalagemService.calcular_estoque_total(item)} unidades\n")
    
    assert item.estoque_embalagens == 10
    assert item.estoque_unidades_soltas == 464
    print("✅ Sistema abriu 1 caixa automaticamente!\n")
    
    # Teste 5: Saída de 2 caixas
    print("5️⃣  Saída de 2 caixas...")
    emb, soltas, sucesso = EmbalagemService.processar_saida(item, quantidade=2, em_embalagens=True)
    item.estoque_embalagens = emb
    item.estoque_unidades_soltas = soltas
    print(f"✅ Estoque: {EmbalagemService.formatar_estoque(item)}")
    print(f"   Embalagens: {item.estoque_embalagens}, Soltas: {item.estoque_unidades_soltas}")
    print(f"   Total: {EmbalagemService.calcular_estoque_total(item)} unidades\n")
    
    assert item.estoque_embalagens == 8
    assert item.estoque_unidades_soltas == 464
    
    # Teste 6: Devolução de 1 caixa
    print("6️⃣  Devolução de 1 caixa...")
    emb, soltas = EmbalagemService.processar_devolucao(item, quantidade=1, em_embalagens=True)
    item.estoque_embalagens = emb
    item.estoque_unidades_soltas = soltas
    print(f"✅ Estoque: {EmbalagemService.formatar_estoque(item)}")
    print(f"   Embalagens: {item.estoque_embalagens}, Soltas: {item.estoque_unidades_soltas}")
    print(f"   Total: {EmbalagemService.calcular_estoque_total(item)} unidades\n")
    
    assert item.estoque_embalagens == 9
    assert item.estoque_unidades_soltas == 464
    
    # Teste 7: Verificar formato de exibição
    print("7️⃣  Teste de formatação...")
    item2 = MockItem()
    item2.estoque_embalagens = 19
    item2.estoque_unidades_soltas = 464
    formato = EmbalagemService.formatar_estoque(item2)
    print(f"✅ Formato: '{formato}'")
    assert formato == "19 caixas + 464 unidades"
    
    item3 = MockItem()
    item3.estoque_embalagens = 1
    item3.estoque_unidades_soltas = 0
    formato = EmbalagemService.formatar_estoque(item3)
    print(f"✅ Formato singular: '{formato}'")
    assert formato == "1 caixa"
    
    item4 = MockItem()
    item4.estoque_embalagens = 0
    item4.estoque_unidades_soltas = 50
    formato = EmbalagemService.formatar_estoque(item4)
    print(f"✅ Formato só unidades: '{formato}'")
    assert formato == "50 unidades"
    
    print("\n" + "="*80)
    print("✅ TODOS OS TESTES PASSARAM COM SUCESSO!")
    print("="*80 + "\n")
    return True

if __name__ == '__main__':
    try:
        success = test_embalagem_service()
        sys.exit(0 if success else 1)
    except AssertionError as e:
        print(f"\n❌ TESTE FALHOU: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
