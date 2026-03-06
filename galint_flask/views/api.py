"""
API endpoints para recursos diversos do sistema GALINT.
"""
from flask import Blueprint, jsonify, request
from ..models import Item
from ..extensions import db

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/calcular-estoque', methods=['POST'])
def calcular_estoque():
    """
    Calcula estoque em diferentes unidades baseado em embalagem (sem conversão por densidade).
    
    Body (JSON):
        - codigo_item: Código do item
        - quantidade: Quantidade atual em estoque
        - unidade_destino: Unidade para converter (opcional)
    
    Returns:
        JSON com cálculos de conversão
    """
    data = request.get_json()
    codigo_item = data.get('codigo_item')
    quantidade = data.get('quantidade', 0)
    
    if not codigo_item:
        return jsonify({'error': 'codigo_item é obrigatório'}), 400
    
    item = Item.query.get(codigo_item)
    if not item:
        return jsonify({'error': 'Item não encontrado'}), 404
    
    resultado = {
        'codigo_item': codigo_item,
        'descricao': item.descricao,
        'unidade_base': item.unidade,
        'quantidade_base': quantidade,
        'tipo_embalagem': item.tipo_embalagem,
        'conversoes': {}
    }
    
    # Conversões por tipo de embalagem (sem Kg↔L por densidade)
    if item.tipo_embalagem == 'Lata':
        # Lata: Unidade → Kg e/ou Litros (se configurado)
        if item.grandeza_referencia:
            resultado['conversoes']['quilos'] = quantidade * (item.grandeza_referencia or 0)
        if item.litros_por_embalagem:
            resultado['conversoes']['litros'] = quantidade * (item.litros_por_embalagem or 0)
        
    elif item.tipo_embalagem == 'Rolo' and item.grandeza_referencia:
        # Rolo: Unidade ↔ M ↔ Cm
        resultado['conversoes']['metros'] = quantidade * item.grandeza_referencia
        resultado['conversoes']['centimetros'] = resultado['conversoes']['metros'] * 100
        
    elif item.tipo_embalagem == 'Pacote' and item.grandeza_referencia:
        # Pacote: Caixa → Pacotes → Unidades
        resultado['conversoes']['unidades'] = quantidade * item.grandeza_referencia
        
    elif item.tipo_embalagem == 'Caixa' and item.grandeza_referencia:
        # Caixa: Caixa → Unidades
        resultado['conversoes']['unidades'] = quantidade * item.grandeza_referencia
    
    return jsonify(resultado)


@api_bp.route('/item/<codigo_item>/barcode', methods=['GET'])
def get_item_barcode(codigo_item):
    """
    Retorna o caminho do código de barras de um item.
    """
    item = Item.query.get(codigo_item)
    if not item:
        return jsonify({'error': 'Item não encontrado'}), 404
    
    return jsonify({
        'codigo_item': codigo_item,
        'barcode_path': item.barcode_image_path,
        'has_barcode': item.barcode_image_path is not None
    })


@api_bp.route('/item/<codigo_item>/lote', methods=['GET'])
def get_item_lote(codigo_item):
    """
    Retorna informações do lote de um item.
    """
    item = Item.query.get(codigo_item)
    if not item:
        return jsonify({'error': 'Item não encontrado'}), 404
    
    return jsonify({
        'codigo_item': codigo_item,
        'lote': item.lote,
        'data_entrada': item.data_entrada.isoformat() if item.data_entrada else None,
        'data_fabricacao': item.data_fabricacao.isoformat() if item.data_fabricacao else None,
        'data_validade': item.data_validade.isoformat() if item.data_validade else None,
    })
