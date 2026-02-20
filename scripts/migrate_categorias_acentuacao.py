"""Script para migrar categorias sem acento para versão com acentuação correta."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item

app = create_app()

MAPEAMENTO_CATEGORIAS = {
    'Material Construcao': 'Material Construção',
    'Material Eletrico': 'Material Elétrico',
    'Material Hidraulico': 'Material Hidráulico',
    'Material Descartavel': 'Materiais de Limpeza',
    'Material Descartável': 'Materiais de Limpeza',
}

def migrate_categories():
    """Atualiza categorias sem acento para versão correta."""
    with app.app_context():
        total_updated = 0
        
        for categoria_antiga, categoria_nova in MAPEAMENTO_CATEGORIAS.items():
            itens = Item.query.filter_by(categoria=categoria_antiga).all()
            count = len(itens)
            
            if count > 0:
                print(f'\n📦 Categoria: "{categoria_antiga}" → "{categoria_nova}"')
                print(f'   Itens encontrados: {count}')
                
                for item in itens:
                    item.categoria = categoria_nova
                    # Também atualiza o campo setor (legacy)
                    if item.setor == categoria_antiga:
                        item.setor = categoria_nova
                
                db.session.commit()
                total_updated += count
                print(f'   ✅ {count} itens atualizados!')
            else:
                print(f'\n⚪ Categoria "{categoria_antiga}": Nenhum item encontrado')
        
        print(f'\n{"="*60}')
        print(f'🎉 MIGRAÇÃO CONCLUÍDA!')
        print(f'📊 Total de itens atualizados: {total_updated}')
        print(f'{"="*60}\n')

if __name__ == '__main__':
    migrate_categories()
