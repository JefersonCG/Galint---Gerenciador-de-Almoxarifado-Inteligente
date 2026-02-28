"""Serviço para gerenciamento de fotos de itens."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from flask import current_app
from werkzeug.utils import secure_filename

if TYPE_CHECKING:
    from werkzeug.datastructures import FileStorage


class ItemFotoService:
    """Serviço para upload e gerenciamento de fotos de itens."""

    EXTENSOES_PERMITIDAS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
    TAMANHO_MAXIMO_MB = 5

    @staticmethod
    def validar_arquivo(file: FileStorage) -> tuple[bool, str]:
        """Valida arquivo de foto.
        
        Returns:
            Tupla (valido, mensagem_erro)
        """
        if not file or not file.filename:
            return False, "Nenhum arquivo foi selecionado"

        filename = secure_filename(file.filename)
        if not filename or '.' not in filename:
            return False, "Nome de arquivo inválido"

        extensao = filename.rsplit('.', 1)[1].lower()
        if extensao not in ItemFotoService.EXTENSOES_PERMITIDAS:
            return False, f"Extensão não permitida. Use: {', '.join(ItemFotoService.EXTENSOES_PERMITIDAS)}"

        # Verificar tamanho (se possível)
        try:
            file.seek(0, 2)  # Mover para o final
            tamanho_bytes = file.tell()
            file.seek(0)  # Voltar ao início
            
            tamanho_mb = tamanho_bytes / (1024 * 1024)
            if tamanho_mb > ItemFotoService.TAMANHO_MAXIMO_MB:
                return False, f"Arquivo muito grande ({tamanho_mb:.1f}MB). Máximo: {ItemFotoService.TAMANHO_MAXIMO_MB}MB"
        except Exception:
            pass  # Se não conseguir verificar tamanho, continua

        return True, ""

    @staticmethod
    def upload_foto(file: FileStorage, codigo_item: str) -> str:
        """Faz upload de foto do item.
        
        Args:
            file: Arquivo de imagem
            codigo_item: Código do item
            
        Returns:
            Caminho relativo da foto (ex: 'uploads/itens/7891040044221_20260228_091530.jpg')
            
        Raises:
            ValueError: Se arquivo for inválido
        """
        # Validar arquivo
        valido, mensagem = ItemFotoService.validar_arquivo(file)
        if not valido:
            raise ValueError(mensagem)

        # Validar nome do arquivo
        if not file.filename:
            raise ValueError("Nome do arquivo não fornecido")

        # Obter extensão
        filename = secure_filename(file.filename)
        extensao = filename.rsplit('.', 1)[1].lower()

        # Gerar nome único
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        codigo_limpo = secure_filename(codigo_item)
        novo_filename = f"{codigo_limpo}_{timestamp}.{extensao}"

        # Criar diretório se não existir
        upload_folder = Path(current_app.root_path) / "static" / "uploads" / "itens"
        upload_folder.mkdir(parents=True, exist_ok=True)

        # Salvar arquivo
        filepath = upload_folder / novo_filename
        file.save(str(filepath))

        # Retornar caminho relativo
        return f"uploads/itens/{novo_filename}"

    @staticmethod
    def deletar_foto(foto_path: str) -> bool:
        """Deleta foto do item.
        
        Args:
            foto_path: Caminho relativo da foto (ex: 'uploads/itens/item_20260228.jpg')
            
        Returns:
            True se deletado com sucesso, False caso contrário
        """
        if not foto_path:
            return False

        try:
            filepath = Path(current_app.root_path) / "static" / foto_path
            if filepath.exists() and filepath.is_file():
                filepath.unlink()
                return True
        except Exception as e:
            current_app.logger.warning(f"Erro ao deletar foto {foto_path}: {e}")

        return False
