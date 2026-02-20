"""
Módulo para processar imagens e extrair códigos de barras via Telegram.
Suporta download de fotos do Telegram e leitura de códigos de barras usando zxing-cpp.
VERSÃO SIMPLIFICADA - Sem pré-processamento OpenCV para evitar conflitos de dependências.
"""
import io
import logging
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

import requests
from PIL import Image, ImageEnhance

logger = logging.getLogger(__name__)

# Lazy import para evitar erros se bibliotecas não estiverem instaladas
_zxing_available = False

try:
    import zxingcpp
    _zxing_available = True
except ImportError:
    logger.warning("zxing-cpp não está instalado. Instale com: pip install zxing-cpp")


class BarcodePhotoProcessor:
    """Processa fotos do Telegram e extrai códigos de barras."""
    
    @staticmethod
    def is_available() -> bool:
        """Verifica se as bibliotecas necessárias estão disponíveis."""
        return _zxing_available
    
    @staticmethod
    def get_missing_libraries() -> list[str]:
        """Retorna lista de bibliotecas faltantes."""
        missing = []
        if not _zxing_available:
            missing.append("zxing-cpp")
        return missing
    
    @staticmethod
    def download_telegram_photo(bot_token: str, file_id: str) -> Optional[bytes]:
        """
        Baixa foto do Telegram usando file_id.
        
        Args:
            bot_token: Token do bot do Telegram
            file_id: ID do arquivo da foto
            
        Returns:
            Bytes da imagem ou None se falhar
        """
        try:
            # Primeiro, obter informações do arquivo
            get_file_url = f"https://api.telegram.org/bot{bot_token}/getFile"
            response = requests.get(get_file_url, params={"file_id": file_id}, timeout=10)
            response.raise_for_status()
            
            file_path = response.json().get("result", {}).get("file_path")
            if not file_path:
                logger.error("file_path não encontrado na resposta do Telegram")
                return None
            
            # Baixar o arquivo
            download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
            download_response = requests.get(download_url, timeout=30)
            download_response.raise_for_status()
            
            return download_response.content
            
        except requests.RequestException as e:
            logger.error(f"Erro ao baixar foto do Telegram: {e}")
            return None
        except Exception as e:
            logger.exception(f"Erro inesperado ao baixar foto: {e}")
            return None
    
    @staticmethod
    def preprocess_image_for_barcode(image: Image.Image) -> Optional[Image.Image]:
        """
        Pré-processa imagem para melhorar leitura de código de barras usando apenas PIL.
        
        Args:
            image: Imagem PIL
            
        Returns:
            Imagem PIL processada ou None se falhar
        """
        try:
            # Converter para grayscale
            gray = image.convert('L')
            
            # Aumentar contraste
            enhancer = ImageEnhance.Contrast(gray)
            enhanced = enhancer.enhance(2.0)
            
            # Aumentar nitidez
            sharpness = ImageEnhance.Sharpness(enhanced)
            sharpened = sharpness.enhance(2.0)
            
            return sharpened
            
        except Exception as e:
            logger.exception(f"Erro ao pré-processar imagem: {e}")
            return None
    
    @staticmethod
    def decode_barcode_from_image(image_bytes: bytes, preprocess: bool = True) -> list[Dict[str, Any]]:
        """
        Decodifica códigos de barras de uma imagem.
        
        Args:
            image_bytes: Bytes da imagem
            preprocess: Se deve aplicar pré-processamento (True por padrão)
            
        Returns:
            Lista de dicionários com informações dos códigos encontrados:
            [
                {
                    "data": "CODIGO-123",
                    "type": "CODE128",
                    "quality": 95,
                    "rect": {"x": 100, "y": 200, "width": 300, "height": 50}
                }
            ]
        """
        if not BarcodePhotoProcessor.is_available():
            logger.error("Bibliotecas necessárias não estão instaladas")
            return []
        
        try:
            # Abrir imagem
            image = Image.open(io.BytesIO(image_bytes))
            
            # Converter para RGB se necessário
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Converter PIL para numpy array (formato que zxing-cpp aceita)
            import numpy as np
            img_array = np.array(image)
            
            results = []
            
            # Tentar decodificar da imagem original
            original_barcodes = zxingcpp.read_barcodes(img_array)
            
            if original_barcodes:
                for barcode in original_barcodes:
                    results.append({
                        "data": barcode.text,
                        "type": barcode.format.name,
                        "quality": 100 if barcode.valid else 0,
                        "rect": {
                            "x": barcode.position.top_left.x,
                            "y": barcode.position.top_left.y,
                            "width": barcode.position.top_right.x - barcode.position.top_left.x,
                            "height": barcode.position.bottom_left.y - barcode.position.top_left.y
                        }
                    })
            
            # Se não encontrou e pré-processamento está habilitado, tentar com imagem processada
            if not results and preprocess:
                processed_img = BarcodePhotoProcessor.preprocess_image_for_barcode(image)
                if processed_img is not None:
                    processed_array = np.array(processed_img)
                    processed_barcodes = zxingcpp.read_barcodes(processed_array)
                    
                    for barcode in processed_barcodes:
                        results.append({
                            "data": barcode.text,
                            "type": barcode.format.name,
                            "quality": 100 if barcode.valid else 0,
                            "rect": {
                                "x": barcode.position.top_left.x,
                                "y": barcode.position.top_left.y,
                                "width": barcode.position.top_right.x - barcode.position.top_left.x,
                                "height": barcode.position.bottom_left.y - barcode.position.top_left.y
                            }
                        })
            
            # Remover duplicatas (mesmo código encontrado em múltiplas tentativas)
            unique_results = []
            seen_codes = set()
            for result in results:
                if result["data"] not in seen_codes:
                    unique_results.append(result)
                    seen_codes.add(result["data"])
            
            return unique_results
            
        except Exception as e:
            logger.exception(f"Erro ao decodificar código de barras: {e}")
            return []
    
    @staticmethod
    def process_telegram_photo(bot_token: str, file_id: str) -> Dict[str, Any]:
        """
        Processa foto do Telegram e extrai código de barras.
        
        Função principal que combina download e decodificação.
        
        Args:
            bot_token: Token do bot do Telegram
            file_id: ID do arquivo da foto
            
        Returns:
            Dicionário com resultado:
            {
                "success": True/False,
                "barcodes": [...],  # Lista de códigos encontrados
                "error": "mensagem"  # Se falhar
            }
        """
        if not BarcodePhotoProcessor.is_available():
            return {
                "success": False,
                "error": f"Bibliotecas necessárias não instaladas: {', '.join(BarcodePhotoProcessor.get_missing_libraries())}",
                "barcodes": []
            }
        
        try:
            # 1. Baixar foto
            image_bytes = BarcodePhotoProcessor.download_telegram_photo(bot_token, file_id)
            if not image_bytes:
                return {
                    "success": False,
                    "error": "Falha ao baixar foto do Telegram",
                    "barcodes": []
                }
            
            # 2. Decodificar código de barras
            barcodes = BarcodePhotoProcessor.decode_barcode_from_image(image_bytes)
            
            if not barcodes:
                return {
                    "success": False,
                    "error": "Nenhum código de barras detectado na imagem",
                    "barcodes": []
                }
            
            return {
                "success": True,
                "barcodes": barcodes,
                "count": len(barcodes)
            }
            
        except Exception as e:
            logger.exception(f"Erro ao processar foto do Telegram: {e}")
            return {
                "success": False,
                "error": f"Erro ao processar imagem: {str(e)}",
                "barcodes": []
            }


# Função de conveniência para uso direto
def scan_barcode_from_telegram(bot_token: str, file_id: str) -> Dict[str, Any]:
    """
    Função de conveniência para escanear código de barras de foto do Telegram.
    
    Args:
        bot_token: Token do bot
        file_id: ID da foto
        
    Returns:
        Resultado do processamento
        
    Example:
        >>> result = scan_barcode_from_telegram(token, file_id)
        >>> if result["success"]:
        >>>     for barcode in result["barcodes"]:
        >>>         print(f"Código: {barcode['data']}")
    """
    return BarcodePhotoProcessor.process_telegram_photo(bot_token, file_id)
