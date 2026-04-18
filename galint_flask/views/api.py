"""
API endpoints para recursos diversos do sistema GALINT.
"""
from flask import Blueprint, jsonify, request
from ..models import Item
from ..extensions import db
from ..services.legacy_stock_normalizer import resolve_canonical_unit, resolve_packaging_factor

api_bp = Blueprint('api', __name__, url_prefix='/api')



@api_bp.post('/itens/foto/url')
def aplicar_foto_url_api():
    data = request.form if request.form else (request.json or {})
    codigo = (data.get('codigo') or '').strip()
    image_url = (data.get('image_url') or '').strip()
    if not codigo:
        return jsonify({'success': False, 'message': 'Codigo do item nao informado'}), 400
    if not image_url:
        return jsonify({'success': False, 'message': 'URL da imagem nao informada'}), 400

    item = Item.query.get(codigo)
    if not item:
        return jsonify({'success': False, 'message': 'Item nao encontrado'}), 404

    from ..services.item_foto_service import ItemFotoService
    try:
        foto_path = ItemFotoService.download_foto_from_url(image_url, codigo)
        foto_anterior = item.foto_path
        if foto_anterior and foto_anterior != foto_path:
            ItemFotoService.deletar_foto(foto_anterior)
        item.foto_path = foto_path
        db.session.commit()
        return jsonify({'success': True, 'message': 'Foto atualizada', 'foto_path': foto_path})
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    except Exception:
        return jsonify({'success': False, 'message': 'Falha inesperada ao atualizar foto'}), 500

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

    try:
        quantidade_valor = float(quantidade or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'quantidade inválida'}), 400

    canonical_unit = (resolve_canonical_unit(item) or '').strip().lower()
    packaging_factor = float(resolve_packaging_factor(item) or 0.0)
    unidade_base = item.get_unidade_interna_display() or item.unidade
    tipo_embalagem = item.tipo_embalagem_novo or item.tipo_embalagem
    conversion_labels = {
        'un': 'unidades',
        'm': 'metros',
        'kg': 'quilos',
        'l': 'litros',
    }
    quantidade_base = quantidade_valor
    if packaging_factor > 0 and canonical_unit:
        quantidade_base = quantidade_valor * packaging_factor
    
    resultado = {
        'codigo_item': codigo_item,
        'descricao': item.descricao,
        'unidade_base': unidade_base,
        'quantidade_informada': quantidade_valor,
        'quantidade_base': quantidade_base,
        'tipo_embalagem': tipo_embalagem,
        'conversoes': {}
    }

    if canonical_unit and packaging_factor > 0:
        label = conversion_labels.get(canonical_unit, canonical_unit)
        resultado['conversoes'][label] = quantidade_base
        resultado['conversoes']['conteudo_por_embalagem'] = packaging_factor
        if canonical_unit == 'm':
            resultado['conversoes']['centimetros'] = quantidade_base * 100
    
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
