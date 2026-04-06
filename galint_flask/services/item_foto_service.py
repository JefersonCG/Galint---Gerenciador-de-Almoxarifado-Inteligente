"""Serviço para gerenciamento de fotos de itens."""
from __future__ import annotations

from datetime import datetime
import ipaddress
import socket
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from flask import current_app
from PIL import Image, ImageOps
import requests
from urllib.parse import urlparse
from werkzeug.utils import secure_filename

if TYPE_CHECKING:
    from werkzeug.datastructures import FileStorage


class ItemFotoService:
    """Serviço para upload e gerenciamento de fotos de itens."""

    EXTENSOES_PERMITIDAS = {'png', 'jpg', 'jpeg', 'jpe', 'webp', 'gif'}
    TAMANHO_MAXIMO_MB = 5
    FOTO_MAX_LADO = 800
    FOTO_QUALIDADE_BASE = 60
    FOTO_QUALIDADE_MIN = 35
    FOTO_MAX_KB = 200
    DOWNLOAD_MAX_MB = 6
    DOWNLOAD_TIMEOUT = 10

    @staticmethod
    def _is_private_host(hostname: str) -> bool:
        if not hostname:
            return True
        host = hostname.strip().lower()
        if host in {"localhost", "127.0.0.1", "::1"}:
            return True
        try:
            ip_str = socket.gethostbyname(host)
            ip = ipaddress.ip_address(ip_str)
            return bool(ip.is_private or ip.is_loopback or ip.is_link_local)
        except Exception:
            return True

    @staticmethod
    def _ensure_url_safe(image_url: str) -> None:
        parsed = urlparse(image_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("URL inválida. Use http ou https.")
        if not parsed.netloc or ItemFotoService._is_private_host(parsed.hostname or ""):
            raise ValueError("URL bloqueada por segurança. Use um host público.")

    @staticmethod
    def _process_image_bytes(raw_bytes: bytes, codigo_item: str) -> str:
        if not raw_bytes:
            raise ValueError("Imagem vazia ou inválida")

        try:
            image = Image.open(BytesIO(raw_bytes))
        except Exception as exc:
            raise ValueError("Arquivo não reconhecido como imagem") from exc

        image = ImageOps.exif_transpose(image)

        max_lado = ItemFotoService.FOTO_MAX_LADO
        if max_lado and max_lado > 0:
            image.thumbnail((max_lado, max_lado), Image.Resampling.LANCZOS)

        has_alpha = image.mode in ("RGBA", "LA", "P")
        if has_alpha:
            image = image.convert("RGBA")
        else:
            image = image.convert("RGB")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        codigo_limpo = secure_filename(codigo_item)
        upload_folder = Path(current_app.root_path) / "static" / "uploads" / "itens"
        upload_folder.mkdir(parents=True, exist_ok=True)
        filename = f"{codigo_limpo}_{timestamp}.webp"
        filepath = upload_folder / filename

        qualidade = ItemFotoService.FOTO_QUALIDADE_BASE
        max_bytes = ItemFotoService.FOTO_MAX_KB * 1024

        while True:
            buffer = BytesIO()
            try:
                image.save(
                    buffer,
                    format="WEBP",
                    quality=qualidade,
                    method=6,
                    optimize=True,
                )
            except Exception:
                buffer = BytesIO()
                image.convert("RGB").save(
                    buffer,
                    format="JPEG",
                    quality=qualidade,
                    optimize=True,
                    progressive=True,
                )
                filename = f"{codigo_limpo}_{timestamp}.jpg"
                filepath = upload_folder / filename

            size = buffer.tell()
            if size <= max_bytes or qualidade <= ItemFotoService.FOTO_QUALIDADE_MIN:
                filepath.write_bytes(buffer.getvalue())
                break
            qualidade -= 10

        return f"uploads/itens/{filepath.name}"

    @staticmethod
    def download_foto_from_url(image_url: str, codigo_item: str) -> str:
        """Baixa imagem de uma URL, comprime e salva no padrão do sistema."""
        if not image_url:
            raise ValueError("URL da imagem não informada")

        ItemFotoService._ensure_url_safe(image_url)

        headers = {"User-Agent": "GALINT/1.0 (+https://galint.local)"}
        try:
            response = requests.get(
                image_url,
                stream=True,
                timeout=ItemFotoService.DOWNLOAD_TIMEOUT,
                headers=headers,
            )
        except Exception as exc:
            raise ValueError("Não foi possível baixar a imagem") from exc

        if response.status_code >= 400:
            raise ValueError(f"Falha ao baixar imagem (HTTP {response.status_code})")

        content_type = (response.headers.get("Content-Type") or "").lower()
        if content_type and not content_type.startswith("image/"):
            raise ValueError("URL não aponta para uma imagem válida")

        max_bytes = int(ItemFotoService.DOWNLOAD_MAX_MB * 1024 * 1024)
        data = BytesIO()
        downloaded = 0
        for chunk in response.iter_content(chunk_size=8192):
            if not chunk:
                continue
            downloaded += len(chunk)
            if downloaded > max_bytes:
                raise ValueError("Imagem muito grande para processamento")
            data.write(chunk)

        return ItemFotoService._process_image_bytes(data.getvalue(), codigo_item)

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
    def duplicar_foto_para_item(foto_path: str, codigo_item: str) -> str:
        """Duplica a foto existente para um novo item, gerando um arquivo independente."""
        if not foto_path:
            raise ValueError("Foto de origem não informada")

        source_path = Path(current_app.root_path) / "static" / str(foto_path)
        if not source_path.exists() or not source_path.is_file():
            raise ValueError("Foto de origem não encontrada")

        raw_bytes = source_path.read_bytes()
        return ItemFotoService._process_image_bytes(raw_bytes, codigo_item)

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
