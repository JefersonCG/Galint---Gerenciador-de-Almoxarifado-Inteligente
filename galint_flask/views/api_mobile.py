"""API REST para app mobile - cadastro e consulta via código de barras."""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
import uuid
from datetime import datetime, timedelta
from functools import wraps
from typing import Any

import jwt
from pathlib import Path
from flask import Blueprint, current_app, g, jsonify, request, send_file

# Configurar poppler automaticamente (Windows)
try:
    from galint_flask.poppler_config import configure_poppler_path
    configure_poppler_path()
except Exception:
    pass

from ..services.auth import (
    authenticate,
    create_mobile_token,
    get_mobile_user,
)
from ..services.inventory import inventory_service, MovimentoPayload
from ..services.item_foto_service import ItemFotoService
from ..services.telegram_reports import TelegramReportService
from ..services.telegram_service import TelegramService
from ..utils.time_service import TimeService
from ..extensions import db
from ..models import (
    ApkAuditLog,
    ApkVersion,
    Device,
    DeviceSession,
    Entrada,
    FeatureAssignment,
    FeatureFlag,
    InventarioEvento,
    Item,
    Saida,
    Usuario,
    RetiradaFerramenta,
)

blueprint = Blueprint("api_mobile", __name__, url_prefix="/api/mobile")

logger = logging.getLogger(__name__)


@blueprint.after_request
def flush_withdrawal_notifications(response):
    """Finaliza e envia notificações agrupadas de saídas após cada requisição."""
    try:
        if request.method == "POST" and 200 <= response.status_code < 400:
            TelegramService.flush_pending_withdrawals()
    except Exception:
        pass
    return response


def _convert_pdf_to_jpeg(pdf_path: str, jpeg_path: str, dpi: int = 200) -> None:
    """Converte PDF para JPEG de alta qualidade usando pdf2image + Pillow."""
    try:
        from pdf2image import convert_from_path
        from PIL import Image
    except ImportError as e:
        logger.error(f"Biblioteca necessária não instalada: {e}")
        raise ImportError(
            "Para gerar JPEG, instale: pip install pdf2image pillow\\n"
            "Windows: Também instale poppler (https://github.com/oschwartz10612/poppler-windows/releases)"
        )
    
    try:
        # Converter PDF para lista de imagens (1 imagem por página)
        images = convert_from_path(pdf_path, dpi=dpi)
        
        if len(images) == 1:
            # Apenas 1 página - salvar direto
            images[0].save(jpeg_path, "JPEG", quality=95, optimize=True)
        else:
            # Múltiplas páginas - combinar verticalmente
            total_width = max(img.width for img in images)
            total_height = sum(img.height for img in images)
            
            # Criar imagem grande combinada
            combined = Image.new("RGB", (total_width, total_height), "white")
            y_offset = 0
            for img in images:
                combined.paste(img, (0, y_offset))
                y_offset += img.height
            
            combined.save(jpeg_path, "JPEG", quality=95, optimize=True)
        
        logger.info(f"PDF convertido para JPEG: {jpeg_path}")
    except Exception as e:
        logger.error(f"Erro ao converter PDF para JPEG: {e}")
        raise


LIQUID_PRODUCT_TYPES: list[dict[str, Any]] = [
    {
        "id": "massa_acrilica",
        "label": "Massa Acrílica / Massa Corrida",
        "default_unit": "quilo",
        "keywords": ["massa acrilica", "massa corrida"],
    },
    {
        "id": "tinta_piso_base_agua",
        "label": "Tinta para Piso (base água / acrílica)",
        "default_unit": "litro",
        "keywords": ["tinta piso", "piso acrilica", "piso base agua"],
    },
    {
        "id": "tinta_epoxi_piso",
        "label": "Tinta Epóxi para Piso (bicomp / industrial)",
        "default_unit": "litro",
        "keywords": ["epoxi", "epóxi", "bicomp", "epoxi piso"],
    },
    {
        "id": "tinta_acrilica",
        "label": "Tinta Acrílica (padrão, PVA, semi-brilho, fosca)",
        "default_unit": "litro",
        "keywords": ["tinta acrilica", "tinta pva", "tinta fosca", "tinta semi"],
    },
    {
        "id": "resina_multuso",
        "label": "Resina Multiuso (base água)",
        "default_unit": "litro",
        "keywords": ["resina", "multiuso"],
    },
    {
        "id": "tinta_esmalte",
        "label": "Tinta Esmalte (base solvente)",
        "default_unit": "litro",
        "keywords": ["tinta esmalte", "esmalte"],
    },
    {
        "id": "impermeabilizante",
        "label": "Impermeabilizante (acrílico / borracha líquida)",
        "default_unit": "litro",
        "keywords": ["impermeabilizante", "borracha liquida", "acrilico"],
    },
    {
        "id": "cloro_granulado",
        "label": "Cloro Granulado HTH (hipoclorito de cálcio 65%)",
        "default_unit": "quilo",
        "keywords": ["cloro", "cloro granulado", "hipoclorito", "hth"],
    },
]

LIQUID_PRODUCT_TYPES_BY_ID = {entry["id"]: entry for entry in LIQUID_PRODUCT_TYPES}

_invalidated_tokens: set[str] = set()

LIQUID_PRODUCT_TYPES_BY_ID = {entry["id"]: entry for entry in LIQUID_PRODUCT_TYPES}

_invalidated_tokens: set[str] = set()

def _invalidate_mobile_token(token: str) -> None:
    """Marca um token mobile como inválido."""
    _invalidated_tokens.add(_hash_token(token))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalize_version(value: str | None) -> tuple[int, ...]:
    if not value:
        return tuple()
    parts = [int(p) for p in re.split(r"\D+", value) if p.isdigit()]
    return tuple(parts)


def _is_version_at_least(current: str | None, minimum: str | None) -> bool:
    if not minimum:
        return True
    current_t = _normalize_version(current)
    minimum_t = _normalize_version(minimum)
    if not current_t:
        return False
    max_len = max(len(current_t), len(minimum_t))
    current_t += (0,) * (max_len - len(current_t))
    minimum_t += (0,) * (max_len - len(minimum_t))
    return current_t >= minimum_t


def _get_client_ip() -> str | None:
    return request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr


def _truncate(value: str | None, max_len: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[:max_len]


def _get_or_create_device(payload: dict[str, Any], user: Usuario | None) -> Device | None:
    raw_uuid = (payload.get("device_uuid") or payload.get("deviceId") or "").strip()
    if not raw_uuid:
        return None

    try:
        device_uuid = str(uuid.UUID(raw_uuid))
    except Exception:
        device_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, raw_uuid))

    device = Device.query.filter_by(device_uuid=device_uuid).first()
    if not device:
        device = Device(device_uuid=device_uuid)
        db.session.add(device)

    device.platform = _truncate((payload.get("platform") or device.platform or "android"), 20)
    device.manufacturer = payload.get("manufacturer") or device.manufacturer
    device.model = payload.get("model") or device.model
    device.os_version = payload.get("os_version") or payload.get("osVersion") or device.os_version
    device.apk_version = _truncate(
        payload.get("apk_version") or payload.get("apkVersion") or device.apk_version,
        20,
    )
    device.apk_build_number = payload.get("apk_build_number") or payload.get("apkBuildNumber") or device.apk_build_number
    device.apk_channel = _truncate(
        payload.get("apk_channel") or payload.get("apkChannel") or device.apk_channel or "production",
        20,
    )
    device.last_heartbeat_at = datetime.utcnow()
    device.last_ip_address = _get_client_ip()
    if user:
        device.current_user_id = user.matricula
    if device.status is None:
        device.status = "active"
    device.status = _truncate(device.status, 20)
    return device


def _normalize_text(value: str | None) -> str:
    value = (value or "").strip().lower()
    if not value:
        return ""
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _infer_unidade(unidade: str | None) -> str:
    normalized = _normalize_text(unidade)
    if not normalized:
        return ""
    if re.search(r"\b(litro|litros|lt|lts)\b", normalized):
        return "litro"
    if re.search(r"\b(kg|quilo|quilos)\b", normalized):
        return "quilo"
    return normalized


def _is_developer(user) -> bool:
    """Verifica se o usuário é desenvolvedor (permissões totais)."""
    if not user:
        return False
    cargo = (getattr(user, "cargo", "") or "").strip().lower()
    return "desenvolvedor" in cargo


def _is_admin_or_manager(user) -> bool:
    if not user:
        return False
    if _is_developer(user):
        return True
    if bool(getattr(user, "is_admin", False)) or str(getattr(user, "is_admin", "")).strip() == "1":
        return True
    cargo = (getattr(user, "cargo", "") or "").strip().lower()
    return "gerente" in cargo


def _is_supervisor(user) -> bool:
    if not user:
        return False
    setor = (getattr(user, "setor", "") or "").strip().lower()
    cargo = (getattr(user, "cargo", "") or "").strip().lower()
    return "supervisor" in setor or "supervisor" in cargo


def _is_admin_or_supervisor(user) -> bool:
    return _is_developer(user) or _is_admin_flag(user) or _is_supervisor(user)


def _is_admin_flag(user) -> bool:
    if not user:
        return False
    if _is_developer(user):
        return True
    value = getattr(user, "is_admin", 0)
    if isinstance(value, str):
        return value.strip() in ("1", "true", "True", "TRUE")
    return bool(value)


def mobile_login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Suporte para token via header (preferencial) ou query parameter (para testes)
        auth_header = request.headers.get("Authorization", "")
        token = None
        
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            logger.debug(f"Token via header: {token[:20]}...")
        else:
            # Fallback: token via query parameter (útil para testes no navegador)
            token = request.args.get("token", "").strip()
            if token:
                logger.debug(f"Token via query param: {token[:20]}...")
            else:
                logger.warning("Token não encontrado nem em header nem em query parameter")
        
        if not token:
            return jsonify({"error": "Token de autenticação ausente. Use header 'Authorization: Bearer <token>' ou query param '?token=<token>'"}), 401
        
        # Verificar se token foi invalidado
        if _hash_token(token) in _invalidated_tokens:
            return jsonify({"error": "Sessão inválida. Faça login novamente."}), 401
        
        user = None

        # 1) Preferir JWT (token atual do APK)
        try:
            secret = current_app.config.get("SECRET_KEY") or current_app.secret_key
            payload = jwt.decode(token, secret, algorithms=["HS256"])
            matricula = (payload or {}).get("matricula")
            if matricula:
                user = Usuario.query.get(matricula)
        except Exception as e:
            logger.debug(f"Erro ao decodificar JWT: {e}")
            user = None

        # 2) Fallback: token legado (itsdangerous)
        if not user:
            user = get_mobile_user(token)

        if not user:
            return jsonify({"error": "Token inválido ou expirado. Faça login novamente."}), 401
        g.mobile_user = user
        return func(*args, **kwargs)
    return wrapper


