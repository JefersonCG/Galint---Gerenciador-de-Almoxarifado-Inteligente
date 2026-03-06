"""
Gerador de números de lote para rastreabilidade de itens.
Formato: LOTE-YYYYMMDD-XXXX (onde XXXX é um contador sequencial)
"""
from datetime import datetime
from typing import Optional
from galint_flask.extensions import db
from sqlalchemy import text


def generate_lote(data_entrada: Optional[datetime] = None) -> str:
    """
    Gera um número de lote único no formato LOTE-YYYYMMDD-XXXX.
    
    Args:
        data_entrada: Data de entrada do item. Se None, usa a data atual.
        
    Returns:
        String no formato LOTE-20260131-0001
        
    Example:
        >>> generate_lote()
        'LOTE-20260131-0001'
        >>> generate_lote(datetime(2026, 1, 15))
        'LOTE-20260115-0001'
    """
    if data_entrada is None:
        data_entrada = datetime.now()
    
    # Formatar data como YYYYMMDD
    data_str = data_entrada.strftime('%Y%m%d')
    prefix = f'LOTE-{data_str}-'
    
    # Buscar o maior número sequencial para esta data
    query = text("""
        SELECT lote 
        FROM itens 
        WHERE lote LIKE :prefix 
        ORDER BY lote DESC 
        LIMIT 1
    """)
    
    result = db.session.execute(query, {'prefix': f'{prefix}%'}).fetchone()
    
    if result and result[0]:
        # Extrair o número sequencial do último lote
        ultimo_lote = result[0]
        try:
            ultimo_numero = int(ultimo_lote.split('-')[-1])
            proximo_numero = ultimo_numero + 1
        except (ValueError, IndexError):
            proximo_numero = 1
    else:
        proximo_numero = 1
    
    # Formatar com 4 dígitos
    return f'{prefix}{proximo_numero:04d}'


def validate_lote(lote: str) -> bool:
    """
    Valida se um lote está no formato correto.
    
    Args:
        lote: String do lote a validar
        
    Returns:
        True se válido, False caso contrário
        
    Example:
        >>> validate_lote('LOTE-20260131-0001')
        True
        >>> validate_lote('INVALID')
        False
    """
    if not lote or not isinstance(lote, str):
        return False
    
    parts = lote.split('-')
    if len(parts) != 3:
        return False
    
    if parts[0] != 'LOTE':
        return False
    
    # Validar data (YYYYMMDD)
    try:
        datetime.strptime(parts[1], '%Y%m%d')
    except ValueError:
        return False
    
    # Validar número sequencial (4 dígitos)
    if not parts[2].isdigit() or len(parts[2]) != 4:
        return False
    
    return True


def parse_lote_data(lote: str) -> Optional[datetime]:
    """
    Extrai a data de um número de lote.
    
    Args:
        lote: String do lote no formato LOTE-YYYYMMDD-XXXX
        
    Returns:
        datetime object com a data, ou None se inválido
        
    Example:
        >>> parse_lote_data('LOTE-20260131-0001')
        datetime.datetime(2026, 1, 31, 0, 0)
    """
    if not validate_lote(lote):
        return None
    
    try:
        data_str = lote.split('-')[1]
        return datetime.strptime(data_str, '%Y%m%d')
    except (ValueError, IndexError):
        return None
