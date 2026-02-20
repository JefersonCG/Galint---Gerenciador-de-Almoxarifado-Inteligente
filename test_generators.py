"""
Script de teste para os geradores de lote e barcode.
"""
from galint_flask import create_app
from galint_flask.utils.lote_generator import generate_lote, validate_lote, parse_lote_data
from galint_flask.utils.barcode_generator import generate_barcode, get_barcode_path
from datetime import datetime

# Criar contexto da aplicação
app = create_app()

with app.app_context():
    print('=' * 60)
    print('TESTE: Gerador de Lote')
    print('=' * 60)
    
    # Teste 1: Gerar lote com data atual
    lote1 = generate_lote()
    print(f'✅ Lote gerado (data atual): {lote1}')
    print(f'   Válido: {validate_lote(lote1)}')
    print(f'   Data extraída: {parse_lote_data(lote1)}')
    
    # Teste 2: Gerar lote com data específica
    data_teste = datetime(2026, 1, 15)
    lote2 = generate_lote(data_teste)
    print(f'\n✅ Lote gerado (15/01/2026): {lote2}')
    print(f'   Válido: {validate_lote(lote2)}')
    print(f'   Data extraída: {parse_lote_data(lote2)}')
    
    # Teste 3: Gerar mais um lote (deve incrementar)
    lote3 = generate_lote()
    print(f'\n✅ Lote gerado (incremento): {lote3}')
    
    # Teste 4: Validar lote inválido
    lote_invalido = 'INVALID-LOTE'
    print(f'\n❌ Lote inválido: {lote_invalido}')
    print(f'   Válido: {validate_lote(lote_invalido)}')
    
    print('\n' + '=' * 60)
    print('TESTE: Gerador de Barcode')
    print('=' * 60)
    
    # Teste 5: Gerar barcode simples
    try:
        path1 = generate_barcode('TESTE-001', 'Item de Teste')
        print(f'✅ Barcode gerado: {path1}')
        print(f'   Existe: {get_barcode_path("TESTE-001") is not None}')
    except Exception as e:
        print(f'❌ Erro ao gerar barcode: {e}')
    
    # Teste 6: Gerar barcode com título longo
    try:
        titulo_longo = 'Este é um título muito longo que precisa ser truncado para caber no código de barras'
        path2 = generate_barcode('TESTE-002', titulo_longo)
        print(f'\n✅ Barcode com título longo: {path2}')
    except Exception as e:
        print(f'❌ Erro: {e}')
    
    # Teste 7: Verificar barcode que não existe
    path_inexistente = get_barcode_path('ITEM-INEXISTENTE')
    print(f'\n❌ Barcode inexistente: {path_inexistente}')
    
    print('\n' + '=' * 60)
    print('TODOS OS TESTES CONCLUÍDOS!')
    print('=' * 60)
