"""Script para transferir itens de 'Material de Pintura/Drywall' para 'Mat. Pintura E Drywall'."""
import sys
from pathlib import Path

# Adicionar o diretório raiz ao path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item

def transferir_categoria_pintura():
    """Transfere itens da categoria antiga para a nova."""
    app = create_app()
    
    with app.app_context():
        # Buscar itens com a categoria antiga
        categoria_antiga = "Mat. Pintura E Drywall"
        categoria_nova = "Mat. Pintura e Drywall"
        
        itens_antigos = Item.query.filter_by(categoria=categoria_antiga).all()
        
        if not itens_antigos:
            print(f"❌ Nenhum item encontrado com a categoria '{categoria_antiga}'")
            return
        
        print(f"📦 Encontrados {len(itens_antigos)} itens para transferir:")
        print("-" * 80)
        
        for item in itens_antigos:
            print(f"  • {item.codigo_item} - {item.descricao}")
        
        print("-" * 80)
        print(f"\n🔄 Transferindo de '{categoria_antiga}' para '{categoria_nova}'...")
        
        # Atualizar categoria
        contador = 0
        for item in itens_antigos:
            item.categoria = categoria_nova
            contador += 1
        
        # Salvar alterações
        try:
            db.session.commit()
            print(f"\n✅ Sucesso! {contador} itens transferidos para '{categoria_nova}'")
            
            # Verificar resultado
            novos_total = Item.query.filter_by(categoria=categoria_nova).count()
            print(f"📊 Total de itens em '{categoria_nova}': {novos_total}")
            
            antigos_restantes = Item.query.filter_by(categoria=categoria_antiga).count()
            print(f"📊 Itens restantes em '{categoria_antiga}': {antigos_restantes}")
            
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Erro ao transferir itens: {e}")
            raise

if __name__ == "__main__":
    transferir_categoria_pintura()