def token_required(func):
    """Compatibilidade com o guia: autenticação via JWT (Bearer).

    Mantém fallback para token antigo (itsdangerous) já usado pelo app.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "message": "Token de autenticação ausente"}), 401

        token = auth_header.split(" ", 1)[1].strip()
        current_user = None

        # 1) Tentar JWT conforme o guia
        try:
            payload = jwt.decode(
                token,
                current_app.config.get("SECRET_KEY"),
                algorithms=["HS256"],
            )
            matricula = (payload or {}).get("matricula")
            if matricula:
                current_user = Usuario.query.get(matricula)
        except Exception:
            current_user = None

        # 2) Fallback: token simples legado
        if not current_user:
            current_user = get_mobile_user(token)

        if not current_user:
            return jsonify({"success": False, "message": "Token inválido ou expirado. Faça login novamente."}), 401

        g.mobile_user = current_user
        return func(current_user, *args, **kwargs)

    return wrapper


@blueprint.post("/login")
def mobile_login():
    """Autentica usuário por matrícula OU nome (guia de replicação APK)."""
    try:
        data = request.get_json() or {}
        matricula_ou_nome = str(data.get("matricula", "")).strip()
        senha = str(data.get("senha", "")).strip()

        if not matricula_ou_nome or not senha:
            return jsonify({
                "success": False,
                "message": "Matrícula/Nome e senha são obrigatórios",
            }), 400

        # Buscar por matrícula (numérico) ou por nome (ilike)
        if matricula_ou_nome.isdigit():
            user = Usuario.query.filter_by(matricula=matricula_ou_nome).first()
        else:
            users = Usuario.query.filter(
                Usuario.nome.ilike(f"%{matricula_ou_nome}%")
            ).all()

            if len(users) == 0:
                user = None
            elif len(users) == 1:
                user = users[0]
            else:
                return jsonify({
                    "success": False,
                    "ambiguous": True,
                    "message": "Múltiplos usuários encontrados. Seja mais específico ou use a matrícula.",
                    "matches": [
                        {"matricula": u.matricula, "nome": u.nome}
                        for u in users[:10]
                    ],
                }), 400

        if not user:
            return jsonify({
                "success": False,
                "message": "Usuário não encontrado",
            }), 404

        # Verificar senha
        if not user.check_password(senha):
            # Compatibilidade: alguns ambientes usam authenticate() para login de sessão
            if not authenticate(user.matricula, senha):
                return jsonify({
                    "success": False,
                    "message": "Senha incorreta",
                }), 401

        # Invalidar sessão mobile anterior da mesma matrícula
        if user.active_session_id and user.active_session_id.startswith('mobile:'):
            logger.info(f"[Mobile] Invalidando sessão mobile anterior de {user.matricula}")
            # Marcar token anterior como inválido
            _invalidate_mobile_token(user.active_session_id.replace('mobile:', '', 1))
        
        # Gerar token JWT
        token = jwt.encode(
            {
                "matricula": user.matricula,
                "exp": datetime.utcnow() + timedelta(days=30),
            },
            current_app.config.get("SECRET_KEY"),
            algorithm="HS256",
        )
        
        # Registrar nova sessão mobile
        user.active_session_id = f"mobile:{token[:32]}"

        # Registrar device + sessão (se houver device_uuid)
        device = _get_or_create_device(data, user)
        if device and device.status == "blocked":
            return jsonify({
                "success": False,
                "message": "Dispositivo bloqueado. Contate o administrador.",
                "blocked": True,
            }), 403

        session_token_hash = _hash_token(token)
        if device:
            db.session.flush()
            session = DeviceSession(
                device_id=device.id,
                user_id=user.matricula,
                session_token_hash=session_token_hash,
                expires_at=datetime.utcnow() + timedelta(days=30),
                ip_address=_get_client_ip(),
                user_agent=request.headers.get("User-Agent"),
                status="active",
            )
            db.session.add(session)

            ApkAuditLog.log_action(
                action_type="login",
                action_result="success",
                user_id=user.matricula,
                device_id=device.id,
                apk_version=device.apk_version,
                ip_address=_get_client_ip(),
            )

        db.session.commit()

        is_admin = _is_admin_flag(user)
        is_manager = _is_admin_or_manager(user) and not is_admin
        return jsonify({
            "success": True,
            "message": "Login realizado com sucesso",
            "data": {
                "token": token,
                "user": {
                    "matricula": user.matricula,
                    "nome": user.nome,
                    "setor": user.setor,
                    "is_admin": is_admin,
                    "cargo": getattr(user, "cargo", None),
                    "is_manager": is_manager,
                },
                "device": {
                    "device_uuid": getattr(device, "device_uuid", None),
                    "status": getattr(device, "status", None),
                    "apk_version": getattr(device, "apk_version", None),
                    "apk_channel": getattr(device, "apk_channel", None),
                }
            },
        }), 200

    except Exception as e:
        logger.exception("Erro no login mobile")
        return jsonify({
            "success": False,
            "message": f"Erro no servidor: {str(e)}",
        }), 500


@blueprint.post("/heartbeat")
@mobile_login_required
def mobile_heartbeat():
    """Atualiza last_heartbeat_at e status do dispositivo."""
    try:
        data = request.get_json() or {}
        user = g.mobile_user
        device = _get_or_create_device(data, user)

        if not device:
            return jsonify({"success": False, "message": "device_uuid é obrigatório"}), 400

        if device.status == "blocked":
            return jsonify({"success": False, "message": "Dispositivo bloqueado"}), 403

        db.session.commit()

        return jsonify({
            "success": True,
            "data": {
                "device_uuid": device.device_uuid,
                "status": device.status,
                "last_heartbeat_at": device.last_heartbeat_at.isoformat() if device.last_heartbeat_at else None,
            },
        }), 200
    except Exception:
        db.session.rollback()
        logger.exception("Erro no heartbeat mobile")
        return jsonify({"success": False, "message": "Erro interno"}), 500


@blueprint.get("/features")
@mobile_login_required
def mobile_features():
    """Retorna feature flags resolvidas para o device/usuário."""
    user = g.mobile_user
    device_uuid = (request.args.get("device_uuid") or "").strip()
    device = Device.query.filter_by(device_uuid=device_uuid).first() if device_uuid else None

    flags = FeatureFlag.active_query().all()
    flag_ids = [flag.id for flag in flags]
    now = datetime.utcnow()

    assignments_query = FeatureAssignment.query.filter(
        FeatureAssignment.feature_flag_id.in_(flag_ids),
        FeatureAssignment.deleted_at.is_(None),
    ).filter(
        (FeatureAssignment.expires_at.is_(None)) | (FeatureAssignment.expires_at > now)
    )

    assignments = assignments_query.all()

    by_flag: dict[int, list[FeatureAssignment]] = {}
    for assignment in assignments:
        by_flag.setdefault(assignment.feature_flag_id, []).append(assignment)

    resolved: dict[str, Any] = {}
    for flag in flags:
        enabled = bool(flag.is_enabled)
        value = flag.default_value

        candidates = by_flag.get(flag.id, [])

        def match(target_type: str, target_id: str | None):
            if not target_id:
                return None
            for item in candidates:
                if item.target_type == target_type and str(item.target_id) == str(target_id):
                    return item
            return None

        assignment = None
        if device:
            assignment = match("device", str(device.id))
        if not assignment:
            assignment = match("user", user.matricula)
        if not assignment and getattr(user, "cargo", None):
            assignment = match("profile", str(user.cargo))

        if assignment:
            enabled = bool(assignment.is_enabled)
            if assignment.override_value is not None:
                value = assignment.override_value

        if not _is_version_at_least(device.apk_version if device else None, flag.min_app_version):
            enabled = False

        resolved[flag.flag_key] = {
            "enabled": enabled,
            "value": value,
            "requires_app_restart": bool(flag.requires_app_restart),
            "min_app_version": flag.min_app_version,
            "type": flag.flag_type,
        }

    return jsonify({"success": True, "data": resolved}), 200


@blueprint.post("/logout")
@mobile_login_required
def mobile_logout():
    """Logout explícito do app mobile."""
    try:
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.split(" ", 1)[1].strip() if auth_header.startswith("Bearer ") else ""
        token_hash = _hash_token(token) if token else None
        data = request.get_json() or {}
        device_uuid = (data.get("device_uuid") or "").strip()

        session = None
        if token_hash:
            session = DeviceSession.query.filter_by(session_token_hash=token_hash, status="active").first()

        if session:
            session.status = "logged_out"
            session.logged_out_at = func.now()

        if device_uuid:
            device = Device.query.filter_by(device_uuid=device_uuid).first()
            if device:
                # Limpar sessão ativa do usuário
                if device.current_user_id:
                    user = Usuario.query.get(device.current_user_id)
                    if user and user.active_session_id and user.active_session_id.startswith('mobile:'):
                        user.active_session_id = None
                
                device.current_user_id = None

        ApkAuditLog.log_action(
            action_type="logout",
            action_result="success",
            user_id=g.mobile_user.matricula,
            device_id=session.device_id if session else None,
            ip_address=_get_client_ip(),
        )

        db.session.commit()
        return jsonify({"success": True, "message": "Logout realizado"}), 200
    except Exception:
        db.session.rollback()
        logger.exception("Erro no logout mobile")
        return jsonify({"success": False, "message": "Erro interno"}), 500


@blueprint.get("/itens/<codigo>")
@token_required
def buscar_item_por_codigo(current_user: Usuario, codigo: str):
    """Busca item por código (alias para fluxo de retirada do guia)."""
    codigo = (codigo or "").strip()
    if not codigo:
        return jsonify({"success": False, "message": "Código não fornecido"}), 400

    item = Item.query.filter(
        (Item.codigo_item == codigo)
    ).first()

    if not item:
        return jsonify({"success": False, "message": "Item não encontrado"}), 404

    return jsonify({
        "success": True,
        "data": {
            "id": item.codigo_item,
            "codigo_barras": item.codigo_item,
            "descricao": item.descricao,
            "categoria": item.categoria,
            "localizacao": item.localizacao,
            "marca": item.marca,
            "quantidade": round(float(item.get_saldo_atual() or 0), 6),
            "unidade": item.unidade,
            "estoque_minimo": item.estoque_minimo,
        },
    }), 200


@blueprint.get("/itens/<codigo>/ultima_retirada")
@token_required
def buscar_ultima_retirada(current_user: Usuario, codigo: str):
    """Busca informações do último responsável que retirou o item."""
    codigo = (codigo or "").strip()
    if not codigo:
        return jsonify({"success": False, "message": "Código não fornecido"}), 400

    # Buscar a última saída deste item
    ultima_saida = (
        db.session.query(Saida)
        .filter(Saida.codigo_item == codigo)
        .order_by(Saida.data_saida.desc())
        .first()
    )

    if not ultima_saida:
        return jsonify({
            "success": True,
            "data": None,
            "message": "Nenhuma retirada encontrada para este item",
        }), 200

    # Buscar informações do usuário que retirou
    usuario = Usuario.query.filter_by(id=ultima_saida.matricula).first()

    if not usuario:
        return jsonify({
            "success": True,
            "data": {
                "matricula": ultima_saida.matricula,
                "nome": f"Matrícula {ultima_saida.matricula}",
                "data_saida": ultima_saida.data_saida.isoformat(),
                "quantidade": round(float(ultima_saida.quantidade or 0), 6),
                "tipo_custodia": getattr(ultima_saida, "tipo_custodia", None),
            },
        }), 200

    return jsonify({
        "success": True,
        "data": {
            "matricula": usuario.id,
            "nome": usuario.nome or usuario.username,
            "cargo": usuario.cargo,
            "setor": usuario.setor,
            "data_saida": ultima_saida.data_saida.isoformat(),
            "quantidade": round(float(ultima_saida.quantidade or 0), 6),
            "tipo_custodia": getattr(ultima_saida, "tipo_custodia", None),
        },
    }), 200


def _normalize_tipo_custodia(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if raw in {"permanente", "perm", "p"}:
        return "permanente"
    if raw in {"temporaria", "temporária", "diaria", "diária", "daily", "d"}:
        return "temporaria"
    return "temporaria"


@blueprint.post("/retirar_multipla")
@token_required
def retirar_multipla_mobile(current_user: Usuario):
    """Registra múltiplas retiradas de material em uma única operação."""
    try:
        data = request.get_json() or {}
        itens = data.get("itens", [])
        local_servico_geral = data.get("local_servico", "")
        observacao_geral = data.get("observacao", "")
        matricula_retirante_raw = data.get("matricula_retirante")
        tipo_custodia_geral = _normalize_tipo_custodia(data.get("tipo_custodia"))

        if not itens or not isinstance(itens, list):
            return jsonify({"success": False, "message": "Lista de itens é obrigatória"}), 400

        # Verificar permissão se for retirada em nome de outro
        matricula_retirante = (matricula_retirante_raw or "").strip()
        retirante_user = None
        if matricula_retirante and matricula_retirante != current_user.matricula:
            if not _is_admin_or_manager(current_user):
                return jsonify({
                    "success": False,
                    "message": "Apenas administrador/gerente pode registrar retirada em nome de outro usuário.",
                }), 403
            retirante_user = Usuario.query.filter_by(matricula=matricula_retirante).first()
            if not retirante_user:
                return jsonify({"success": False, "message": "Usuário (retirante) não encontrado."}), 400
        else:
            retirante_user = current_user

        saidas_criadas = []
        resultados = []

        # Processar cada item
        for idx, item_data in enumerate(itens, 1):
            codigo = item_data.get("codigo")
            quantidade = item_data.get("quantidade")
            observacao_item = item_data.get("observacao", "")
            tipo_custodia_item = _normalize_tipo_custodia(item_data.get("tipo_custodia") or tipo_custodia_geral)

            if not codigo:
                resultados.append({"index": idx, "success": False, "message": "Código não informado"})
                continue

            try:
                quantidade_int = int(quantidade)
                if quantidade_int <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                resultados.append({"index": idx, "codigo": codigo, "success": False, "message": "Quantidade inválida"})
                continue

            item = Item.query.filter((Item.codigo_item == str(codigo).strip())).first()
            if not item:
                resultados.append({"index": idx, "codigo": codigo, "success": False, "message": "Item não encontrado"})
                continue

            try:
                saldo_atual = float(item.get_saldo_atual() or 0)
            except Exception:
                saldo_atual = 0.0

            if saldo_atual < quantidade_int:
                resultados.append({
                    "index": idx,
                    "codigo": codigo,
                    "success": False,
                    "message": f"Saldo insuficiente. Disponível: {int(saldo_atual)}"
                })
                continue

            # Criar saída
            saida = Saida()
            saida.codigo_item = item.codigo_item
            saida.quantidade = quantidade_int
            saida.matricula = retirante_user.matricula
            saida.data_saida = datetime.utcnow()
            
            obs_final = observacao_item or observacao_geral
            saida.observacao = str(obs_final or "").upper()
            saida.local_servico = str(local_servico_geral or "").upper()
            if hasattr(saida, "tipo_custodia"):
                saida.tipo_custodia = tipo_custodia_item

            db.session.add(saida)
            # Se for ferramenta, também criar registro em retiradas_ferramentas (apenas custódia diária)
            try:
                categoria_text = (item.categoria or '').lower()
                if 'ferrament' in categoria_text and tipo_custodia_item != "permanente":
                    # VALIDAÇÃO CRÍTICA: Verificar se há saldo disponível para ferramentas
                    from sqlalchemy import func
                    quantidade_em_uso = db.session.query(
                        func.coalesce(func.sum(RetiradaFerramenta.quantidade), 0)
                    ).filter(
                        RetiradaFerramenta.codigo_item == item.codigo_item,
                        RetiradaFerramenta.status == 'em_uso'
                    ).scalar() or 0
                    
                    saldo_disponivel_ferramenta = saldo_atual - quantidade_em_uso
                    
                    if saldo_disponivel_ferramenta < quantidade_int:
                        resultados.append({
                            "index": idx,
                            "codigo": codigo,
                            "success": False,
                            "message": f"Ferramenta indisponível. {int(quantidade_em_uso)} em uso por outro(s) funcionário(s)"
                        })
                        continue  # Pula este item
                    
                    retirada = RetiradaFerramenta(
                        codigo_item=item.codigo_item,
                        matricula=retirante_user.matricula,
                        quantidade=int(quantidade_int or 1),
                        local_servico=str(local_servico_geral or '').upper(),
                        observacao=str(obs_final or '').upper(),
                        status='em_uso',
                    )
                    db.session.add(retirada)
            except Exception as e:
                logger.warning(f"Erro ao criar RetiradaFerramenta para {item.codigo_item}: {e}")
                pass
            saidas_criadas.append(saida)
            resultados.append({
                "index": idx,
                "codigo": codigo,
                "success": True,
                "descricao": item.descricao,
                "quantidade": quantidade_int
            })

        if not saidas_criadas:
            return jsonify({"success": False, "message": "Nenhum item foi processado com sucesso", "resultados": resultados}), 400

        db.session.commit()

        # Notificar via Telegram com mensagem agrupada
        try:
            from ..services.telegram_service import TelegramService
            saida_ids = [s.id_saida for s in saidas_criadas]
            TelegramService.notify_multiple_withdrawal(saida_ids)
        except Exception as e:
            logger.warning(f"Falha ao enviar notificação Telegram: {e}")

        return jsonify({
            "success": True,
            "message": f"{len(saidas_criadas)} item(ns) retirado(s) com sucesso",
            "resultados": resultados
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.exception(f"Erro em retirar_multipla_mobile: {e}")
        return jsonify({"success": False, "message": "Erro interno ao processar retiradas"}), 500


@blueprint.post("/devolver_multipla_ferramentas")
@token_required
def devolver_multipla_ferramentas_mobile(current_user: Usuario):
    """Registra devolução de múltiplas ferramentas em uma única operação."""
    try:
        data = request.get_json() or {}
        itens = data.get("itens", [])  # [{ codigo, quantidade }, ...]
        observacao_geral = data.get("observacao", "")
        matricula_retirante_raw = data.get("matricula")

        if not itens or not isinstance(itens, list):
            return jsonify({"success": False, "message": "Lista de itens é obrigatória"}), 400

        # Verificar permissão se for devolução em nome de outro
        matricula_retirante = (matricula_retirante_raw or "").strip()
        retirante_user = None
        if matricula_retirante and matricula_retirante != current_user.matricula:
            if not _is_admin_or_manager(current_user):
                return jsonify({
                    "success": False,
                    "message": "Apenas administrador/gerente pode registrar devolução em nome de outro usuário.",
                }), 403
            retirante_user = Usuario.query.filter_by(matricula=matricula_retirante).first()
            if not retirante_user:
                return jsonify({"success": False, "message": "Usuário não encontrado."}), 400
        else:
            retirante_user = current_user

        eventos_criados = []
        resultados = []

        # Processar cada item
        for idx, item_data in enumerate(itens, 1):
            codigo = item_data.get("codigo")
            quantidade = item_data.get("quantidade", 1)
            observacao_item = item_data.get("observacao", "")

            if not codigo:
                resultados.append({"index": idx, "success": False, "message": "Código não informado"})
                continue

            try:
                quantidade_int = int(quantidade)
                if quantidade_int <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                resultados.append({"index": idx, "codigo": codigo, "success": False, "message": "Quantidade inválida"})
                continue

            item = Item.query.filter((Item.codigo_item == str(codigo).strip())).first()
            if not item:
                resultados.append({"index": idx, "codigo": codigo, "success": False, "message": "Item não encontrado"})
                continue

            # Verificar se é ferramenta
            categoria_text = (item.categoria or '').lower()
            if 'ferrament' not in categoria_text:
                resultados.append({
                    "index": idx,
                    "codigo": codigo,
                    "success": False,
                    "message": "Item não é uma ferramenta"
                })
                continue

            obs_final = (observacao_item or observacao_geral or "").strip() or None

            evento = InventarioEvento(
                codigo_item=item.codigo_item,
                matricula=retirante_user.matricula,
                quantidade=float(quantidade_int),
                tipo="devolucao_ferramenta",
                descricao=(
                    obs_final
                    or f"Devolução de Ferramenta (mobile múltipla): {item.descricao or 'Item'}"
                ),
                data_evento=datetime.utcnow(),
            )
            db.session.add(evento)

            # Atualizar status de retirada
            try:
                retiradas = RetiradaFerramenta.query.filter(
                    RetiradaFerramenta.codigo_item == item.codigo_item,
                    RetiradaFerramenta.matricula == retirante_user.matricula,
                    RetiradaFerramenta.status == 'em_uso'
                ).order_by(RetiradaFerramenta.data_retirada).limit(quantidade_int).all()

                for retirada in retiradas:
                    retirada.status = 'devolvida'
                    retirada.data_devolucao = datetime.utcnow()
            except Exception:
                pass

            eventos_criados.append(evento)
            resultados.append({
                "index": idx,
                "codigo": codigo,
                "success": True,
                "descricao": item.descricao,
                "quantidade": quantidade_int
            })

        if not eventos_criados:
            return jsonify({
                "success": False,
                "message": "Nenhuma ferramenta foi devolvida",
                "resultados": resultados
            }), 400

        db.session.commit()

        # Notificar via Telegram (opcional)
        try:
            from ..services.telegram_service import TelegramService
            for evento in eventos_criados:
                TelegramService.notify_inventory_event(evento.id_evento)
        except Exception:
            pass

        return jsonify({
            "success": True,
            "message": f"{len(eventos_criados)} ferramenta(s) devolvida(s) com sucesso",
            "resultados": resultados
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.exception(f"Erro em devolver_multipla_ferramentas_mobile: {e}")
        return jsonify({"success": False, "message": "Erro interno ao processar devoluções"}), 500


@blueprint.post("/devolver_multipla_materiais")
@token_required
def devolver_multipla_materiais_mobile(current_user: Usuario):
    """Registra devolução de múltiplos materiais em uma única operação."""
    try:
        data = request.get_json() or {}
        itens = data.get("itens", [])  # [{ codigo, quantidade }, ...]
        observacao_geral = data.get("observacao", "")
        matricula_retirante_raw = data.get("matricula")

        if not itens or not isinstance(itens, list):
            return jsonify({"success": False, "message": "Lista de itens é obrigatória"}), 400

        # Verificar permissão se for devolução em nome de outro
        matricula_retirante = (matricula_retirante_raw or "").strip()
        retirante_user = None
        if matricula_retirante and matricula_retirante != current_user.matricula:
            if not _is_admin_or_manager(current_user):
                return jsonify({
                    "success": False,
                    "message": "Apenas administrador/gerente pode registrar devolução em nome de outro usuário.",
                }), 403
            retirante_user = Usuario.query.filter_by(matricula=matricula_retirante).first()
            if not retirante_user:
                return jsonify({"success": False, "message": "Usuário não encontrado."}), 400
        else:
            retirante_user = current_user

        eventos_criados = []
        resultados = []

        # Processar cada item
        for idx, item_data in enumerate(itens, 1):
            codigo = item_data.get("codigo")
            quantidade = item_data.get("quantidade")
            observacao_item = item_data.get("observacao", "")

            if not codigo:
                resultados.append({"index": idx, "success": False, "message": "Código não informado"})
                continue

            try:
                quantidade_int = int(quantidade)
                if quantidade_int <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                resultados.append({"index": idx, "codigo": codigo, "success": False, "message": "Quantidade inválida"})
                continue

            item = Item.query.filter((Item.codigo_item == str(codigo).strip())).first()
            if not item:
                resultados.append({"index": idx, "codigo": codigo, "success": False, "message": "Item não encontrado"})
                continue

            # Verificar se NÃO é ferramenta
            categoria_text = (item.categoria or '').lower()
            if 'ferrament' in categoria_text:
                resultados.append({
                    "index": idx,
                    "codigo": codigo,
                    "success": False,
                    "message": "Use a API de devolução de ferramentas para este item"
                })
                continue

            obs_final = (observacao_item or observacao_geral or "").strip() or None
            try:
                evento = inventory_service.registrar_devolucao_material(
                    codigo=item.codigo_item,
                    quantidade=quantidade_int,
                    matricula=retirante_user.matricula,
                    observacao=obs_final,
                    commit=False,
                )
                eventos_criados.append(evento)
                resultados.append({
                    "index": idx,
                    "codigo": codigo,
                    "success": True,
                    "descricao": item.descricao,
                    "quantidade": quantidade_int
                })
            except Exception as e:
                resultados.append({
                    "index": idx,
                    "codigo": codigo,
                    "success": False,
                    "message": str(e),
                })

        if not eventos_criados:
            return jsonify({
                "success": False,
                "message": "Nenhum material foi devolvido",
                "resultados": resultados
            }), 400

        db.session.commit()

        # Notificar via Telegram (opcional)
        try:
            from ..services.telegram_service import TelegramService
            for evento in eventos_criados:
                TelegramService.notify_inventory_event(evento.id_evento)
        except Exception:
            pass

        return jsonify({
            "success": True,
            "message": f"{len(eventos_criados)} material(is) devolvido(s) com sucesso",
            "resultados": resultados
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.exception(f"Erro em devolver_multipla_materiais_mobile: {e}")
        return jsonify({"success": False, "message": "Erro interno ao processar devoluções"}), 500


@blueprint.get("/ferramentas_ativas/<matricula>")
@token_required
def listar_ferramentas_ativas_mobile(current_user: Usuario, matricula: str):
    """Lista ferramentas ativas de um funcionário específico."""
    try:
        # Verificar permissão
        if matricula != current_user.matricula and not _is_admin_or_manager(current_user):
            return jsonify({
                "success": False,
                "message": "Sem permissão para visualizar ferramentas de outro usuário"
            }), 403

        # Buscar ferramentas ativas
        retiradas = RetiradaFerramenta.query.filter(
            RetiradaFerramenta.matricula == matricula,
            RetiradaFerramenta.status == 'em_uso'
        ).all()

        ferramentas_data = []
        for retirada in retiradas:
            item = Item.query.filter_by(codigo_item=retirada.codigo_item).first()
            if not item:
                continue

            # Calcular dias em uso
            dias_em_uso = 0
            if retirada.data_retirada:
                dias_em_uso = (datetime.utcnow() - retirada.data_retirada).days

            ferramentas_data.append({
                'codigo_barras': item.codigo_item,
                'descricao': item.descricao,
                'categoria': item.categoria,
                'data_retirada': retirada.data_retirada.isoformat() if retirada.data_retirada else None,
                'dias_em_uso': dias_em_uso,
                'local_servico': retirada.local_servico,
                'observacao': retirada.observacao,
            })

        return jsonify({
            "success": True,
            "data": ferramentas_data
        }), 200

    except Exception as e:
        logger.exception(f"Erro em listar_ferramentas_ativas_mobile: {e}")
        return jsonify({"success": False, "message": "Erro ao buscar ferramentas ativas"}), 500


@blueprint.post("/retirar")
@token_required
def retirar_mobile(current_user: Usuario):
    """Registra retirada de material pelo app mobile (guia de replicação APK)."""
    try:
        data = request.get_json() or {}
        codigo = data.get("codigo")
        quantidade = data.get("quantidade")
        observacao = data.get("observacao", "")
        local_servico = data.get("local_servico", "")
        matricula_retirante_raw = data.get("matricula_retirante")
        tipo_custodia = _normalize_tipo_custodia(data.get("tipo_custodia"))
        usa_fracao = str(data.get("modo_fracionado") or data.get("liquido_habilitado") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )

        if not codigo:
            return jsonify({"success": False, "message": "Código do item é obrigatório"}), 400

        quantidade_int = None
        if not usa_fracao:
            try:
                quantidade_int = int(quantidade)
                if quantidade_int <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                return jsonify({"success": False, "message": "Quantidade inválida"}), 400

        item = Item.query.filter(
            (Item.codigo_item == str(codigo).strip())
        ).first()

        if not item:
            return jsonify({"success": False, "message": "Item não encontrado"}), 404

        try:
            saldo_atual = float(item.get_saldo_atual() or 0)
        except Exception:
            saldo_atual = 0.0

        quantidade_operacao = float(quantidade_int or 0)
        fracao_payload: dict[str, Any] = {}
        if usa_fracao:
            tipo_id = data.get("liquido_tipo_produto") or data.get("tipo_produto_id")
            fracao_numerador = data.get("liquido_fracao_numerador") or data.get("fracao_numerador")
            fracao_denominador = data.get("liquido_fracao_denominador") or data.get("fracao_denominador")
            total_embalagem_raw = data.get("liquido_total_embalagem") or data.get("quantidade_total_embalagem")

            entry = LIQUID_PRODUCT_TYPES_BY_ID.get(str(tipo_id or "").strip())
            if not entry:
                return jsonify({"success": False, "message": "Tipo de produto líquido não reconhecido"}), 400

            try:
                numerador = int(fracao_numerador or 0)
                denominador = int(fracao_denominador or 0)
            except ValueError:
                return jsonify({"success": False, "message": "Selecione uma fração válida"}), 400

            if numerador <= 0 or denominador <= 0 or numerador > denominador:
                return jsonify({"success": False, "message": "Fração selecionada é inválida"}), 400

            try:
                total_embalagem = float(total_embalagem_raw or 0)
            except ValueError:
                return jsonify({"success": False, "message": "Informe a capacidade total da embalagem"}), 400

            if total_embalagem <= 0:
                return jsonify({"success": False, "message": "Informe a capacidade total da embalagem"}), 400

            unidade_item_raw = (item.unidade or "").strip()
            unidade_item = _infer_unidade(unidade_item_raw)
            unidade_calculo = unidade_item
            if unidade_item not in {"litro", "quilo"}:
                unidade_calculo = _infer_unidade(entry.get("default_unit") or "litro")
            if unidade_calculo not in {"litro", "quilo"}:
                unidade_calculo = "litro"

            fracao = numerador / denominador
            quantidade_calculada = total_embalagem * fracao

            retirada_litros: float | None = None
            retirada_quilos: float | None = None

            if unidade_calculo == "litro":
                retirada_litros = quantidade_calculada
                quantidade_para_saida = retirada_litros
                restante = max(total_embalagem - retirada_litros, 0.0)
            else:
                retirada_quilos = quantidade_calculada
                quantidade_para_saida = retirada_quilos
                restante = max(total_embalagem - retirada_quilos, 0.0)

            if unidade_item not in {"litro", "quilo"}:
                quantidade_para_saida = fracao

            if quantidade_para_saida <= 0:
                return jsonify({"success": False, "message": "Quantidade calculada deve ser positiva"}), 400

            if retirada_litros is not None:
                retirada_litros = round(retirada_litros, 6)
            if retirada_quilos is not None:
                retirada_quilos = round(retirada_quilos, 6)
            quantidade_para_saida = round(quantidade_para_saida, 6)
            restante = round(restante, 6)

            unidade_display = unidade_item_raw or ("litro" if unidade_calculo == "litro" else "quilo")
            unidade_retirada = "L" if unidade_calculo == "litro" else "kg"
            retirada_valor = retirada_litros if unidade_calculo == "litro" else retirada_quilos
            retirada_valor = float(retirada_valor or 0)
            resumo_observacao = (
                f"Saída fracionada {numerador}/{denominador} de {total_embalagem:.2f} {unidade_display}. "
                f"Retirada: {retirada_valor:.2f} {unidade_retirada}. "
                f"Restante estimado: {restante:.2f} {unidade_display}."
            )
            if unidade_item not in {"litro", "quilo"}:
                resumo_observacao += f" Quantidade registrada: {quantidade_para_saida:.3f} {unidade_display or 'un'}"
            if observacao:
                observacao = f"{observacao} | {resumo_observacao}"
            else:
                observacao = resumo_observacao

            quantidade_operacao = float(quantidade_para_saida)
            fracao_payload = {
                "usou_fracao": True,
                "tipo_produto": entry["label"],
                "fracao_numerador": numerador,
                "fracao_denominador": denominador,
                "quantidade_total_embalagem": total_embalagem,
                "quantidade_retirada_em_litros": retirada_litros,
                "quantidade_retirada_em_quilos": retirada_quilos,
                "quantidade_restante": restante,
            }

        if saldo_atual < quantidade_operacao:
            return jsonify({
                "success": False,
                "message": f"Saldo insuficiente. Disponível: {int(saldo_atual) if saldo_atual.is_integer() else saldo_atual}",
            }), 400

        matricula_retirante = (matricula_retirante_raw or "").strip()
        retirante_user = None
        if matricula_retirante and matricula_retirante != current_user.matricula:
            if not _is_admin_or_manager(current_user):
                return jsonify({
                    "success": False,
                    "message": "Apenas administrador/gerente pode registrar retirada em nome de outro usuário.",
                }), 403
            retirante_user = Usuario.query.filter_by(matricula=matricula_retirante).first()
            if not retirante_user:
                return jsonify({
                    "success": False,
                    "message": "Usuário (retirante) não encontrado.",
                }), 400
        else:
            retirante_user = current_user

        saida = Saida()
        saida.codigo_item = item.codigo_item
        saida.quantidade = quantidade_operacao
        saida.matricula = retirante_user.matricula
        saida.data_saida = datetime.utcnow()
        saida.observacao = str(observacao or "").upper()
        saida.local_servico = str(local_servico or "").upper()
        if hasattr(saida, "tipo_custodia"):
            saida.tipo_custodia = tipo_custodia

        if fracao_payload:
            if getattr(saida.__class__, "usou_fracao", None) is not None:
                saida.usou_fracao = True
            for attr_name, value in fracao_payload.items():
                if value is not None and hasattr(saida, attr_name):
                    setattr(saida, attr_name, value)

        db.session.add(saida)
        # Se for ferramenta, criar retirada antes do commit (apenas custódia diária)
        try:
            categoria_text = (item.categoria or '').lower()
            if 'ferrament' in categoria_text and tipo_custodia != "permanente":
                qtd = int(max(1, round(float(quantidade_operacao or 1))))

                retirada_ativa_existente = db.session.query(RetiradaFerramenta.id).filter(
                    RetiradaFerramenta.codigo_item == item.codigo_item,
                    RetiradaFerramenta.matricula == retirante_user.matricula,
                    RetiradaFerramenta.status.in_(['em_uso', 'atrasada'])
                ).first()

                if retirada_ativa_existente:
                    db.session.rollback()
                    return jsonify({
                        "success": False,
                        "message": "Retirada bloqueada: este funcionário já possui esta ferramenta em aberto. Faça a devolução antes de nova retirada."
                    }), 400
                
                # VALIDAÇÃO CRÍTICA: Verificar se há saldo disponível para ferramentas
                from sqlalchemy import func
                quantidade_em_uso = db.session.query(
                    func.coalesce(func.sum(RetiradaFerramenta.quantidade), 0)
                ).filter(
                    RetiradaFerramenta.codigo_item == item.codigo_item,
                    RetiradaFerramenta.status == 'em_uso'
                ).scalar() or 0
                
                saldo_disponivel_ferramenta = saldo_atual - quantidade_em_uso
                
                if saldo_disponivel_ferramenta < qtd:
                    db.session.rollback()
                    return jsonify({
                        "success": False,
                        "message": f"Ferramenta indisponível. {int(quantidade_em_uso)} em uso por outro(s) funcionário(s)"
                    }), 400
                
                retirada = RetiradaFerramenta(
                    codigo_item=item.codigo_item,
                    matricula=retirante_user.matricula,
                    quantidade=qtd,
                    local_servico=str(local_servico or '').upper(),
                    observacao=str(observacao or '').upper(),
                    status='em_uso',
                )
                db.session.add(retirada)
        except ValueError as ve:
            # Exceção de validação deve retornar erro ao cliente
            db.session.rollback()
            return jsonify({"success": False, "message": str(ve)}), 400
        except Exception as e:
            # Outros erros apenas logam mas não interrompem
            logger.warning(f"Erro ao criar RetiradaFerramenta para {item.codigo_item}: {e}")

        db.session.commit()

        try:
            novo_saldo = round(float(item.get_saldo_atual() or 0), 6)
        except Exception:
            novo_saldo = None

        # Notificar via Telegram (opcional)
        try:
            if tipo_custodia == "permanente" and hasattr(TelegramService, "notify_permanent_custody"):
                TelegramService.notify_permanent_custody(saida.id_saida)
            else:
                TelegramService.notify_withdrawal(saida.id_saida, force_single=True)
        except Exception as e:
            logger.warning(f"Falha ao enviar notificação Telegram: {e}")

        return jsonify({
            "success": True,
            "message": "Retirada registrada com sucesso",
            "data": {
                "saida_id": saida.id_saida,
                "retirado_por": {
                    "matricula": retirante_user.matricula,
                    "nome": retirante_user.nome,
                },
                "item": {
                    "codigo": item.codigo_item,
                    "descricao": item.descricao,
                    "saldo": novo_saldo,
                },
            },
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.exception("Erro ao registrar retirada mobile")
        return jsonify({
            "success": False,
            "message": f"Erro ao processar retirada: {str(e)}",
        }), 500


@blueprint.post("/devolver")
@token_required
def devolver_ferramenta_mobile(current_user: Usuario):
    """Registra devolução de ferramenta (categoria Ferramentas) pelo app mobile.

    Importante: devolução de ferramenta NÃO é "entrada" (não deve criar Entrada).
    A devolução é registrada como InventarioEvento (tipo: devolucao_ferramenta).
    """
    try:
        if not _is_admin_or_manager(current_user):
            return jsonify({"success": False, "message": "Acesso negado"}), 403

        data = request.get_json() or {}
        codigo = (data.get("codigo") or "").strip()
        quantidade = data.get("quantidade")
        matricula_devolvedor = (data.get("matricula_devolvedor") or "").strip()

        if not codigo:
            return jsonify({"success": False, "message": "Código do item é obrigatório"}), 400

        try:
            quantidade_int = int(quantidade)
            if quantidade_int <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            return jsonify({"success": False, "message": "Quantidade inválida"}), 400

        item = Item.query.filter(Item.codigo_item == codigo).first()
        if not item:
            return jsonify({"success": False, "message": "Item não encontrado"}), 404

        categoria = (item.categoria or "").strip().lower()
        if "ferrament" not in categoria:
            return jsonify({
                "success": False,
                "message": "Somente itens da categoria 'Ferramentas' podem ser devolvidos.",
            }), 400

        devolvedor_user = current_user
        if matricula_devolvedor and matricula_devolvedor != current_user.matricula:
            if not _is_admin_or_manager(current_user):
                return jsonify({"success": False, "message": "Acesso negado"}), 403
            devolvedor_user = Usuario.query.filter_by(matricula=matricula_devolvedor).first()
            if not devolvedor_user:
                return jsonify({"success": False, "message": "Usuário devolvedor não encontrado"}), 404

        # Só permite devolução se houver retirada diária (RetiradaFerramenta) em aberto
        retiradas_ativas = (
            RetiradaFerramenta.query.filter(
                RetiradaFerramenta.codigo_item == item.codigo_item,
                RetiradaFerramenta.matricula == devolvedor_user.matricula,
                RetiradaFerramenta.status == 'em_uso',
            )
            .order_by(RetiradaFerramenta.data_retirada)
            .limit(quantidade_int)
            .all()
        )

        if len(retiradas_ativas) < quantidade_int:
            return jsonify({
                "success": False,
                "message": "Devolução não permitida: esta ferramenta não possui retirada em custódia diária em aberto.",
            }), 400

        for retirada in retiradas_ativas:
            retirada.status = 'devolvida'
            retirada.data_devolucao = datetime.utcnow()

        # Registrar devolução como evento de inventário (evita tratar como adição/Entrada)
        evento = InventarioEvento(
            codigo_item=item.codigo_item,
            matricula=devolvedor_user.matricula,
            quantidade=float(quantidade_int),
            tipo="devolucao_ferramenta",
            descricao=f"Devolução de Ferramenta (mobile): {item.descricao or 'Item'}",
            data_evento=datetime.utcnow(),
        )
        db.session.add(evento)
        db.session.commit()

        # Notificar via Telegram (opcional)
        try:
            from ..services.telegram_service import TelegramService
            TelegramService.notify_inventory_event(evento.id_evento)
        except Exception as e:
            logger.warning(f"Falha ao enviar notificação Telegram: {e}")

        try:
            novo_saldo = round(float(item.get_saldo_atual() or 0), 6)
        except Exception:
            novo_saldo = None

        return jsonify({
            "success": True,
            "message": "Devolução registrada com sucesso",
            "data": {
                "item": {
                    "codigo": item.codigo_item,
                    "descricao": item.descricao,
                    "saldo": novo_saldo,
                }
            },
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.exception("Erro ao registrar devolução mobile")
        return jsonify({
            "success": False,
            "message": f"Erro ao processar devolução: {str(e)}",
        }), 500


@blueprint.post("/devolver_material")
@token_required
def devolver_material_mobile(current_user: Usuario):
    """Registra devolução de material (qualquer categoria exceto Ferramentas) pelo app mobile.

    Gera registro em Entrada para aparecer no histórico de entradas.
    """
    try:
        if not _is_admin_or_manager(current_user):
            return jsonify({"success": False, "message": "Acesso negado"}), 403

        data = request.get_json() or {}
        codigo = (data.get("codigo") or "").strip()
        quantidade = data.get("quantidade")
        matricula_devolvedor = (data.get("matricula_devolvedor") or "").strip()

        if not codigo:
            return jsonify({"success": False, "message": "Código do item é obrigatório"}), 400

        try:
            quantidade_int = int(quantidade)
            if quantidade_int <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            return jsonify({"success": False, "message": "Quantidade inválida"}), 400

        item = Item.query.filter(Item.codigo_item == codigo).first()
        if not item:
            return jsonify({"success": False, "message": "Item não encontrado"}), 404

        categoria = (item.categoria or "").strip().lower()

        devolvedor_user = current_user
        if matricula_devolvedor and matricula_devolvedor != current_user.matricula:
            if not _is_admin_or_manager(current_user):
                return jsonify({"success": False, "message": "Acesso negado"}), 403
            devolvedor_user = Usuario.query.filter_by(matricula=matricula_devolvedor).first()
            if not devolvedor_user:
                return jsonify({"success": False, "message": "Usuário devolvedor não encontrado"}), 404

        # Compatibilidade: se o app chamar /devolver_material para Ferramentas,
        # executar o fluxo correto (InventarioEvento + baixa de custódia), sem criar Entrada.
        if "ferrament" in categoria:
            retiradas_ativas = (
                RetiradaFerramenta.query.filter(
                    RetiradaFerramenta.codigo_item == item.codigo_item,
                    RetiradaFerramenta.matricula == devolvedor_user.matricula,
                    RetiradaFerramenta.status == 'em_uso',
                )
                .order_by(RetiradaFerramenta.data_retirada)
                .limit(quantidade_int)
                .all()
            )

            if len(retiradas_ativas) < quantidade_int:
                return jsonify({
                    "success": False,
                    "message": "Devolução não permitida: esta ferramenta não possui retirada em custódia diária em aberto.",
                }), 400

            for retirada in retiradas_ativas:
                retirada.status = 'devolvida'
                retirada.data_devolucao = datetime.utcnow()

            evento = InventarioEvento(
                codigo_item=item.codigo_item,
                matricula=devolvedor_user.matricula,
                quantidade=float(quantidade_int),
                tipo="devolucao_ferramenta",
                descricao=f"Devolução de Ferramenta (mobile via /devolver_material): {item.descricao or 'Item'}",
                data_evento=datetime.utcnow(),
            )
            db.session.add(evento)
            db.session.commit()

            try:
                from ..services.telegram_service import TelegramService
                TelegramService.notify_inventory_event(evento.id_evento)
            except Exception as e:
                logger.warning(f"Falha ao enviar notificação Telegram: {e}")

            try:
                novo_saldo = round(float(item.get_saldo_atual() or 0), 6)
            except Exception:
                novo_saldo = None

            return jsonify({
                "success": True,
                "message": "Ferramenta devolvida com sucesso",
                "data": {
                    "item": {
                        "codigo": item.codigo_item,
                        "descricao": item.descricao,
                        "saldo": novo_saldo,
                    }
                },
            }), 201

        evento = inventory_service.registrar_devolucao_material(
            codigo=item.codigo_item,
            quantidade=quantidade_int,
            matricula=devolvedor_user.matricula,
            observacao=None,
            commit=True,
        )

        # Notificar via Telegram (opcional)
        try:
            if evento and hasattr(evento, 'id_evento'):
                from ..services.telegram_service import TelegramService
                logger.info(f"[DEVOLVER_MATERIAL] Enviando notificação Telegram para evento {evento.id_evento}")
                TelegramService.notify_inventory_event(evento.id_evento)
                logger.info("[DEVOLVER_MATERIAL] Notificação Telegram enviada com sucesso")
        except Exception as e:
            logger.error(f"[DEVOLVER_MATERIAL] Falha ao enviar notificação Telegram: {e}", exc_info=True)

        try:
            novo_saldo = round(float(item.get_saldo_atual() or 0), 6)
        except Exception:
            novo_saldo = None

        return jsonify({
            "success": True,
            "message": "Material devolvido com sucesso",
            "data": {
                "item": {
                    "codigo": item.codigo_item,
                    "descricao": item.descricao,
                    "saldo": novo_saldo,
                }
            },
        }), 201

    except ValueError as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": str(e),
        }), 400

    except Exception as e:
        db.session.rollback()
        logger.exception("Erro ao devolver material mobile")
        return jsonify({
            "success": False,
            "message": f"Erro ao processar devolução de material: {str(e)}",
        }), 500


@blueprint.get("/reports/daily")
@mobile_login_required
def mobile_report_daily():
    current_user = g.mobile_user
    if not _is_admin_or_manager(current_user):
        return jsonify({"success": False, "message": "Acesso negado"}), 403

    scope = (request.args.get("scope") or "all").strip().lower()
    fmt = (request.args.get("format") or "pdf").strip().lower()

    if scope not in {"all", "materials", "tools"}:
        return jsonify({"success": False, "message": "Escopo inválido"}), 400
    if fmt not in {"pdf", "xlsx", "jpeg", "jpg"}:
        return jsonify({"success": False, "message": "Formato inválido"}), 400

    # Usar caminho absoluto relativo à raiz do projeto
    from flask import current_app
    instance_path = Path(current_app.instance_path)
    reports_dir = instance_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = TimeService.now_local().strftime('%Y%m%d_%H%M%S')

    # Tratar jpg como jpeg
    if fmt == "jpg":
        fmt = "jpeg"

    if fmt == "pdf":
        target = reports_dir / f"saidas_dia_{scope}_{timestamp}.pdf"
        TelegramService.generate_saidas_dia_pdf(str(target), scope=scope)
        return send_file(target, mimetype="application/pdf", as_attachment=True, download_name=target.name)
    
    if fmt == "jpeg":
        # Gera PDF primeiro, depois converte para JPEG
        pdf_target = reports_dir / f"saidas_dia_{scope}_{timestamp}.pdf"
        TelegramService.generate_saidas_dia_pdf(str(pdf_target), scope=scope)
        
        # Converter PDF para JPEG
        jpeg_target = reports_dir / f"saidas_dia_{scope}_{timestamp}.jpeg"
        _convert_pdf_to_jpeg(str(pdf_target), str(jpeg_target))
        
        return send_file(jpeg_target, mimetype="image/jpeg", as_attachment=True, download_name=jpeg_target.name)

    target = TelegramReportService.generate_daily_xlsx(scope=scope)
    return send_file(target, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=Path(target).name)


@blueprint.get("/reports/monthly")
@mobile_login_required
def mobile_report_monthly():
    current_user = g.mobile_user
    if not _is_admin_or_manager(current_user):
        return jsonify({"success": False, "message": "Acesso negado"}), 403

    scope = (request.args.get("scope") or "all").strip().lower()
    fmt = (request.args.get("format") or "pdf").strip().lower()
    year = request.args.get("year")
    month = request.args.get("month")

    try:
        year_int = int(year)
        month_int = int(month)
        if month_int < 1 or month_int > 12:
            raise ValueError()
    except Exception:
        return jsonify({"success": False, "message": "Ano/mês inválido"}), 400

    if scope not in {"all", "materials", "tools"}:
        return jsonify({"success": False, "message": "Escopo inválido"}), 400
    if fmt not in {"pdf", "xlsx", "jpeg", "jpg"}:
        return jsonify({"success": False, "message": "Formato inválido"}), 400
    
    # Tratar jpg como jpeg
    if fmt == "jpg":
        fmt = "jpeg"

    if fmt == "pdf":
        path = TelegramReportService.generate_monthly_pdf_report(year_int, month_int, scope=scope)
        return send_file(path, mimetype="application/pdf", as_attachment=True, download_name=Path(path).name)
    
    if fmt == "jpeg":
        # Gera PDF primeiro, depois converte para JPEG
        pdf_path = TelegramReportService.generate_monthly_pdf_report(year_int, month_int, scope=scope)
        
        # Converter PDF para JPEG
        instance_path = Path(current_app.instance_path)
        reports_dir = instance_path / "reports"
        timestamp = TimeService.now_local().strftime('%Y%m%d_%H%M%S')
        jpeg_path = reports_dir / f"monthly_{scope}_{year_int}_{month_int:02d}_{timestamp}.jpeg"
        _convert_pdf_to_jpeg(str(pdf_path), str(jpeg_path))
        
        return send_file(jpeg_path, mimetype="image/jpeg", as_attachment=True, download_name=jpeg_path.name)

    path = TelegramReportService.generate_monthly_xlsx_report(year_int, month_int, scope=scope)
    return send_file(path, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=Path(path).name)


@blueprint.get("/produtos/buscar/<codigo>")
@mobile_login_required
def buscar_produto(codigo: str):
    """Busca produto por código de barras."""
    if not codigo:
        return jsonify({"error": "Código não fornecido"}), 400

    item = inventory_service.get_item(codigo)

    if not item:
        return jsonify({
            "found": False,
            "codigo": codigo,
            "message": "Produto não encontrado",
        }), 404

    return jsonify({
        "found": True,
        "produto": {
            "codigo": item.get("codigo"),
            "descricao": item.get("descricao"),
            "categoria": item.get("categoria"),
            "marca": item.get("marca") or item.get("setor"),
            "saldo": item.get("saldo"),
            "estoque_minimo": item.get("estoque_minimo"),
            "unidade": item.get("unidade"),
            "localizacao": item.get("localizacao"),
        },
    }), 200


@blueprint.post("/produtos/cadastrar")
@mobile_login_required
def cadastrar_produto():
    """Cadastra novo produto via código de barras."""
    user = g.mobile_user
    if not _is_admin_or_supervisor(user):
        return jsonify({"error": "Acesso negado. Apenas administradores podem cadastrar."}), 403

    data = request.get_json()

    try:
        payload = {
            "codigo": (data.get("codigo") or "").strip(),
            "descricao": (data.get("descricao") or "").strip(),
            "categoria": data.get("categoria", "Material Elétrico"),
            "marca": (data.get("marca") or "").strip() or None,
            "unidade": (data.get("unidade") or "").strip(),
            "nota_fiscal": (data.get("nota_fiscal") or "").strip() or None,
            "localizacao": (data.get("localizacao") or "").strip() or None,
        }

        if not payload["codigo"] or not payload["descricao"]:
            raise ValueError("Código e descrição são obrigatórios")

        existing = inventory_service.get_item(payload["codigo"])
        if existing:
            return jsonify({"error": "Produto com este código já existe"}), 409

        saldo_inicial = int(data.get("saldo_inicial", 0))
        if saldo_inicial < 0:
            raise ValueError("Saldo inicial deve ser >= 0")

        codigo = inventory_service.create_item(payload)

        if saldo_inicial > 0:
            inventory_service.registrar_entrada(
                MovimentoPayload(
                    codigo=codigo,
                    quantidade=saldo_inicial,
                    matricula=user.matricula,
                    nota_fiscal=payload["nota_fiscal"],
                )
            )

        return jsonify({
            "success": True,
            "message": "Produto cadastrado com sucesso",
            "codigo": codigo,
        }), 201

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Erro ao cadastrar: {str(exc)}"}), 500


@blueprint.get("/categorias")
@mobile_login_required
def listar_categorias():
    """Lista categorias disponíveis."""
    categorias = [
        "Material Elétrico",
        "Hidraulica",
        "Ferramentas",
        "EPI",
        "Materiais de Limpeza",
        "Escritorio",
        "Outros",
    ]
    return jsonify({"categorias": categorias}), 200


@blueprint.get("/health")
def health_check():
    """Verifica se API está funcionando."""
    return jsonify({
        "status": "ok",
        "message": "API Mobile funcionando",
        "version": "1.0.0"
    }), 200


@blueprint.get("/usuarios")
@token_required
def listar_usuarios_mobile(current_user: Usuario):
    """Lista todos os usuários cadastrados para autocomplete (nome + matrícula)."""
    try:
        usuarios = Usuario.query.order_by(Usuario.nome).all()
        resultado = [
            {
                "matricula": u.matricula,
                "nome": u.nome,
                "cargo": getattr(u, "cargo", None),
                "setor": u.setor,
            }
            for u in usuarios
        ]
        return jsonify({
            "success": True,
            "data": resultado,
        }), 200
    except Exception as e:
        logger.exception("Erro ao listar usuários")
        return jsonify({
            "success": False,
            "message": f"Erro ao listar usuários: {str(e)}",
        }), 500


@blueprint.get("/estoque")
@mobile_login_required
def listar_estoque():
    """Lista todos os itens do estoque com busca opcional."""
    search = request.args.get("search", "").strip()
    
    query = Item.query
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Item.descricao.ilike(search_term)) |
            (Item.codigo_item.ilike(search_term)) |
            (Item.marca.ilike(search_term)) |
            (Item.categoria.ilike(search_term))
        )
    
    items = query.order_by(Item.descricao).all()
    
    result = []
    for item in items:
        result.append({
            "id": item.codigo_item,
            "descricao": item.descricao,
            "codigo_barras": item.codigo_item,
            "categoria": item.categoria,
            "localizacao": item.localizacao,
            "marca": item.marca,
            "quantidade": round(float(item.get_saldo_atual() or 0), 6),
            "unidade": item.unidade,
            "estoque_minimo": item.estoque_minimo,
            "tipo_embalagem_novo": item.tipo_embalagem_novo,
            "unidades_por_embalagem": item.unidades_por_embalagem,
            "estoque_embalagens": item.estoque_embalagens,
            "estoque_unidades_soltas": item.estoque_unidades_soltas,
        })
    
    return jsonify(result), 200


@blueprint.get("/estoque/resumo")
@mobile_login_required
def resumo_estoque_mobile():
    """Retorna totais do estoque para KPI mobile."""
    try:
        total_itens = Item.query.count()
        total_quantidade = inventory_service.total_quantity()
        categorias_raw = db.session.query(Item.categoria).distinct().all()
        categorias = { (c[0] or "Sem categoria") for c in categorias_raw }
        total_categorias = len(categorias)

        return jsonify({
            "success": True,
            "data": {
                "total_itens": int(total_itens),
                "total_quantidade": int(total_quantidade),
                "total_categorias": int(total_categorias),
            }
        }), 200
    except Exception:
        logger.exception("Erro ao obter resumo do estoque mobile")
        return jsonify({"success": False, "message": "Erro ao obter resumo do estoque"}), 500


@blueprint.get("/estoque/barcode/<codigo>")
@mobile_login_required
def buscar_por_barcode(codigo: str):
    """Busca item por código de barras."""
    item = Item.query.filter_by(codigo_item=codigo).first()
    
    if not item:
        return jsonify({"message": "Item não encontrado"}), 404
    
    # Formatar estoque com embalagens quando aplicável
    try:
        from ..services.embalagem_service import EmbalagemService
        estoque_formatado = EmbalagemService.formatar_estoque(item) if EmbalagemService.tem_embalagem(item) else None
    except Exception:
        estoque_formatado = None

    return jsonify({
        "id": item.codigo_item,
        "descricao": item.descricao,
        "codigo_barras": item.codigo_item,
        "categoria": item.categoria,
        "localizacao": item.localizacao,
        "marca": item.marca,
        "quantidade": round(float(item.get_saldo_atual() or 0), 6),
        "unidade": item.unidade,
        "estoque_minimo": item.estoque_minimo,
        "tipo_embalagem_novo": item.tipo_embalagem_novo,
        "unidades_por_embalagem": item.unidades_por_embalagem,
        "estoque_embalagens": item.estoque_embalagens,
        "estoque_unidades_soltas": item.estoque_unidades_soltas,
        "estoque_formatado": estoque_formatado,
    }), 200


@blueprint.post("/estoque")
@mobile_login_required
def criar_item_estoque():
    """Cria novo item no estoque."""
    user = g.mobile_user
    if not _is_admin_or_supervisor(user):
        return jsonify({"error": "Apenas administradores ou supervisores podem cadastrar itens"}), 403
    
    # Suportar tanto JSON quanto multipart/form-data (para upload de foto)
    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.form.to_dict()
    else:
        data = request.get_json() or {}
    
    codigo = (data.get("codigo_barras") or "").strip()
    descricao = (data.get("descricao") or "").strip()
    
    if not codigo or not descricao:
        return jsonify({"error": "Código e descrição são obrigatórios"}), 400
    
    # Verifica se já existe
    existing = Item.query.filter_by(codigo_item=codigo).first()
    if existing:
        return jsonify({"error": "Item com este código já existe"}), 409
    
    try:
        # Processar foto se fornecida
        foto_path = None
        if 'foto' in request.files:
            foto_file = request.files['foto']
            if foto_file and foto_file.filename:
                try:
                    foto_path = ItemFotoService.upload_foto(foto_file, codigo)
                except ValueError as foto_error:
                    return jsonify({"error": f"Erro ao fazer upload da foto: {str(foto_error)}"}), 400
        
        # Suportar novo sistema de embalagens (compatível com app antigo)
        tipo_emb_novo = (data.get("tipo_embalagem_novo") or data.get("tipo_embalagem") or "").strip().lower()
        unidades_por_emb = data.get("unidades_por_embalagem")
        if unidades_por_emb is None:
            unidades_por_emb = data.get("grandeza_referencia")

        payload = {
            "codigo": codigo,
            "descricao": descricao,
            "categoria": data.get("categoria", "Material Elétrico"),
            "marca": (data.get("marca") or "").strip() or None,
            "unidade": (data.get("unidade") or "Unidade").strip() or "Unidade",
            "localizacao": (data.get("localizacao") or "").strip() or None,
            "nota_fiscal": None,
            "tipo_embalagem_novo": tipo_emb_novo or None,
            "unidades_por_embalagem": float(unidades_por_emb) if unidades_por_emb not in (None, "") else None,
            "foto_path": foto_path,
        }
        
        codigo_criado = inventory_service.create_item(payload)
        
        # Adiciona saldo inicial se fornecido (entrada)
        quantidade_inicial = int(data.get("quantidade", 0))
        if quantidade_inicial > 0:
            em_embalagens = None
            if tipo_emb_novo and unidades_por_emb not in (None, ""):
                try:
                    if float(unidades_por_emb) > 0:
                        em_embalagens = True
                except (ValueError, TypeError):
                    em_embalagens = None

            inventory_service.registrar_entrada(
                MovimentoPayload(
                    codigo=codigo_criado,
                    quantidade=quantidade_inicial,
                    matricula=user.matricula,
                    nota_fiscal=None,
                    em_embalagens=em_embalagens,
                )
            )
        
        return jsonify({
            "id": codigo_criado,
            "message": "Item cadastrado com sucesso"
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@blueprint.put("/estoque/<codigo>")
@blueprint.post("/estoque/<codigo>")
@mobile_login_required
def atualizar_item_estoque(codigo: str):
    """Atualiza dados de um item do estoque (edição via app).

    Permitido apenas para Administrador ou Gerente.
    Campos aceitos: descricao, categoria, marca, unidade, localizacao, nota_fiscal, foto.
    """
    user = g.mobile_user
    if not _is_admin_or_manager(user):
        return jsonify({"error": "Acesso negado. Apenas administrador ou gerente pode editar itens."}), 403

    codigo = (codigo or "").strip()
    if not codigo:
        return jsonify({"error": "Código não fornecido"}), 400

    # Suportar tanto JSON quanto multipart/form-data (para upload de foto)
    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.form.to_dict()
    else:
        data = request.get_json() or {}

    try:
        existing = inventory_service.get_item(codigo)
        if not existing:
            return jsonify({"error": "Item não encontrado"}), 404

        # Processar foto se fornecida
        foto_path = None
        if 'foto' in request.files:
            foto_file = request.files['foto']
            if foto_file and foto_file.filename:
                try:
                    # Deletar foto antiga se existir
                    if existing.get('foto_path'):
                        ItemFotoService.deletar_foto(existing['foto_path'])
                    foto_path = ItemFotoService.upload_foto(foto_file, codigo)
                except ValueError as foto_error:
                    return jsonify({"error": f"Erro ao fazer upload da foto: {str(foto_error)}"}), 400
        elif data.get('remover_foto') == 'true' or data.get('remover_foto') is True:
            # Remover foto existente
            if existing.get('foto_path'):
                ItemFotoService.deletar_foto(existing['foto_path'])
            foto_path = None  # Será setado no payload para limpar

        tipo_emb_novo = (data.get("tipo_embalagem_novo") or data.get("tipo_embalagem") or "").strip().lower()
        unidades_por_emb = data.get("unidades_por_embalagem")
        if unidades_por_emb is None:
            unidades_por_emb = data.get("grandeza_referencia")

        payload = {
            "descricao": (data.get("descricao") or existing.get("descricao") or "").strip(),
            "categoria": (data.get("categoria") or existing.get("categoria") or "Material Elétrico"),
            "marca": (data.get("marca") or "").strip() or None,
            "unidade": (data.get("unidade") or existing.get("unidade") or "").strip(),
            "localizacao": (data.get("localizacao") or "").strip() or None,
            "nota_fiscal": (data.get("nota_fiscal") or "").strip() or None,
            "tipo_embalagem_novo": tipo_emb_novo or existing.get("tipo_embalagem_novo"),
            "unidades_por_embalagem": float(unidades_por_emb) if unidades_por_emb not in (None, "") else existing.get("unidades_por_embalagem"),
        }
        
        # Adicionar foto_path ao payload se foi modificada
        if foto_path is not None or data.get('remover_foto'):
            payload["foto_path"] = foto_path

        if not payload["descricao"]:
            raise ValueError("Descrição é obrigatória")

        inventory_service.update_item(codigo, payload)
        updated = inventory_service.get_item(codigo)
        return jsonify({"success": True, "item": updated}), 200

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Erro ao atualizar item: {str(exc)}"}), 500


@blueprint.put("/estoque/<codigo>/saldo")
@blueprint.post("/estoque/<codigo>/saldo")
@mobile_login_required
def atualizar_saldo_item_estoque(codigo: str):
    """Atualiza o saldo do item (ajuste) via app.

    Permitido apenas para Administrador ou Gerente.
    Espera JSON: {"saldo": <int>}.
    """
    user = g.mobile_user
    if not _is_admin_or_manager(user):
        return jsonify({"error": "Acesso negado. Apenas administrador ou gerente pode ajustar saldo."}), 403

    codigo = (codigo or "").strip()
    if not codigo:
        return jsonify({"error": "Código não fornecido"}), 400

    data = request.get_json() or {}
    saldo_raw = data.get("saldo")
    try:
        novo_saldo = int(saldo_raw)
        if novo_saldo < 0:
            raise ValueError("Saldo deve ser >= 0")
    except Exception:
        return jsonify({"error": "Saldo inválido. Informe um número inteiro (>= 0)."}), 400

    try:
        existing = inventory_service.get_item(codigo)
        if not existing:
            return jsonify({"error": "Item não encontrado"}), 404

        inventory_service.adjust_item_balance(
            codigo=codigo,
            novo_saldo=novo_saldo,
            matricula=getattr(user, "matricula", None),
            nota_fiscal=None,
        )
        updated = inventory_service.get_item(codigo)
        return jsonify({"success": True, "item": updated}), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Erro ao ajustar saldo: {str(exc)}"}), 500


@blueprint.delete("/estoque/<codigo>")
@blueprint.post("/estoque/<codigo>/delete")
@mobile_login_required
def excluir_item_estoque(codigo: str):
    """Exclui um item do estoque via app.

    Permitido apenas para Administrador ou Gerente.
    Bloqueia exclusão se houver movimentações (Entrada/Saída) ou eventos de inventário.
    """
    user = g.mobile_user
    if not _is_admin_or_manager(user):
        return jsonify({"error": "Acesso negado. Apenas administrador ou gerente pode excluir itens."}), 403

    codigo = (codigo or "").strip()
    if not codigo:
        return jsonify({"error": "Código não fornecido"}), 400

    try:
        item = Item.query.filter_by(codigo_item=codigo).first()
        if not item:
            return jsonify({"error": "Item não encontrado"}), 404

        has_saida = Saida.query.filter(Saida.codigo_item == codigo).first() is not None
        has_entrada = Entrada.query.filter(Entrada.codigo_item == codigo).first() is not None
        has_inventario = (
            InventarioEvento.query.filter(InventarioEvento.codigo_item == codigo).first() is not None
        )
        if has_saida or has_entrada or has_inventario:
            return jsonify({
                "error": "Não é possível excluir: item possui movimentações/ajustes registrados."
            }), 409

        inventory_service.delete_item(codigo)
        return jsonify({"success": True}), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Erro ao excluir item: {str(exc)}"}), 500


@blueprint.get("/reports/history")
@mobile_login_required
def mobile_reports_history():
    """Lista todos os relatórios disponíveis para download.
    
    Query params:
        - date_from: data início (YYYY-MM-DD)
        - date_to: data fim (YYYY-MM-DD)
        - type: tipo de relatório (saidas, estoque, mensal, all)
        - format: formato (pdf, xlsx, jpeg, all)
    """
    current_user = g.mobile_user
    if not _is_admin_or_manager(current_user):
        return jsonify({"success": False, "message": "Acesso negado"}), 403
    
    from pathlib import Path
    from datetime import datetime
    
    reports_dir = Path(current_app.instance_path) / "reports"
    
    if not reports_dir.exists():
        return jsonify({"success": True, "reports": [], "count": 0}), 200
    
    # Obter filtros
    filters = {
        "date_from": request.args.get("date_from"),
        "date_to": request.args.get("date_to"),
        "type": request.args.get("type", "all"),
        "format": request.args.get("format", "all"),
    }
    
    reports = []
    
    # Listar arquivos
    for item in reports_dir.iterdir():
        if item.is_file() and item.suffix.lower() in [".pdf", ".xlsx", ".jpeg", ".jpg"]:
            # Extrair informações do nome do arquivo
            filename = item.name
            parts = filename.split("_")
            
            info = {
                "filename": filename,
                "type": "unknown",
                "scope": "all",
                "format": item.suffix[1:].upper(),
                "size_mb": round(item.stat().st_size / (1024 * 1024), 2),
            }
            
            # Identificar tipo
            if filename.startswith("saidas_dia"):
                info["type"] = "saidas"
                if len(parts) >= 4 and parts[2] in ["all", "materials", "tools"]:
                    info["scope"] = parts[2]
                    timestamp_part = parts[3].split(".")[0]
                elif len(parts) >= 3:
                    timestamp_part = parts[2].split(".")[0]
                else:
                    timestamp_part = None
                    
                if timestamp_part:
                    try:
                        dt = datetime.strptime(timestamp_part, "%Y%m%d_%H%M%S")
                        info["date"] = dt.isoformat()
                        info["date_formatted"] = dt.strftime("%d/%m/%Y %H:%M")
                    except ValueError:
                        info["date"] = datetime.fromtimestamp(item.stat().st_mtime).isoformat()
                        info["date_formatted"] = datetime.fromtimestamp(item.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            
            elif filename.startswith("estoque_baixo"):
                info["type"] = "estoque"
                if len(parts) >= 3:
                    timestamp_part = parts[2].split(".")[0]
                    try:
                        dt = datetime.strptime(timestamp_part, "%Y%m%d_%H%M%S")
                        info["date"] = dt.isoformat()
                        info["date_formatted"] = dt.strftime("%d/%m/%Y %H:%M")
                    except ValueError:
                        info["date"] = datetime.fromtimestamp(item.stat().st_mtime).isoformat()
                        info["date_formatted"] = datetime.fromtimestamp(item.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            
            elif filename.startswith("monthly"):
                info["type"] = "mensal"
                if len(parts) >= 5:
                    info["scope"] = parts[1]
                    try:
                        year = int(parts[2])
                        month = int(parts[3])
                        info["month"] = f"{month:02d}/{year}"
                    except (ValueError, IndexError):
                        pass
                    
                    timestamp_part = parts[4].split(".")[0]
                    try:
                        dt = datetime.strptime(timestamp_part, "%Y%m%d_%H%M%S")
                        info["date"] = dt.isoformat()
                        info["date_formatted"] = dt.strftime("%d/%m/%Y %H:%M")
                    except ValueError:
                        info["date"] = datetime.fromtimestamp(item.stat().st_mtime).isoformat()
                        info["date_formatted"] = datetime.fromtimestamp(item.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            
            # Se não conseguiu extrair data, usar data de modificação
            if "date" not in info:
                dt = datetime.fromtimestamp(item.stat().st_mtime)
                info["date"] = dt.isoformat()
                info["date_formatted"] = dt.strftime("%d/%m/%Y %H:%M")
            
            # Aplicar filtros
            if filters["type"] != "all" and info["type"] != filters["type"]:
                continue
            
            if filters["format"] != "all" and info["format"].lower() != filters["format"].lower():
                continue
            
            if filters["date_from"]:
                try:
                    date_from = datetime.fromisoformat(filters["date_from"])
                    report_date = datetime.fromisoformat(info["date"])
                    if report_date < date_from:
                        continue
                except ValueError:
                    pass
            
            if filters["date_to"]:
                try:
                    date_to = datetime.fromisoformat(filters["date_to"])
                    date_to = date_to.replace(hour=23, minute=59, second=59)
                    report_date = datetime.fromisoformat(info["date"])
                    if report_date > date_to:
                        continue
                except ValueError:
                    pass
            
            reports.append(info)
    
    # Ordenar por data (mais recente primeiro)
    reports.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    return jsonify({
        "success": True,
        "reports": reports,
        "count": len(reports),
    }), 200


@blueprint.get("/reports/download/<path:filename>")
@mobile_login_required
def mobile_reports_download(filename: str):
    """Baixa um relatório específico pelo nome do arquivo.
    
    Args:
        filename: Nome do arquivo (validado para evitar path traversal)
    """
    current_user = g.mobile_user
    if not _is_admin_or_manager(current_user):
        return jsonify({"success": False, "message": "Acesso negado"}), 403
    
    # Validar nome do arquivo para evitar path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        return jsonify({"success": False, "message": "Nome de arquivo inválido"}), 400
    
    reports_dir = Path(current_app.instance_path) / "reports"
    file_path = reports_dir / filename
    
    if not file_path.exists() or not file_path.is_file():
        return jsonify({"success": False, "message": "Relatório não encontrado"}), 404
    
    # Determinar mimetype
    ext = file_path.suffix.lower()
    mimetype_map = {
        ".pdf": "application/pdf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".jpeg": "image/jpeg",
        ".jpg": "image/jpeg",
    }
    
    mimetype = mimetype_map.get(ext, "application/octet-stream")
    
    return send_file(
        file_path,
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )

