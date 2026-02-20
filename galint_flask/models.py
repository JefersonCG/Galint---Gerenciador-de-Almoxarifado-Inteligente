"""SQLAlchemy models mirroring the legacy schema."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from flask_login import UserMixin
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, backref, validates
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class Item(db.Model):
    __tablename__ = "itens"

    codigo_item: Mapped[str] = mapped_column(String, primary_key=True)
    descricao: Mapped[str] = mapped_column(String, nullable=False)
    unidade: Mapped[str | None] = mapped_column(String, nullable=True, default="Unidade")
    localizacao: Mapped[str | None] = mapped_column(String, nullable=True)
    setor: Mapped[str] = mapped_column(String, nullable=False)
    estoque_minimo: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nota_fiscal: Mapped[str | None] = mapped_column(String, nullable=True)
    categoria: Mapped[str] = mapped_column(String, nullable=False, default="Material Elétrico")
    marca: Mapped[str | None] = mapped_column(String, nullable=True)
    numero_serie: Mapped[str | None] = mapped_column(String, nullable=True)
    modelo: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Campos de rastreabilidade
    data_entrada: Mapped[date | None] = mapped_column(Date, nullable=True, server_default=func.now())
    lote: Mapped[str | None] = mapped_column(String(50), nullable=True)
    data_fabricacao: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_validade: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    # Campos de unidade dinâmica (antigos)
    tipo_embalagem: Mapped[str | None] = mapped_column(String(20), nullable=True)
    grandeza_referencia: Mapped[float | None] = mapped_column(Float, nullable=True)
    densidade: Mapped[float | None] = mapped_column(Float, nullable=True)
    litros_por_embalagem: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # Sistema de embalagens (novo)
    tipo_embalagem_novo: Mapped[str | None] = mapped_column(String(20), nullable=True)  # lata, rolo, pacote, caixa, litro, balde, nenhum
    unidades_por_embalagem: Mapped[float | None] = mapped_column(Float, nullable=True)
    estoque_embalagens: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    estoque_unidades_soltas: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    
    # Código de barras
    barcode_image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Histórico de Edição
    ultima_edicao_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ultima_edicao_por: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Campos de Equipamento
    voltagem: Mapped[str | None] = mapped_column(String(50), nullable=True)
    amperagem: Mapped[str | None] = mapped_column(String(50), nullable=True)
    local_instalacao: Mapped[str | None] = mapped_column(String(255), nullable=True)

    entradas: Mapped[list[Entrada]] = relationship("Entrada", back_populates="item", cascade="all, delete-orphan")
    saidas: Mapped[list[Saida]] = relationship("Saida", back_populates="item", cascade="all, delete-orphan")

    def to_dict(self, include_balance: bool = False) -> dict[str, object]:
        data = {
            "codigo": self.codigo_item,
            "descricao": self.descricao,
            "unidade": self.unidade,
            "localizacao": self.localizacao,
            "setor": self.setor,
            "marca": self.marca,
            "estoque_minimo": self.estoque_minimo,
            "nota_fiscal": self.nota_fiscal,
            "categoria": self.categoria,
            "numero_serie": self.numero_serie,
            "modelo": self.modelo,
            "data_entrada": self.data_entrada.isoformat() if self.data_entrada else None,
            "lote": self.lote,
            "data_fabricacao": self.data_fabricacao.isoformat() if self.data_fabricacao else None,
            "data_validade": self.data_validade.isoformat() if self.data_validade else None,
            "ultima_edicao_em": self.ultima_edicao_em.isoformat() if self.ultima_edicao_em else None,
            "ultima_edicao_por": self.ultima_edicao_por,
            "voltagem": self.voltagem,
            "amperagem": self.amperagem,
            "local_instalacao": self.local_instalacao,
            "tipo_embalagem": self.tipo_embalagem,
            "grandeza_referencia": self.grandeza_referencia,
            "densidade": self.densidade,
            "litros_por_embalagem": self.litros_por_embalagem,
            "tipo_embalagem_novo": self.tipo_embalagem_novo,
            "unidades_por_embalagem": self.unidades_por_embalagem,
            "estoque_embalagens": self.estoque_embalagens,
            "estoque_unidades_soltas": self.estoque_unidades_soltas,
            "barcode_image_path": self.barcode_image_path,
        }
        if include_balance:
            data["saldo"] = self.get_saldo_atual()
            if self.tipo_embalagem_novo and self.unidades_por_embalagem:
                data["saldo_embalagens"] = self.estoque_embalagens
                data["saldo_unidades_soltas"] = self.estoque_unidades_soltas
        return data
    
    def get_estoque_total_com_embalagens(self) -> float:
        """Calcula o estoque total considerando embalagens + unidades soltas."""
        if self.tipo_embalagem_novo and self.unidades_por_embalagem:
            return (self.estoque_embalagens * self.unidades_por_embalagem) + self.estoque_unidades_soltas
        return self.get_saldo_atual()
    
    def get_nome_embalagem(self) -> str:
        """Retorna o nome da embalagem no singular."""
        nomes = {
            'lata': 'lata',
            'rolo': 'rolo',
            'pacote': 'pacote',
            'caixa': 'caixa',
            'litro': 'litro',
            'balde': 'balde'
        }
        return nomes.get(self.tipo_embalagem_novo, 'embalagem')
    
    def get_nome_embalagem_plural(self) -> str:
        """Retorna o nome da embalagem no plural."""
        nomes = {
            'lata': 'latas',
            'rolo': 'rolos',
            'pacote': 'pacotes',
            'caixa': 'caixas',
            'litro': 'litros',
            'balde': 'baldes'
        }
        return nomes.get(self.tipo_embalagem_novo, 'embalagens')

    def get_saldo_atual(self) -> float:
        """Calcula o saldo deste item.

        Observação: o saldo pode ser fracionário (ex.: saídas fracionadas em LATA).
        """
        entradas = sum(entrada.quantidade for entrada in self.entradas)
        saidas = sum(saida.quantidade for saida in self.saidas)
        ajustes = (
            db.session.query(func.coalesce(func.sum(InventarioEvento.quantidade), 0))
            .filter(InventarioEvento.codigo_item == self.codigo_item)
            .scalar()
        )
        return entradas - saidas + (ajustes or 0)

    @staticmethod
    def get_saldo_total_by_codigo(codigo: str) -> float:
        """Calcula o saldo total de TODOS os lotes com o mesmo código EAN."""
        itens = db.session.query(Item).filter(Item.codigo_item == codigo).all()
        return sum(item.get_saldo_atual() for item in itens)

    @validates("grandeza_referencia", "densidade", "litros_por_embalagem", "unidades_por_embalagem", "estoque_embalagens", "estoque_unidades_soltas")
    def _coerce_float_fields(self, _key: str, value):
        if value in ("", None):
            # Para estoque_embalagens e estoque_unidades_soltas, retorna 0 em vez de None
            if _key in ("estoque_embalagens", "estoque_unidades_soltas"):
                return 0
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            if _key in ("estoque_embalagens", "estoque_unidades_soltas"):
                return 0
            return None


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    matricula: Mapped[str] = mapped_column(String, primary_key=True)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    setor: Mapped[str | None] = mapped_column(String, nullable=True)
    cargo: Mapped[str | None] = mapped_column(String, default="")
    senha_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    is_admin: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_standard: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    barcode_token: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    active_session_id: Mapped[str | None] = mapped_column(String, nullable=True)

    entradas: Mapped[list[Entrada]] = relationship("Entrada", back_populates="usuario")
    saidas: Mapped[list[Saida]] = relationship("Saida", back_populates="usuario")

    @property
    def id(self) -> str:  # type: ignore[override]
        return self.matricula

    @property
    def admin(self) -> bool:
        return bool(self.is_admin)

    @admin.setter
    def admin(self, value: bool) -> None:
        self.is_admin = 1 if bool(value) else 0

    def set_password(self, senha: str) -> None:
        self.senha_hash = generate_password_hash(senha)

    def check_password(self, senha: str) -> bool:
        if not self.senha_hash:
            return False
        return check_password_hash(self.senha_hash, senha)


class Saida(db.Model):
    __tablename__ = "saidas"

    id_saida: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo_item: Mapped[str | None] = mapped_column(ForeignKey("itens.codigo_item"))
    matricula: Mapped[str | None] = mapped_column(ForeignKey("usuarios.matricula"))
    data_saida: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    quantidade: Mapped[float] = mapped_column(Float, nullable=False)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo_produto: Mapped[str | None] = mapped_column(String, nullable=True)
    densidade_aplicada: Mapped[float | None] = mapped_column(Float, nullable=True)
    fracao_numerador: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fracao_denominador: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantidade_total_embalagem: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantidade_retirada_em_litros: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantidade_retirada_em_quilos: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantidade_restante: Mapped[float | None] = mapped_column(Float, nullable=True)
    usou_fracao: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    local_servico: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo_custodia: Mapped[str] = mapped_column(String(20), nullable=False, default="temporaria")  # temporaria ou permanente

    item: Mapped[Item | None] = relationship("Item", back_populates="saidas")
    usuario: Mapped[Usuario | None] = relationship("Usuario", back_populates="saidas")


class Entrada(db.Model):
    __tablename__ = "entradas"

    id_entrada: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo_item: Mapped[str | None] = mapped_column(ForeignKey("itens.codigo_item"))
    matricula: Mapped[str | None] = mapped_column(ForeignKey("usuarios.matricula"))
    data_entrada: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    quantidade: Mapped[float] = mapped_column(Float, nullable=False)
    nota_fiscal: Mapped[str | None] = mapped_column(Text, nullable=True)

    item: Mapped[Item | None] = relationship("Item", back_populates="entradas")
    usuario: Mapped[Usuario | None] = relationship("Usuario", back_populates="entradas")


class InventarioEvento(db.Model):
    __tablename__ = "inventario_eventos"

    id_evento: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo_item: Mapped[str | None] = mapped_column(String, nullable=True)
    matricula: Mapped[str | None] = mapped_column(String, nullable=True)
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    quantidade: Mapped[float] = mapped_column(Float, nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_evento: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    matricula: Mapped[str | None] = mapped_column(String, nullable=True)
    mensagem: Mapped[str] = mapped_column(Text, nullable=False)
    data_envio: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class MaterialInventario(db.Model):
    __tablename__ = "material_inventario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    saida_id: Mapped[int | None] = mapped_column(ForeignKey("saidas.id_saida"), nullable=True)
    codigo_item: Mapped[str | None] = mapped_column(String, nullable=True)
    matricula: Mapped[str | None] = mapped_column(String, nullable=True)
    responsavel_nome: Mapped[str | None] = mapped_column(String, nullable=True)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_registro: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    saida: Mapped[Saida | None] = relationship("Saida", backref="material_inventario")


class DescarteAutorizacao(db.Model):
    __tablename__ = "descarte_autorizacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gerente_nome: Mapped[str] = mapped_column(String, nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    conteudo: Mapped[str | None] = mapped_column(Text, nullable=True)
    arquivo_relatorio: Mapped[str] = mapped_column(String, nullable=False)
    data_autorizacao: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class TelegramConfig(db.Model):
    __tablename__ = "telegram_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_token: Mapped[str | None] = mapped_column(String, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notify_on_withdrawal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_supervisors: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    alert_weekday_time: Mapped[str | None] = mapped_column(String, nullable=True, default="16:20")
    alert_saturday_time: Mapped[str | None] = mapped_column(String, nullable=True, default="11:00")
    alert_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_updated: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Low stock notifications
    low_stock_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    low_stock_weekly_count: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    low_stock_daily_count: Mapped[int] = mapped_column(Integer, nullable=False, default=3)


class TelegramUser(db.Model):
    __tablename__ = "telegram_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    matricula: Mapped[str] = mapped_column(ForeignKey("usuarios.matricula"), nullable=False, unique=True)
    chat_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    celular: Mapped[str | None] = mapped_column(String, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_withdraw_via_telegram: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="Permite que o usuário faça retiradas via Telegram (escaneando código de barras)"
    )
    can_create_item_via_telegram: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="Permite que o usuário cadastre itens via Telegram"
    )
    can_update_item_via_telegram: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="Permite que o usuário edite itens existentes via Telegram"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_notification: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    usuario: Mapped[Usuario] = relationship("Usuario", backref=backref("telegram_config", cascade="all, delete-orphan"))


class TelegramNotificationPreferences(db.Model):
    """Preferências de notificações do Telegram por usuário.
    
    Permite que cada usuário escolha quais tipos de notificações deseja receber
    por categoria de material/ferramenta e tipo de operação (retirada/devolução).
    
    Categorias suportadas:
    - Ferramentas
    - Limpeza
    - Elétrico
    - Hidráulico
    - Construção
    - Pintura/Drywall
    - Piscina
    - EPIs (Equipamentos de Proteção Individual)
    """
    __tablename__ = "telegram_notification_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(
        ForeignKey("telegram_users.id", ondelete="CASCADE"), 
        nullable=False, 
        unique=True
    )
    
    # Ferramentas
    notify_ferramenta_withdrawal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Receber notificações de retirada de ferramentas"
    )
    notify_ferramenta_return: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Receber notificações de devolução de ferramentas"
    )
    
    # Limpeza
    notify_limpeza_withdrawal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Receber notificações de retirada de materiais de limpeza"
    )
    notify_limpeza_return: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Receber notificações de devolução de materiais de limpeza"
    )
    
    # Elétrico
    notify_eletrico_withdrawal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Receber notificações de retirada de materiais elétricos"
    )
    notify_eletrico_return: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Receber notificações de devolução de materiais elétricos"
    )
    
    # Hidráulico
    notify_hidraulico_withdrawal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Receber notificações de retirada de materiais hidráulicos"
    )
    notify_hidraulico_return: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Receber notificações de devolução de materiais hidráulicos"
    )
    
    # Construção
    notify_construcao_withdrawal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Receber notificações de retirada de materiais de construção"
    )
    notify_construcao_return: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Receber notificações de devolução de materiais de construção"
    )
    
    # Pintura/Drywall
    notify_pintura_withdrawal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Receber notificações de retirada de materiais de pintura/drywall"
    )
    notify_pintura_return: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Receber notificações de devolução de materiais de pintura/drywall"
    )
    
    # Piscina
    notify_piscina_withdrawal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Receber notificações de retirada de materiais de piscina"
    )
    notify_piscina_return: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Receber notificações de devolução de materiais de piscina"
    )
    
    # EPIs
    notify_epi_withdrawal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Receber notificações de retirada de EPIs"
    )
    notify_epi_return: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Receber notificações de devolução de EPIs"
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relacionamento
    telegram_user: Mapped[TelegramUser] = relationship(
        "TelegramUser", 
        backref=backref("notification_preferences", uselist=False, cascade="all, delete-orphan")
    )
    
    @staticmethod
    def normalize_category(categoria: str) -> str:
        """Normaliza nome da categoria para o padrão do sistema.
        
        Args:
            categoria: Nome da categoria do item (ex: "Material Elétrico", "Ferramenta")
            
        Returns:
            Nome normalizado (ex: "eletrico", "ferramenta")
        """
        if not categoria:
            return "outros"
            
        categoria_lower = categoria.lower().strip()
        
        # Mapeamento de variações para nomes padronizados
        mappings = {
            "ferramenta": ["ferramenta", "ferramentas", "tool", "tools"],
            "limpeza": ["limpeza", "material de limpeza", "materiais de limpeza"],
            "eletrico": ["elétrico", "eletrico", "material elétrico", "material eletrico", "materiais elétricos"],
            "hidraulico": ["hidráulico", "hidraulico", "material hidráulico", "material hidraulico", "materiais hidráulicos"],
            "construcao": ["construção", "construcao", "material de construção", "material de construcao", "construcao civil"],
            "pintura": ["pintura", "drywall", "pintura/drywall", "material de pintura", "gesso"],
            "piscina": ["piscina", "material de piscina", "materiais de piscina"],
            "epi": ["epi", "epis", "equipamento de proteção", "equipamento de protecao", "segurança"],
        }
        
        for normalized, variations in mappings.items():
            if any(var in categoria_lower for var in variations):
                return normalized
                
        return "outros"
    
    def should_notify(self, categoria: str, is_return: bool = False) -> bool:
        """Verifica se o usuário deve receber notificação para uma categoria e tipo de operação.
        
        Args:
            categoria: Categoria do item (ex: "Material Elétrico", "Ferramenta")
            is_return: True se for devolução, False se for retirada
            
        Returns:
            True se deve notificar, False caso contrário
        """
        normalized = self.normalize_category(categoria)
        operation = "return" if is_return else "withdrawal"
        field_name = f"notify_{normalized}_{operation}"
        
        # Se a categoria não foi mapeada, notifica por padrão
        if not hasattr(self, field_name):
            return True
            
        return getattr(self, field_name, True)


class TelegramConversation(db.Model):
    """Armazena estado de conversas ativas para registro automático."""
    __tablename__ = "telegram_conversations"

    chat_id: Mapped[str] = mapped_column(String, primary_key=True)
    state: Mapped[str] = mapped_column(String, nullable=False)  # 'awaiting_name', 'awaiting_cargo', 'completed'
    nome_informado: Mapped[str | None] = mapped_column(String, nullable=True)
    cargo_informado: Mapped[str | None] = mapped_column(String, nullable=True)
    celular_informado: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class TelegramGroup(db.Model):
    __tablename__ = "telegram_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    receive_withdrawals: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    receive_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class TelegramNotification(db.Model):
    __tablename__ = "telegram_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String, nullable=False)
    recipient_name: Mapped[str | None] = mapped_column(String, nullable=True)
    message_type: Mapped[str] = mapped_column(String, nullable=False)  # 'withdrawal', 'alert', 'test'
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)  # 'sent', 'failed'
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    saida_id: Mapped[int | None] = mapped_column(ForeignKey("saidas.id_saida"), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    saida: Mapped[Saida | None] = relationship("Saida", backref="telegram_notifications")


class TelegramOutbox(db.Model):
    """Fila persistente (outbox) para envio confiável via Telegram.

    Objetivo:
    - Registrar a intenção de envio antes de chamar a API.
    - Permitir retry/backoff automático e resiliência a restart.
    - Garantir idempotência via `idempotency_key`.

    Observação:
    - Mantemos `TelegramNotification` como histórico/visibilidade. O outbox aponta
      para uma notificação única (`notification_id`) que é atualizada a cada tentativa.
    """

    __tablename__ = "telegram_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")  # pending/failed/sent/dead
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    available_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0 = ilimitado
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    chat_id: Mapped[str] = mapped_column(String, nullable=False)
    recipient_name: Mapped[str | None] = mapped_column(String, nullable=True)
    message_type: Mapped[str] = mapped_column(String, nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    parse_mode: Mapped[str | None] = mapped_column(String, nullable=True, default="HTML")
    reply_markup_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Referências opcionais (para rastreabilidade/idempotência por evento)
    saida_id: Mapped[int | None] = mapped_column(ForeignKey("saidas.id_saida"), nullable=True)
    entrada_id: Mapped[int | None] = mapped_column(ForeignKey("entradas.id_entrada"), nullable=True)
    inventario_evento_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventario_eventos.id_evento"), nullable=True
    )

    notification_id: Mapped[int | None] = mapped_column(
        ForeignKey("telegram_notifications.id"), nullable=True
    )

    notification: Mapped[TelegramNotification | None] = relationship(
        "TelegramNotification", backref="outbox_message", uselist=False
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        self.deleted_at = func.now()

    @classmethod
    def active_query(cls):
        return cls.query.filter(cls.deleted_at.is_(None))


class Device(db.Model, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_uuid: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, unique=True)

    platform: Mapped[str] = mapped_column(String(20), nullable=False, default="android")
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    apk_version: Mapped[str] = mapped_column(String(20), nullable=False)
    apk_build_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    apk_channel: Mapped[str] = mapped_column(String(20), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    current_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("usuarios.matricula", ondelete="SET NULL"), nullable=True
    )

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)

    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_by: Mapped[str | None] = mapped_column(ForeignKey("usuarios.matricula", ondelete="SET NULL"), nullable=True)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    current_user: Mapped[Usuario | None] = relationship(
        "Usuario", foreign_keys=[current_user_id], backref="devices"
    )
    blocked_by_user: Mapped[Usuario | None] = relationship(
        "Usuario", foreign_keys=[blocked_by], backref="blocked_devices"
    )
    sessions: Mapped[list[DeviceSession]] = relationship(
        "DeviceSession", back_populates="device", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[ApkAuditLog]] = relationship("ApkAuditLog", back_populates="device")

    @property
    def is_online(self) -> bool:
        if not self.last_heartbeat_at:
            return False
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        return self.last_heartbeat_at >= cutoff

    def block(self, reason: str, admin_id: str | None) -> None:
        self.status = "blocked"
        self.blocked_at = func.now()
        self.blocked_reason = reason
        self.blocked_by = admin_id
        DeviceSession.query.filter_by(device_id=self.id, status="active").update(
            {"status": "revoked", "revoked_at": func.now()}
        )
        ApkAuditLog.log_action(
            action_type="block_device",
            device_id=self.id,
            admin_id=admin_id,
            details={"reason": reason},
        )

    def force_logout(self, admin_id: str | None) -> None:
        sessions = DeviceSession.query.filter_by(device_id=self.id, status="active").all()
        for session in sessions:
            session.revoke(reason="Admin force logout", admin_id=admin_id)


class DeviceSession(db.Model, TimestampMixin):
    __tablename__ = "device_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("usuarios.matricula", ondelete="CASCADE"), nullable=False)

    session_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    refresh_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    logged_in_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    logged_out_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    revoked_by: Mapped[str | None] = mapped_column(ForeignKey("usuarios.matricula", ondelete="SET NULL"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    device: Mapped[Device] = relationship("Device", back_populates="sessions")
    user: Mapped[Usuario] = relationship("Usuario", foreign_keys=[user_id], backref="device_sessions")
    revoked_by_user: Mapped[Usuario | None] = relationship("Usuario", foreign_keys=[revoked_by])
    audit_logs: Mapped[list[ApkAuditLog]] = relationship("ApkAuditLog", back_populates="session")

    __table_args__ = (
        CheckConstraint(
            "logged_out_at IS NULL OR logged_out_at >= logged_in_at",
            name="chk_logout_after_login",
        ),
        CheckConstraint(
            "expires_at >= logged_in_at",
            name="chk_expires_after_login",
        ),
    )

    def revoke(self, reason: str, admin_id: str | None = None) -> None:
        self.status = "revoked"
        self.revoked_at = func.now()
        self.revoke_reason = reason
        self.revoked_by = admin_id
        ApkAuditLog.log_action(
            action_type="revoke_session",
            device_id=self.device_id,
            user_id=self.user_id,
            admin_id=admin_id,
            details={"reason": reason, "session_id": self.id},
        )

    @classmethod
    def validate_token(cls, token_hash: str):
        return (
            cls.query.filter(
                cls.session_token_hash == token_hash,
                cls.status == "active",
                cls.expires_at > func.now(),
            )
            .first()
        )


class ApkVersion(db.Model, TimestampMixin):
    __tablename__ = "apk_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_name: Mapped[str] = mapped_column(String(20), nullable=False)
    version_code: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)

    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    release_date: Mapped[date] = mapped_column(Date, nullable=False, default=func.current_date())
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    download_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    eas_build_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    eas_update_group_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_by: Mapped[str | None] = mapped_column(ForeignKey("usuarios.matricula", ondelete="SET NULL"), nullable=True)
    created_by_user: Mapped[Usuario | None] = relationship("Usuario", foreign_keys=[created_by])

    __table_args__ = (
        CheckConstraint("version_code > 0", name="chk_version_positive"),
        UniqueConstraint("version_name", "channel", name="uq_version_channel"),
    )

    @classmethod
    def get_latest_mandatory(cls, channel: str = "production"):
        return (
            cls.query.filter_by(channel=channel, is_mandatory=True)
            .order_by(cls.version_code.desc())
            .first()
        )

    @classmethod
    def is_version_allowed(cls, version_name: str, channel: str) -> bool:
        version = cls.query.filter_by(version_name=version_name, channel=channel).first()
        if not version:
            return True
        return not version.is_blocked


class FeatureFlag(db.Model, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "feature_flags"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    flag_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    flag_type: Mapped[str] = mapped_column(String(50), nullable=False, default="boolean")
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    requires_app_restart: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    min_app_version: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_by: Mapped[str | None] = mapped_column(ForeignKey("usuarios.matricula", ondelete="SET NULL"), nullable=True)
    created_by_user: Mapped[Usuario | None] = relationship("Usuario", foreign_keys=[created_by])

    assignments: Mapped[list[FeatureAssignment]] = relationship(
        "FeatureAssignment", back_populates="feature_flag", cascade="all, delete-orphan"
    )


class FeatureAssignment(db.Model, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "feature_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feature_flag_id: Mapped[int] = mapped_column(
        ForeignKey("feature_flags.id", ondelete="CASCADE"), nullable=False
    )

    target_type: Mapped[str] = mapped_column(
        Enum("user", "device", "profile", name="target_type_enum"), nullable=False
    )
    target_id: Mapped[str] = mapped_column(String(100), nullable=False)

    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    override_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    assigned_by: Mapped[str | None] = mapped_column(ForeignKey("usuarios.matricula", ondelete="SET NULL"), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    feature_flag: Mapped[FeatureFlag] = relationship("FeatureFlag", back_populates="assignments")
    assigned_by_user: Mapped[Usuario | None] = relationship("Usuario", foreign_keys=[assigned_by])

    __table_args__ = (
        UniqueConstraint("feature_flag_id", "target_type", "target_id", name="uq_feature_assignment"),
    )


class ApkAuditLog(db.Model):
    __tablename__ = "apk_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    user_id: Mapped[str | None] = mapped_column(ForeignKey("usuarios.matricula", ondelete="SET NULL"), nullable=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    admin_id: Mapped[str | None] = mapped_column(ForeignKey("usuarios.matricula", ondelete="SET NULL"), nullable=True)

    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    action_result: Mapped[str] = mapped_column(String(20), nullable=False, default="success")

    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    apk_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("device_sessions.id", ondelete="SET NULL"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    user: Mapped[Usuario | None] = relationship("Usuario", foreign_keys=[user_id])
    admin: Mapped[Usuario | None] = relationship("Usuario", foreign_keys=[admin_id])
    device: Mapped[Device | None] = relationship("Device", back_populates="audit_logs")
    session: Mapped[DeviceSession | None] = relationship("DeviceSession", back_populates="audit_logs")

    @classmethod
    def log_action(cls, action_type: str, action_result: str = "success", **kwargs):
        log = cls(
            action_type=action_type,
            action_result=action_result,
            user_id=kwargs.get("user_id"),
            device_id=kwargs.get("device_id"),
            admin_id=kwargs.get("admin_id"),
            ip_address=kwargs.get("ip_address"),
            apk_version=kwargs.get("apk_version"),
            session_id=kwargs.get("session_id"),
            details=kwargs.get("details"),
        )
        db.session.add(log)
        db.session.commit()
        return log

    @classmethod
    def get_device_history(cls, device_id: int, limit: int = 50):
        return (
            cls.query.filter_by(device_id=device_id)
            .order_by(cls.occurred_at.desc())
            .limit(limit)
            .all()
        )

class RetiradaFerramenta(db.Model):
    """Controle de retirada temporária de ferramentas com devolução obrigatória."""
    
    __tablename__ = "retiradas_ferramentas"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo_item: Mapped[str] = mapped_column(ForeignKey("itens.codigo_item"), nullable=False)
    matricula: Mapped[str] = mapped_column(ForeignKey("usuarios.matricula"), nullable=False)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    local_servico: Mapped[str | None] = mapped_column(Text, nullable=True)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    data_retirada: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    data_devolucao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    data_prevista_devolucao: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    status: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default='em_uso'
    )  # em_uso, devolvida, atrasada, para_reparo
    
    observacao_devolucao: Mapped[str | None] = mapped_column(Text, nullable=True)
    observacao_reparo: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Relationships
    item: Mapped[Item] = relationship("Item")
    usuario: Mapped[Usuario] = relationship("Usuario")
    
    __table_args__ = (
        CheckConstraint("status IN ('em_uso', 'devolvida', 'atrasada', 'para_reparo')", name="check_status"),
        CheckConstraint("quantidade > 0", name="check_quantidade_positiva"),
    )
    
    def __init__(self, codigo_item: str, matricula: str, quantidade: int, local_servico: str | None = None, 
                 observacao: str | None = None, data_prevista_devolucao: date | None = None, status: str = 'em_uso'):
        self.codigo_item = codigo_item
        self.matricula = matricula
        self.quantidade = quantidade
        self.local_servico = local_servico
        self.observacao = observacao
        self.data_prevista_devolucao = data_prevista_devolucao
        self.status = status
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "codigo_item": self.codigo_item,
            "descricao": self.item.descricao if self.item else "",
            "matricula": self.matricula,
            "matricula_ultimos5": self.matricula[-5:] if self.matricula and len(self.matricula) >= 5 else self.matricula,
            "nome_usuario": self.usuario.nome if self.usuario else "",
            "quantidade": self.quantidade,
            "local_servico": self.local_servico,
            "observacao": self.observacao,
            "data_retirada": self.data_retirada,
            "data_devolucao": self.data_devolucao,
            "data_prevista_devolucao": self.data_prevista_devolucao,
            "status": self.status,
            "observacao_devolucao": self.observacao_devolucao,
            "observacao_reparo": self.observacao_reparo,
            "dias_em_uso": (datetime.now() - self.data_retirada).days if not self.data_devolucao else 0,
            "esta_atrasada": self.verificar_atraso(),
        }
    
    def verificar_atraso(self) -> bool:
        """Verifica se a ferramenta está atrasada (passou de um dia e não foi devolvida)."""
        if self.status == 'devolvida':
            return False
        if self.data_prevista_devolucao:
            return date.today() > self.data_prevista_devolucao
        # Se não tem data prevista, considera atrasada se passou de 1 dia
        return (datetime.now() - self.data_retirada).days > 0
    
    def registrar_devolucao(self, observacao: str | None = None):
        """Registra a devolução da ferramenta."""
        self.data_devolucao = datetime.now()
        self.status = 'devolvida'
        if observacao:
            self.observacao_devolucao = observacao
    
    def marcar_para_reparo(self, observacao: str):
        """Marca a ferramenta para reparo."""
        self.status = 'para_reparo'
        self.observacao_reparo = observacao
        if not self.data_devolucao:
            self.data_devolucao = datetime.now()


class EntradaRegistro30Dias(db.Model):
    """Controla ciclos de 30 dias de registro de entradas e PDFs gerados."""
    __tablename__ = "entradas_registro_30_dias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    data_fim: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    pdf_gerado: Mapped[bool] = mapped_column(Boolean, default=False)
    pdf_caminho: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_nome_arquivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_geracao_pdf: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    data_criacao: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class PatrimonioFerramenta(db.Model):
    """Códigos patrimoniais individuais para ferramentas.
    
    Relacionamento: 1 Item → MÚLTIPLOS códigos patrimoniais
    Exemplo: 20 furadeiras Bosch = 20 registros (PAT-001 a PAT-020)
    """
    __tablename__ = "patrimonio_ferramentas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo_patrimonial: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    codigo_item: Mapped[str] = mapped_column(ForeignKey("itens.codigo_item", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='disponivel', index=True)
    matricula: Mapped[str | None] = mapped_column(ForeignKey("usuarios.matricula", ondelete="SET NULL"), nullable=True, index=True)
    data_criacao: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Relationships
    item: Mapped[Item | None] = relationship("Item", foreign_keys=[codigo_item])
    usuario: Mapped[Usuario | None] = relationship("Usuario", foreign_keys=[matricula])
    
    __table_args__ = (
        CheckConstraint(status.in_(['disponivel', 'em_uso', 'manutencao', 'baixado']), name='ck_patrimonio_status'),
    )
    
    def to_dict(self) -> dict[str, object]:
        """Converte para dicionário."""
        return {
            "id": self.id,
            "codigo_patrimonial": self.codigo_patrimonial,
            "codigo_item": self.codigo_item,
            "item_descricao": self.item.descricao if self.item else None,
            "status": self.status,
            "matricula": self.matricula,
            "usuario_nome": self.usuario.nome if self.usuario else None,
            "data_criacao": self.data_criacao.isoformat() if self.data_criacao else None,
            "observacao": self.observacao,
        }


class FerramentaEmUso(db.Model):
    """Registra ferramentas que estão em uso por colaboradores (controle patrimonial)."""
    __tablename__ = "ferramentas_em_uso"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo_item: Mapped[str] = mapped_column(ForeignKey("itens.codigo_item", ondelete="CASCADE"), nullable=False)
    codigo_patrimonial: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    matricula: Mapped[str] = mapped_column(ForeignKey("usuarios.matricula", ondelete="CASCADE"), nullable=False)
    data_retirada: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    data_devolucao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    saida_id: Mapped[int | None] = mapped_column(ForeignKey("saidas.id_saida", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='EM_USO', index=True)
    
    # Relationships
    item: Mapped[Item | None] = relationship("Item", foreign_keys=[codigo_item])
    usuario: Mapped[Usuario | None] = relationship("Usuario", foreign_keys=[matricula])
    saida: Mapped[Saida | None] = relationship("Saida", foreign_keys=[saida_id])
    
    def to_dict(self) -> dict[str, object]:
        """Converte para dicionário."""
        return {
            "id": self.id,
            "codigo_item": self.codigo_item,
            "codigo_patrimonial": self.codigo_patrimonial,
            "matricula": self.matricula,
            "usuario_nome": self.usuario.nome if self.usuario else None,
            "item_descricao": self.item.descricao if self.item else None,
            "data_retirada": self.data_retirada.isoformat() if self.data_retirada else None,
            "data_devolucao": self.data_devolucao.isoformat() if self.data_devolucao else None,
            "observacao": self.observacao,
            "saida_id": self.saida_id,
            "status": self.status,
        }


class EmpresaConfig(db.Model):
    """Configurações da empresa (multi-tenant)."""
    __tablename__ = "empresa_config"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Dados da Empresa
    nome_empresa: Mapped[str] = mapped_column(String(200), nullable=False)
    nome_fantasia: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cnpj: Mapped[str | None] = mapped_column(String(18), nullable=True)
    
    # Endereço
    endereco_rua: Mapped[str | None] = mapped_column(String(255), nullable=True)
    endereco_numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    endereco_complemento: Mapped[str | None] = mapped_column(String(100), nullable=True)
    endereco_bairro: Mapped[str | None] = mapped_column(String(100), nullable=True)
    endereco_cidade: Mapped[str | None] = mapped_column(String(100), nullable=True)
    endereco_estado: Mapped[str | None] = mapped_column(String(2), nullable=True)
    endereco_cep: Mapped[str | None] = mapped_column(String(10), nullable=True)
    
    # Contato
    telefone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    telefone_secundario: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(100), nullable=True)
    site: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Logo
    logo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_width: Mapped[int] = mapped_column(Integer, default=150)
    logo_height: Mapped[int] = mapped_column(Integer, default=80)
    
    # Sistema
    primeira_execucao: Mapped[bool] = mapped_column(Boolean, default=True)
    setup_completo: Mapped[bool] = mapped_column(Boolean, default=False)
    versao_instalada: Mapped[str | None] = mapped_column(String(20), nullable=True)
    
    # Metadados
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    def to_dict(self) -> dict[str, object]:
        """Converte para dicionário."""
        return {
            "id": self.id,
            "nome_empresa": self.nome_empresa,
            "nome_fantasia": self.nome_fantasia,
            "cnpj": self.cnpj,
            "endereco_completo": self.get_endereco_completo(),
            "telefone": self.telefone,
            "telefone_secundario": self.telefone_secundario,
            "email": self.email,
            "site": self.site,
            "logo_path": self.logo_path,
            "logo_width": self.logo_width,
            "logo_height": self.logo_height,
            "primeira_execucao": self.primeira_execucao,
            "setup_completo": self.setup_completo,
            "versao_instalada": self.versao_instalada,
        }
    
    def get_endereco_completo(self) -> str:
        """Retorna endereço formatado."""
        partes = []
        
        if self.endereco_rua:
            rua = self.endereco_rua
            if self.endereco_numero:
                rua += f", {self.endereco_numero}"
            if self.endereco_complemento:
                rua += f" - {self.endereco_complemento}"
            partes.append(rua)
        
        if self.endereco_bairro:
            partes.append(self.endereco_bairro)
        
        if self.endereco_cidade and self.endereco_estado:
            partes.append(f"{self.endereco_cidade}/{self.endereco_estado}")
        
        if self.endereco_cep:
            partes.append(f"CEP: {self.endereco_cep}")
        
        return " - ".join(partes) if partes else ""


class RelatorioConfig(db.Model):
    """Configurações de relatórios e templates."""
    __tablename__ = "relatorio_config"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Cabeçalho
    cabecalho_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    cabecalho_altura_mm: Mapped[int] = mapped_column(Integer, default=40)
    cabecalho_mostrar_logo: Mapped[bool] = mapped_column(Boolean, default=True)
    cabecalho_cor_texto: Mapped[str] = mapped_column(String(7), default="#000000")
    cabecalho_fonte: Mapped[str] = mapped_column(String(50), default="Helvetica")
    cabecalho_tamanho_fonte: Mapped[int] = mapped_column(Integer, default=10)
    
    # Rodapé
    rodape_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    rodape_altura_mm: Mapped[int] = mapped_column(Integer, default=20)
    rodape_cor_texto: Mapped[str] = mapped_column(String(7), default="#666666")
    rodape_tamanho_fonte: Mapped[int] = mapped_column(Integer, default=8)
    rodape_mostrar_data: Mapped[bool] = mapped_column(Boolean, default=True)
    rodape_mostrar_pagina: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Estilo Geral
    cor_primaria: Mapped[str] = mapped_column(String(7), default="#007bff")
    cor_secundaria: Mapped[str] = mapped_column(String(7), default="#6c757d")
    cor_sucesso: Mapped[str] = mapped_column(String(7), default="#28a745")
    cor_perigo: Mapped[str] = mapped_column(String(7), default="#dc3545")
    cor_aviso: Mapped[str] = mapped_column(String(7), default="#ffc107")
    fonte_principal: Mapped[str] = mapped_column(String(50), default="Helvetica")
    fonte_tabelas: Mapped[str] = mapped_column(String(50), default="Courier")
    
    # Metadados
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    def to_dict(self) -> dict[str, object]:
        """Converte para dicionário."""
        return {
            "id": self.id,
            "cabecalho_template": self.cabecalho_template,
            "cabecalho_altura_mm": self.cabecalho_altura_mm,
            "cabecalho_mostrar_logo": self.cabecalho_mostrar_logo,
            "cabecalho_cor_texto": self.cabecalho_cor_texto,
            "cabecalho_fonte": self.cabecalho_fonte,
            "cabecalho_tamanho_fonte": self.cabecalho_tamanho_fonte,
            "rodape_template": self.rodape_template,
            "rodape_altura_mm": self.rodape_altura_mm,
            "rodape_cor_texto": self.rodape_cor_texto,
            "rodape_tamanho_fonte": self.rodape_tamanho_fonte,
            "rodape_mostrar_data": self.rodape_mostrar_data,
            "rodape_mostrar_pagina": self.rodape_mostrar_pagina,
            "cor_primaria": self.cor_primaria,
            "cor_secundaria": self.cor_secundaria,
            "fonte_principal": self.fonte_principal,
            "fonte_tabelas": self.fonte_tabelas,
        }


class EquipamentoReparo(db.Model):
    """Gerenciamento de equipamentos enviados para reparo."""
    __tablename__ = "equipamentos_reparo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo_item: Mapped[str] = mapped_column(String, ForeignKey("itens.codigo_item"), nullable=False)
    
    # Responsável e datas
    matricula_responsavel: Mapped[str] = mapped_column(String(100), ForeignKey("usuarios.matricula"), nullable=False)
    data_envio: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    data_retorno: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    prazo_previsto: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    # Detalhes do reparo
    problema_descrito: Mapped[str] = mapped_column(Text, nullable=False)
    solucao_aplicada: Mapped[str | None] = mapped_column(Text, nullable=True)
    fornecedor_oficina: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Custos
    custo_estimado: Mapped[float | None] = mapped_column(Float, nullable=True)
    custo_real: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # Status: aguardando_orcamento, em_reparo, concluido, sem_conserto
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="aguardando_orcamento")
    
    # Observações adicionais
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Timestamps de auditoria
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    atualizado_por: Mapped[str | None] = mapped_column(String(100), ForeignKey("usuarios.matricula"), nullable=True)
    
    # Relacionamentos
    item: Mapped["Item"] = relationship("Item", backref="reparos")
    responsavel: Mapped["Usuario"] = relationship("Usuario", foreign_keys=[matricula_responsavel], backref="reparos_responsavel")
    atualizador: Mapped["Usuario"] = relationship("Usuario", foreign_keys=[atualizado_por], backref="reparos_atualizados")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "codigo_item": self.codigo_item,
            "descricao_item": self.item.descricao if self.item else None,
            "categoria": self.item.categoria if self.item else None,
            "matricula_responsavel": self.matricula_responsavel,
            "responsavel_nome": self.responsavel.name if self.responsavel else None,
            "data_envio": self.data_envio.isoformat() if self.data_envio else None,
            "data_retorno": self.data_retorno.isoformat() if self.data_retorno else None,
            "prazo_previsto": self.prazo_previsto.isoformat() if self.prazo_previsto else None,
            "problema_descrito": self.problema_descrito,
            "solucao_aplicada": self.solucao_aplicada,
            "fornecedor_oficina": self.fornecedor_oficina,
            "custo_estimado": self.custo_estimado,
            "custo_real": self.custo_real,
            "status": self.status,
            "observacoes": self.observacoes,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
            "atualizado_em": self.atualizado_em.isoformat() if self.atualizado_em else None,
            "atualizado_por": self.atualizado_por,
        }
    
    @property
    def dias_em_reparo(self) -> int | None:
        """Calcula dias desde o envio até retorno (ou hoje se ainda em reparo)."""
        if self.data_retorno:
            return (self.data_retorno.date() - self.data_envio.date()).days
        return (datetime.now().date() - self.data_envio.date()).days
    
    @property
    def status_display(self) -> str:
        """Retorna nome legível do status."""
        status_map = {
            "aguardando_orcamento": "Aguardando Orçamento",
            "em_reparo": "Em Reparo",
            "concluido": "Concluído",
            "sem_conserto": "Sem Conserto"
        }
        return status_map.get(self.status, self.status)
