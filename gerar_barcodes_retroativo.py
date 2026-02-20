"""
Script para gerar códigos de barras retroativamente para todos os itens existentes.
Executar apenas uma vez após implementação do sistema de rastreabilidade.
"""
from galint_flask import create_app
from galint_flask.models import Item
from galint_flask.utils.barcode_generator import generate_barcode
from galint_flask.extensions import db

def main():
    app = create_app()
    
    with app.app_context():
        print('='*60)
        print('GERACAO RETROATIVA DE CODIGOS DE BARRAS')
        print('='*60)
        print()
        
        # Buscar todos os itens
        itens = Item.query.all()
        total_itens = len(itens)
        
        print(f'Total de itens encontrados: {total_itens}')
        print()
        
        # Confirmar
        resposta = input('Deseja continuar? (s/n): ')
        if resposta.lower() != 's':
            print('Operacao cancelada.')
            return
        
        print()
        print('Gerando barcodes...')
        print('-'*60)
        
        sucessos = 0
        falhas = 0
        ja_existentes = 0
        erros = []
        
        for idx, item in enumerate(itens, 1):
            try:
                # Verificar se ja tem barcode
                if item.barcode_image_path:
                    ja_existentes += 1
                    print(f'[{idx}/{total_itens}] {item.codigo_item} - JA EXISTE')
                    continue
                
                # Gerar barcode
                barcode_path = generate_barcode(item.codigo_item, item.descricao)
                
                # Atualizar item
                item.barcode_image_path = barcode_path
                db.session.add(item)
                
                sucessos += 1
                print(f'[{idx}/{total_itens}] {item.codigo_item} - OK')
                
                # Commit a cada 10 itens
                if idx % 10 == 0:
                    db.session.commit()
                    print(f'    (Commit executado - {idx} itens processados)')
                
            except Exception as e:
                falhas += 1
                erro_msg = f'{item.codigo_item}: {str(e)}'
                erros.append(erro_msg)
                print(f'[{idx}/{total_itens}] {item.codigo_item} - ERRO: {e}')
        
        # Commit final
        try:
            db.session.commit()
            print()
            print('Commit final executado.')
        except Exception as e:
            print(f'ERRO no commit final: {e}')
            db.session.rollback()
        
        # Resumo
        print()
        print('='*60)
        print('RESUMO')
        print('='*60)
        print(f'Total de itens:       {total_itens}')
        print(f'Barcodes gerados:     {sucessos}')
        print(f'Ja existentes:        {ja_existentes}')
        print(f'Falhas:               {falhas}')
        print()
        
        if erros:
            print('ERROS ENCONTRADOS:')
            for erro in erros[:10]:  # Mostrar primeiros 10 erros
                print(f'  - {erro}')
            if len(erros) > 10:
                print(f'  ... e mais {len(erros) - 10} erros')
        
        print()
        print('='*60)
        
        if falhas == 0:
            print('CONCLUIDO COM SUCESSO!')
        else:
            print(f'CONCLUIDO COM {falhas} ERRO(S)')
        
        print('='*60)

if __name__ == '__main__':
    main()
