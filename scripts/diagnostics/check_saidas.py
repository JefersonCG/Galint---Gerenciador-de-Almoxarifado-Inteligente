"""Script para verificar saídas no banco de dados."""
from galint_flask import create_app
from galint_flask.models import Saida, Item, Usuario
from galint_flask.extensions import db

app = create_app()
with app.app_context():
    print("=" * 60)
    print("VERIFICAÇÃO DE SAÍDAS")
    print("=" * 60)
    
    # Listar alguns itens
    print("\n=== ITENS COM 'BICO' NO NOME ===")
    itens_bico = Item.query.filter(Item.descricao.ilike('%BICO%')).all()
    for item in itens_bico:
        print(f"  Código: {item.codigo_item}")
        print(f"  Descrição: {item.descricao}")
        saidas_item = Saida.query.filter(Saida.codigo_item == item.codigo_item).all()
        print(f"  Total de saídas: {len(saidas_item)}")
        for s in saidas_item[:5]:
            usuario = Usuario.query.get(s.matricula)
            nome_usuario = usuario.nome if usuario else f"[Matrícula: {s.matricula}]"
            print(f"    - Saida {s.id_saida}: {s.quantidade} un, por {nome_usuario}, em {s.data_saida}")
        print()
    
    # Verificar se código é igual
    print("\n=== VERIFICANDO CÓDIGO EXATO ===")
    codigo_teste = "7897637118610"
    item_teste = Item.query.get(codigo_teste)
    if item_teste:
        print(f"Item encontrado pelo código exato: {item_teste.descricao}")
        saidas_teste = Saida.query.filter(Saida.codigo_item == codigo_teste).all()
        print(f"Saídas encontradas: {len(saidas_teste)}")
    else:
        print(f"Item com código {codigo_teste} não encontrado")
    
    # Total geral
    print("\n=== ESTATÍSTICAS GERAIS ===")
    print(f"Total de itens: {Item.query.count()}")
    print(f"Total de saídas: {Saida.query.count()}")
    print(f"Total de usuários: {Usuario.query.count()}")
    
    # Ultimas 10 saídas
    print("\n=== ÚLTIMAS 10 SAÍDAS ===")
    ultimas = Saida.query.order_by(Saida.data_saida.desc()).limit(10).all()
    for s in ultimas:
        item = Item.query.get(s.codigo_item)
        usuario = Usuario.query.get(s.matricula)
        desc = item.descricao[:30] if item else "[Item removido]"
        nome = usuario.nome if usuario else f"[Mat: {s.matricula}]"
        print(f"  {s.data_saida.strftime('%d/%m/%Y %H:%M')} | {desc} | {nome} | Qtd: {s.quantidade}")
