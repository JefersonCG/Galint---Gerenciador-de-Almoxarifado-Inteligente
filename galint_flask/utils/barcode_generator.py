"""
Gerador de código de barras para itens do inventário.
Utiliza o formato Code128 e salva como PNG.
"""
import os
from pathlib import Path
from typing import Optional
import barcode
from barcode.writer import ImageWriter
from PIL import Image


# Diretório onde os códigos de barras serão salvos
BARCODE_DIR = Path('instance/barcodes')


def generate_barcode(codigo_item: str, item_titulo: Optional[str] = None) -> str:
    """
    Gera um código de barras Code128 para um item e salva como PNG.
    
    Args:
        codigo_item: Código único do item (ex: 'ITEM-001')
        item_titulo: Título do item para exibir abaixo do código (opcional)
        
    Returns:
        Caminho relativo do arquivo PNG gerado (ex: 'instance/barcodes/ITEM-001.png')
        
    Raises:
        ValueError: Se codigo_item for vazio ou inválido
        
    Example:
        >>> generate_barcode('ITEM-001', 'Parafuso M8')
        'instance/barcodes/ITEM-001.png'
    """
    if not codigo_item or not isinstance(codigo_item, str):
        raise ValueError('codigo_item deve ser uma string não vazia')
    
    # Criar diretório se não existir
    BARCODE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Sanitizar nome do arquivo (remover caracteres inválidos)
    filename_safe = codigo_item.replace('/', '-').replace('\\', '-')
    output_path = BARCODE_DIR / filename_safe
    
    try:
        # Gerar código de barras Code128
        code128 = barcode.get('code128', codigo_item, writer=ImageWriter())
        
        # Opções de renderização
        options = {
            'module_width': 0.3,  # Largura das barras (mm)
            'module_height': 10.0,  # Altura das barras (mm)
            'quiet_zone': 6.5,  # Margem ao redor (mm)
            'font_size': 10,  # Tamanho da fonte do texto
            'text_distance': 3.0,  # Distância entre barras e texto (mm)
            'background': 'white',
            'foreground': 'black',
        }
        
        # Se tem título, adicionar como texto adicional
        if item_titulo:
            # Truncar título se for muito longo
            if len(item_titulo) > 50:
                item_titulo = item_titulo[:47] + '...'
            options['text'] = f'{codigo_item}\n{item_titulo}'
        
        # Salvar como PNG
        full_path = code128.save(str(output_path), options=options)
        
        # Retornar caminho relativo (normalizado)
        relative_path = os.path.join('instance', 'barcodes', f'{filename_safe}.png')
        
        return relative_path
        
    except Exception as e:
        raise RuntimeError(f'Erro ao gerar código de barras: {str(e)}')


def get_barcode_path(codigo_item: str) -> Optional[str]:
    """
    Retorna o caminho do código de barras se ele existir.
    
    Args:
        codigo_item: Código único do item
        
    Returns:
        Caminho relativo do PNG, ou None se não existir
        
    Example:
        >>> get_barcode_path('ITEM-001')
        'instance/barcodes/ITEM-001.png'
    """
    if not codigo_item:
        return None
    
    filename_safe = codigo_item.replace('/', '-').replace('\\', '-')
    barcode_file = BARCODE_DIR / f'{filename_safe}.png'
    
    if barcode_file.exists():
        return os.path.join('instance', 'barcodes', f'{filename_safe}.png')
    
    return None


def delete_barcode(codigo_item: str) -> bool:
    """
    Remove o arquivo de código de barras de um item.
    
    Args:
        codigo_item: Código único do item
        
    Returns:
        True se removido com sucesso, False se não existia
        
    Example:
        >>> delete_barcode('ITEM-001')
        True
    """
    barcode_path = get_barcode_path(codigo_item)
    if barcode_path:
        try:
            Path(barcode_path).unlink()
            return True
        except Exception:
            return False
    return False


def regenerate_all_barcodes(items: list) -> dict:
    """
    Regenera códigos de barras para múltiplos itens.
    
    Args:
        items: Lista de dicts com 'codigo_item' e 'titulo'
        
    Returns:
        Dict com estatísticas: {'success': int, 'failed': int, 'errors': list}
        
    Example:
        >>> items = [
        ...     {'codigo_item': 'ITEM-001', 'titulo': 'Parafuso'},
        ...     {'codigo_item': 'ITEM-002', 'titulo': 'Porca'}
        ... ]
        >>> regenerate_all_barcodes(items)
        {'success': 2, 'failed': 0, 'errors': []}
    """
    stats = {
        'success': 0,
        'failed': 0,
        'errors': []
    }
    
    for item in items:
        try:
            codigo = item.get('codigo_item')
            titulo = item.get('titulo')
            
            if not codigo:
                stats['failed'] += 1
                stats['errors'].append('Item sem codigo_item')
                continue
            
            generate_barcode(codigo, titulo)
            stats['success'] += 1
            
        except Exception as e:
            stats['failed'] += 1
            stats['errors'].append(f'{item.get("codigo_item", "?")} - {str(e)}')
    
    return stats
