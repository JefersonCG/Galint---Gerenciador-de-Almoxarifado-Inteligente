"""
Script para verificar se existe um item específico no banco de dados.
"""
from app import app
from galint_flask.models import Item

def buscar_item_pano():
    """Busca item com nome 'Pano Microfibra Azul escuro 30x30'"""
    with app.app_context():
        # Buscar exata
        nome_exato = "Pano Microfibra Azul escuro 30x30"
        item_exato = Item.query.filter_by(descricao=nome_exato).first()
        
        if item_exato:
            print("=" * 80)
            print("✓ ITEM ENCONTRADO (correspondência exata):")
            print("=" * 80)
            print(f"Código: {item_exato.codigo_item}")
            print(f"Descrição: {item_exato.descricao}")
            print(f"Categoria: {item_exato.categoria}")
            print(f"Unidade: {item_exato.unidade}")
            print(f"Marca: {item_exato.marca}")
            print(f"Localização: {item_exato.localizacao}")
            print(f"Setor: {item_exato.setor}")
            print(f"Estoque Mínimo: {item_exato.estoque_minimo}")
            print(f"Saldo Atual: {item_exato.get_saldo_atual()}")
            if item_exato.data_entrada:
                print(f"Data de Entrada: {item_exato.data_entrada}")
            print("=" * 80)
            return True
        
        # Buscar similar (case insensitive)
        print("\nBuscando por correspondências similares...")
        itens_similares = Item.query.filter(
            Item.descricao.ilike(f"%pano%microfibra%")
        ).all()
        
        if itens_similares:
            print("\n" + "=" * 80)
            print(f"✓ ENCONTRADO(S) {len(itens_similares)} ITEM(NS) SIMILAR(ES):")
            print("=" * 80)
            for item in itens_similares:
                print(f"\nCódigo: {item.codigo_item}")
                print(f"Descrição: {item.descricao}")
                print(f"Categoria: {item.categoria}")
                print(f"Saldo: {item.get_saldo_atual()}")
                print("-" * 40)
            print("=" * 80)
            return True
        
        # Nada encontrado
        print("\n" + "=" * 80)
        print("✗ NENHUM ITEM ENCONTRADO")
        print("=" * 80)
        print(f"Não foi encontrado nenhum item com descrição '{nome_exato}'")
        print("Também não foram encontrados itens similares contendo 'pano' e 'microfibra'")
        print("=" * 80)
        return False

if __name__ == "__main__":
    buscar_item_pano()
