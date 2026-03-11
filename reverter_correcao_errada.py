"""Reverter correção ERRADA e restaurar valores corretos."""
import sys
import os

sys.path.insert(0, os.getcwd())

from app import app
from galint_flask.extensions import db
from galint_flask.models import Item

if __name__ == "__main__":
    with app.app_context():
        item = Item.query.filter_by(codigo_item="7891323113965").first()
        
        if not item:
            print("❌ Item não encontrado!")
            sys.exit(1)
        
        print("="*80)
        print("REVERTENDO CORRECAO ERRADA DA TINTA METALEX")
        print("="*80)
        
        print(f"\nESTADO ATUAL (ERRADO POR MINHA CULPA):")
        print(f"  - estoque_embalagens: {item.estoque_embalagens}")
        print(f"  - estoque_unidades_soltas: {item.estoque_unidades_soltas}")
        print(f"  - get_saldo_atual(): {item.get_saldo_atual()}")
        
        # RESTAURAR OS VALORES CORRETOS!
        item.estoque_embalagens = 2.0   # 2 latas fechadas
        item.estoque_unidades_soltas = 16.0  # 16 litros soltos
        
        db.session.commit()
        
        print(f"\nVALORES CORRETOS RESTAURADOS:")
        print(f"  - estoque_embalagens: {item.estoque_embalagens} (2 latas)")
        print(f"  - estoque_unidades_soltas: {item.estoque_unidades_soltas} (16 litros)")
        print(f"  - Total: (2 x 18) + 16 = 52 litros")
        
        from galint_flask.services.embalagem_service import EmbalagemService
        print(f"  - Formatacao: {EmbalagemService.formatar_estoque(item)}")
        
        print("\n" + "="*80)
        print("VALORES CORRETOS RESTAURADOS!")
        print("="*80)
        print("\nPROBLEMA REAL: O sistema mostra 'Saldo atual: 52 Lata'")
        print("   quando deveria mostrar '52 litros' ou similar!")
