# README - Mensageria Condominial

## Objetivo

Este documento consolida a proposta tecnica do novo modulo de Mensageria Condominial dentro do GALINT.

O foco aqui nao e estoque, ledger, embalagem ou unidade canonica. O foco aqui e um dominio novo, com regras proprias, mas que precisa nascer com o mesmo rigor arquitetural que o GALINT aprendeu a exigir no almoxarifado.

O modulo deve controlar:

- recebimento de encomendas
- vinculacao a morador
- notificacao automatica por canal disponivel
- registro de ciencia do morador
- entrega fisica ao destinatario
- politica de retencao
- trilha auditavel de tudo o que aconteceu

## Veredito arquitetural

O modulo e aprovado com esta linha:

- monolito modular dentro do mesmo backend Flask
- banco autoritativo em PostgreSQL
- tabelas proprias do dominio
- services proprios
- zero dependencia da logica de estoque
- notificacao tratada como efeito colateral, nunca como fonte de verdade

SQLite pode existir apenas como apoio lateral, por exemplo:

- staging
- cache auxiliar
- arquivo morto
- export local

SQLite nao deve ser o banco autoritativo do modulo.

## Principios inegociaveis

1. Package e a verdade do dominio.
2. NotificationAttempt e entrega de canal, nao estado do pacote.
3. PackageEvent e a trilha auditavel.
4. Toda mutacao de estado passa por um unico writer.
5. Concorrencia deve ser tratada no banco com transacao e lock.
6. Morador e entidade propria, nao reaproveitamento semantico de Usuario.

## Fronteira de dominio

O modulo nao deve reutilizar tabelas ou services do estoque para decidir regra de negocio.

Pode reutilizar apenas infraestrutura transversal:

- autenticacao
- usuarios operadores do sistema
- Telegram como canal de entrega
- GalintNotify como inbox/push
- conventions de migration
- conventions de blueprints e services

Não deve reutilizar:

- InventoryEngine
- StockMovement
- StockBalance
- EmbalagemService
- qualquer regra de unidade, saldo ou conversão de item

## Máquina de estados

### Regra central

Não colapsar tudo em um único enum gigante.

Se o sistema misturar no mesmo status:

- pacote recebido
- notificação enviada
- ciência do morador
- entrega fisica

o modulo rapidamente fica inconsistente.

### Status principal do pacote

O status principal deve ser curto e refletir apenas a situacao de posse operacional do pacote.

```python
from enum import Enum


class PackageStatus(str, Enum):
    RECEBIDO = "RECEBIDO"
    ENTREGUE = "ENTREGUE"
    RETIDO = "RETIDO"
    ARQUIVADO = "ARQUIVADO"
```

### Estado derivado e nao principal

Estes conceitos nao precisam ser status principal:

- NOTIFICADO
- CIENTE
- DISPONIVEL_PARA_RETIRADA

Eles devem ser derivados assim:

- notificado: existe tentativa enviada com sucesso
- ciente: `acknowledged_at` preenchido
- disponivel para retirada: `status == RECEBIDO`

### Eventos do pacote

```python
class PackageEventType(str, Enum):
    RECEBIDO = "RECEBIDO"
    NOTIFICACAO_ENFILEIRADA = "NOTIFICACAO_ENFILEIRADA"
    NOTIFICACAO_ENVIADA = "NOTIFICACAO_ENVIADA"
    NOTIFICACAO_FALHOU = "NOTIFICACAO_FALHOU"
    CIENCIA_REGISTRADA = "CIENCIA_REGISTRADA"
    ENTREGA_CONFIRMADA = "ENTREGA_CONFIRMADA"
    RETENCAO_APLICADA = "RETENCAO_APLICADA"
    ARQUIVAMENTO_REALIZADO = "ARQUIVAMENTO_REALIZADO"
```

### Status das tentativas de notificacao

```python
class NotificationAttemptStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    DEAD = "DEAD"
    SKIPPED = "SKIPPED"
```

### Tags de retencao

```python
class RetentionTag(str, Enum):
    ANTIGO = "ANTIGO"
    ABANDONO = "ABANDONO"
    MORADOR_INATIVO = "MORADOR_INATIVO"
```

### Fontes do evento

```python
class EventSource(str, Enum):
    WEB = "WEB"
    API = "API"
    TELEGRAM = "TELEGRAM"
    NOTIFY = "NOTIFY"
    JOB = "JOB"
```

### Transicoes validas

As transicoes de status principal devem ser estas:

1. RECEBIDO -> ENTREGUE
2. RECEBIDO -> RETIDO
3. RETIDO -> ENTREGUE
4. ENTREGUE -> ARQUIVADO
5. RETIDO -> ARQUIVADO

Eventos que nao trocam o status principal:

1. registrar ciencia
2. enfileirar notificacao
3. marcar notificacao como enviada
4. marcar notificacao como falha
5. reagendar notificacao

## Modelagem relacional

### 1. condo_residents

Tabela de moradores.

Campos minimos:

- `id BIGSERIAL PRIMARY KEY`
- `nome VARCHAR(160) NOT NULL`
- `bloco VARCHAR(30) NULL`
- `unidade VARCHAR(30) NOT NULL`
- `telefone VARCHAR(40) NULL`
- `documento VARCHAR(30) NULL`
- `ativo BOOLEAN NOT NULL DEFAULT TRUE`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### 2. condo_resident_notification_prefs

Politica de notificacao por morador.

Campos minimos:

- `resident_id BIGINT PRIMARY KEY REFERENCES condo_residents(id) ON DELETE CASCADE`
- `telegram_enabled BOOLEAN NOT NULL DEFAULT TRUE`
- `notify_enabled BOOLEAN NOT NULL DEFAULT FALSE`
- `reminder_after_hours INTEGER NOT NULL DEFAULT 24`
- `max_reminders INTEGER NOT NULL DEFAULT 3`
- `retention_days INTEGER NOT NULL DEFAULT 7`
- `quiet_hours_json JSONB NULL`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Importante:

- essa preferencia nao pertence ao `Package`
- o pacote nao deve carregar a verdade do canal

### 3. condo_resident_channels

Tabela de enderecos de canal por morador.

Campos minimos:

- `id BIGSERIAL PRIMARY KEY`
- `resident_id BIGINT NOT NULL REFERENCES condo_residents(id) ON DELETE CASCADE`
- `channel_type VARCHAR(20) NOT NULL`
- `external_address VARCHAR(255) NOT NULL`
- `verified BOOLEAN NOT NULL DEFAULT FALSE`
- `enabled BOOLEAN NOT NULL DEFAULT TRUE`
- `last_seen_at TIMESTAMPTZ NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Restricao:

- `UNIQUE (resident_id, channel_type, external_address)`

Uso:

- Telegram `chat_id`
- identificador do inbox/app
- outros canais futuros

### 4. condo_packages

Tabela principal do dominio.

Campos minimos:

- `id BIGSERIAL PRIMARY KEY`
- `resident_id BIGINT NOT NULL REFERENCES condo_residents(id)`
- `codigo_barras VARCHAR(120) NULL`
- `tracking_code VARCHAR(120) NULL`
- `carrier_name VARCHAR(80) NULL`
- `origin_label VARCHAR(80) NULL`
- `status VARCHAR(30) NOT NULL`
- `acknowledged_at TIMESTAMPTZ NULL`
- `delivered_at TIMESTAMPTZ NULL`
- `retained_at TIMESTAMPTZ NULL`
- `archived_at TIMESTAMPTZ NULL`
- `retention_tag VARCHAR(30) NULL`
- `notes TEXT NULL`
- `received_by_user_id VARCHAR(32) NOT NULL REFERENCES usuarios(matricula)`
- `delivered_by_user_id VARCHAR(32) NULL REFERENCES usuarios(matricula)`
- `version INTEGER NOT NULL DEFAULT 1`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Indices recomendados:

- `(status, created_at)`
- `(resident_id, status)`
- `(tracking_code)`
- `(codigo_barras)`

Observacoes:

- `tracking_code` nao precisa ser unico global obrigatorio
- `version` existe para apoiar controle otimista quando fizer sentido

### 5. condo_package_events

Tabela de trilha auditavel do pacote.

Campos minimos:

- `id BIGSERIAL PRIMARY KEY`
- `package_id BIGINT NOT NULL REFERENCES condo_packages(id) ON DELETE CASCADE`
- `event_type VARCHAR(40) NOT NULL`
- `from_status VARCHAR(30) NULL`
- `to_status VARCHAR(30) NULL`
- `actor_type VARCHAR(20) NOT NULL`
- `actor_user_id VARCHAR(32) NULL REFERENCES usuarios(matricula)`
- `actor_resident_id BIGINT NULL REFERENCES condo_residents(id)`
- `source VARCHAR(20) NOT NULL`
- `idempotency_key VARCHAR(120) NULL`
- `payload_json JSONB NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Restricao recomendada:

- `UNIQUE (idempotency_key)`

### 6. condo_package_notification_attempts

Tabela de outbox/tentativas de entrega.

Campos minimos:

- `id BIGSERIAL PRIMARY KEY`
- `package_id BIGINT NOT NULL REFERENCES condo_packages(id) ON DELETE CASCADE`
- `purpose VARCHAR(30) NOT NULL`
- `channel VARCHAR(20) NOT NULL`
- `status VARCHAR(20) NOT NULL`
- `idempotency_key VARCHAR(120) NOT NULL`
- `recipient_address VARCHAR(255) NULL`
- `attempt_count INTEGER NOT NULL DEFAULT 0`
- `next_retry_at TIMESTAMPTZ NULL`
- `last_attempt_at TIMESTAMPTZ NULL`
- `sent_at TIMESTAMPTZ NULL`
- `stopped_at TIMESTAMPTZ NULL`
- `provider_message_id VARCHAR(120) NULL`
- `error_message TEXT NULL`
- `payload_json JSONB NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Restricao recomendada:

- `UNIQUE (idempotency_key)`

Indice recomendado:

- `(status, next_retry_at)`

### 7. condo_messaging_config

Configuracao global do modulo.

Campos minimos:

- `id SMALLINT PRIMARY KEY`
- `reminder_policy_json JSONB NOT NULL`
- `retention_days INTEGER NOT NULL DEFAULT 7`
- `archive_after_days INTEGER NOT NULL DEFAULT 30`
- `updated_by_user_id VARCHAR(32) NULL REFERENCES usuarios(matricula)`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

## 1. Models SQLAlchemy iniciais

O modulo pode nascer em um arquivo proprio, por exemplo:

- `galint_flask/models_condominial.py`

Esqueleto inicial:

```python
from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db


class PackageStatus(str, Enum):
    RECEBIDO = "RECEBIDO"
    ENTREGUE = "ENTREGUE"
    RETIDO = "RETIDO"
    ARQUIVADO = "ARQUIVADO"


class CondoResident(db.Model):
    __tablename__ = "condo_residents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    bloco: Mapped[str | None] = mapped_column(String(30), nullable=True)
    unidade: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    telefone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    documento: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class CondoResidentNotificationPrefs(db.Model):
    __tablename__ = "condo_resident_notification_prefs"

    resident_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("condo_residents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reminder_after_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    max_reminders: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    quiet_hours_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    resident: Mapped[CondoResident] = relationship("CondoResident", backref="notification_prefs", uselist=False)


class CondoResidentChannel(db.Model):
    __tablename__ = "condo_resident_channels"
    __table_args__ = (
        UniqueConstraint("resident_id", "channel_type", "external_address", name="uq_condo_resident_channel"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    resident_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("condo_residents.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    external_address: Mapped[str] = mapped_column(String(255), nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(db.DateTime, nullable=False, default=datetime.utcnow)

    resident: Mapped[CondoResident] = relationship("CondoResident", backref="channels")


class CondoPackage(db.Model):
    __tablename__ = "condo_packages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    resident_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("condo_residents.id"), nullable=False, index=True)
    codigo_barras: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    tracking_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    carrier_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    origin_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    retained_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    retention_tag: Mapped[str | None] = mapped_column(String(30), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_by_user_id: Mapped[str] = mapped_column(String(32), ForeignKey("usuarios.matricula"), nullable=False)
    delivered_by_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("usuarios.matricula"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    resident: Mapped[CondoResident] = relationship("CondoResident", backref="packages")


class CondoPackageEvent(db.Model):
    __tablename__ = "condo_package_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("condo_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("usuarios.matricula"), nullable=True)
    actor_resident_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("condo_residents.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    package: Mapped[CondoPackage] = relationship("CondoPackage", backref="events")


class CondoPackageNotificationAttempt(db.Model):
    __tablename__ = "condo_package_notification_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("condo_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    recipient_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True, index=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(db.DateTime, nullable=False, default=datetime.utcnow)

    package: Mapped[CondoPackage] = relationship("CondoPackage", backref="notification_attempts")


class CondoMessagingConfig(db.Model):
    __tablename__ = "condo_messaging_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reminder_policy_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    archive_after_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    updated_by_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("usuarios.matricula"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
```

## 2. Migration Alembic inicial

Arquivo sugerido:

- `migrations/versions/<id>_create_condo_messaging_tables.py`

Esqueleto inicial:

```python
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "xxxx_create_condo_messaging_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "condo_residents",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("nome", sa.String(length=160), nullable=False),
        sa.Column("bloco", sa.String(length=30), nullable=True),
        sa.Column("unidade", sa.String(length=30), nullable=False),
        sa.Column("telefone", sa.String(length=40), nullable=True),
        sa.Column("documento", sa.String(length=30), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_condo_residents_unidade", "condo_residents", ["unidade"])
    op.create_index("ix_condo_residents_ativo", "condo_residents", ["ativo"])

    op.create_table(
        "condo_resident_notification_prefs",
        sa.Column("resident_id", sa.BigInteger(), sa.ForeignKey("condo_residents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("telegram_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notify_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reminder_after_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("max_reminders", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("quiet_hours_json", postgresql.JSONB(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "condo_resident_channels",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("resident_id", sa.BigInteger(), sa.ForeignKey("condo_residents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_type", sa.String(length=20), nullable=False),
        sa.Column("external_address", sa.String(length=255), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("resident_id", "channel_type", "external_address", name="uq_condo_resident_channel"),
    )
    op.create_index("ix_condo_resident_channels_resident_id", "condo_resident_channels", ["resident_id"])

    op.create_table(
        "condo_packages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("resident_id", sa.BigInteger(), sa.ForeignKey("condo_residents.id"), nullable=False),
        sa.Column("codigo_barras", sa.String(length=120), nullable=True),
        sa.Column("tracking_code", sa.String(length=120), nullable=True),
        sa.Column("carrier_name", sa.String(length=80), nullable=True),
        sa.Column("origin_label", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retention_tag", sa.String(length=30), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("received_by_user_id", sa.String(length=32), sa.ForeignKey("usuarios.matricula"), nullable=False),
        sa.Column("delivered_by_user_id", sa.String(length=32), sa.ForeignKey("usuarios.matricula"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_condo_packages_status_created_at", "condo_packages", ["status", "created_at"])
    op.create_index("ix_condo_packages_resident_status", "condo_packages", ["resident_id", "status"])
    op.create_index("ix_condo_packages_tracking_code", "condo_packages", ["tracking_code"])
    op.create_index("ix_condo_packages_codigo_barras", "condo_packages", ["codigo_barras"])

    op.create_table(
        "condo_package_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("package_id", sa.BigInteger(), sa.ForeignKey("condo_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=True),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.String(length=32), sa.ForeignKey("usuarios.matricula"), nullable=True),
        sa.Column("actor_resident_id", sa.BigInteger(), sa.ForeignKey("condo_residents.id"), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True, unique=True),
        sa.Column("payload_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_condo_package_events_package_id", "condo_package_events", ["package_id"])
    op.create_index("ix_condo_package_events_event_type", "condo_package_events", ["event_type"])

    op.create_table(
        "condo_package_notification_attempts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("package_id", sa.BigInteger(), sa.ForeignKey("condo_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False, unique=True),
        sa.Column("recipient_address", sa.String(length=255), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_condo_package_notification_attempts_status_retry", "condo_package_notification_attempts", ["status", "next_retry_at"])

    op.create_table(
        "condo_messaging_config",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("reminder_policy_json", postgresql.JSONB(), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("archive_after_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("updated_by_user_id", sa.String(length=32), sa.ForeignKey("usuarios.matricula"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade():
    op.drop_table("condo_messaging_config")
    op.drop_index("ix_condo_package_notification_attempts_status_retry", table_name="condo_package_notification_attempts")
    op.drop_table("condo_package_notification_attempts")
    op.drop_index("ix_condo_package_events_event_type", table_name="condo_package_events")
    op.drop_index("ix_condo_package_events_package_id", table_name="condo_package_events")
    op.drop_table("condo_package_events")
    op.drop_index("ix_condo_packages_codigo_barras", table_name="condo_packages")
    op.drop_index("ix_condo_packages_tracking_code", table_name="condo_packages")
    op.drop_index("ix_condo_packages_resident_status", table_name="condo_packages")
    op.drop_index("ix_condo_packages_status_created_at", table_name="condo_packages")
    op.drop_table("condo_packages")
    op.drop_index("ix_condo_resident_channels_resident_id", table_name="condo_resident_channels")
    op.drop_table("condo_resident_channels")
    op.drop_table("condo_resident_notification_prefs")
    op.drop_index("ix_condo_residents_ativo", table_name="condo_residents")
    op.drop_index("ix_condo_residents_unidade", table_name="condo_residents")
    op.drop_table("condo_residents")
```

## 3. Servico transacional unico com controle de concorrencia

O modulo deve ter um unico writer. Nada de controller mudando status diretamente e nada de servico de notificacao alterando o pacote.

Arquivo sugerido:

- `galint_flask/services/condo_package_service.py`

### Estrategia obrigatoria

1. toda mutacao principal usa transacao unica
2. toda mutacao principal gera `CondoPackageEvent`
3. notificacao entra como tentativa pendente, nao envio inline obrigatorio
4. leitura e envio de notificacao rodam fora da transacao de negocio
5. entrega e retencao usam lock no pacote

### Esqueleto inicial

```python
from __future__ import annotations

from datetime import datetime, timedelta

from ..extensions import db
from ..models_condominial import (
    CondoMessagingConfig,
    CondoPackage,
    CondoPackageEvent,
    CondoPackageNotificationAttempt,
    CondoResident,
    CondoResidentChannel,
    CondoResidentNotificationPrefs,
    EventSource,
    NotificationAttemptStatus,
    PackageEventType,
    PackageStatus,
    RetentionTag,
)


class CondoPackageService:
    @staticmethod
    def receive_package(
        *,
        resident_id: int,
        operator_id: str,
        codigo_barras: str | None,
        tracking_code: str | None,
        carrier_name: str | None,
        origin_label: str | None,
        notes: str | None,
    ) -> int:
        now = datetime.utcnow()

        with db.session.begin():
            resident = CondoResident.query.filter_by(id=resident_id, ativo=True).first()
            if not resident:
                raise ValueError("Morador nao encontrado ou inativo")

            package = CondoPackage(
                resident_id=resident_id,
                codigo_barras=(codigo_barras or "").strip() or None,
                tracking_code=(tracking_code or "").strip() or None,
                carrier_name=(carrier_name or "").strip() or None,
                origin_label=(origin_label or "").strip() or None,
                status=PackageStatus.RECEBIDO.value,
                notes=(notes or "").strip() or None,
                received_by_user_id=operator_id,
                version=1,
            )
            db.session.add(package)
            db.session.flush()

            db.session.add(
                CondoPackageEvent(
                    package_id=package.id,
                    event_type=PackageEventType.RECEBIDO.value,
                    from_status=None,
                    to_status=PackageStatus.RECEBIDO.value,
                    actor_type="OPERATOR",
                    actor_user_id=operator_id,
                    source=EventSource.WEB.value,
                    payload_json={
                        "codigo_barras": package.codigo_barras,
                        "tracking_code": package.tracking_code,
                        "carrier_name": package.carrier_name,
                        "origin_label": package.origin_label,
                    },
                )
            )

            prefs = CondoResidentNotificationPrefs.query.filter_by(resident_id=resident_id).first()
            channel = CondoResidentChannel.query.filter_by(
                resident_id=resident_id,
                channel_type="TELEGRAM",
                enabled=True,
                verified=True,
            ).first()

            if prefs and prefs.telegram_enabled and channel:
                db.session.add(
                    CondoPackageNotificationAttempt(
                        package_id=package.id,
                        purpose="INITIAL",
                        channel="TELEGRAM",
                        status=NotificationAttemptStatus.PENDING.value,
                        idempotency_key=f"pkg:{package.id}:initial:telegram",
                        recipient_address=channel.external_address,
                        next_retry_at=now,
                        payload_json={
                            "template": "package_received",
                            "resident_id": resident_id,
                            "package_id": package.id,
                        },
                    )
                )

        return package.id

    @staticmethod
    def acknowledge_package(*, package_id: int, resident_id: int, source: str, idempotency_key: str) -> None:
        now = datetime.utcnow()

        with db.session.begin():
            duplicate = CondoPackageEvent.query.filter_by(idempotency_key=idempotency_key).first()
            if duplicate:
                return

            package = (
                CondoPackage.query
                .filter_by(id=package_id)
                .with_for_update()
                .first()
            )
            if not package:
                raise ValueError("Pacote nao encontrado")

            if package.resident_id != resident_id:
                raise ValueError("Morador incompatível com o pacote")

            if package.status in {PackageStatus.ENTREGUE.value, PackageStatus.ARQUIVADO.value}:
                raise ValueError("Pacote ja encerrado")

            if package.acknowledged_at is None:
                package.acknowledged_at = now
                package.version += 1

                db.session.add(
                    CondoPackageEvent(
                        package_id=package.id,
                        event_type=PackageEventType.CIENCIA_REGISTRADA.value,
                        from_status=package.status,
                        to_status=package.status,
                        actor_type="RESIDENT",
                        actor_resident_id=resident_id,
                        source=source,
                        idempotency_key=idempotency_key,
                        payload_json=None,
                    )
                )

    @staticmethod
    def deliver_package(*, package_id: int, operator_id: str, idempotency_key: str) -> None:
        now = datetime.utcnow()

        with db.session.begin():
            duplicate = CondoPackageEvent.query.filter_by(idempotency_key=idempotency_key).first()
            if duplicate:
                return

            package = (
                CondoPackage.query
                .filter_by(id=package_id)
                .with_for_update()
                .first()
            )
            if not package:
                raise ValueError("Pacote nao encontrado")

            if package.status not in {PackageStatus.RECEBIDO.value, PackageStatus.RETIDO.value}:
                raise ValueError("Pacote nao esta disponivel para entrega")

            previous_status = package.status
            package.status = PackageStatus.ENTREGUE.value
            package.delivered_at = now
            package.delivered_by_user_id = operator_id
            package.version += 1

            db.session.add(
                CondoPackageEvent(
                    package_id=package.id,
                    event_type=PackageEventType.ENTREGA_CONFIRMADA.value,
                    from_status=previous_status,
                    to_status=PackageStatus.ENTREGUE.value,
                    actor_type="OPERATOR",
                    actor_user_id=operator_id,
                    source=EventSource.WEB.value,
                    idempotency_key=idempotency_key,
                    payload_json=None,
                )
            )

    @staticmethod
    def retain_expired_packages(*, operator_id: str | None = None, batch_size: int = 100) -> int:
        now = datetime.utcnow()
        config = CondoMessagingConfig.query.get(1)
        if not config:
            raise ValueError("Configuracao condominial ausente")

        cutoff = now - timedelta(days=config.retention_days)

        with db.session.begin():
            packages = (
                CondoPackage.query
                .filter(
                    CondoPackage.status == PackageStatus.RECEBIDO.value,
                    CondoPackage.created_at <= cutoff,
                )
                .with_for_update(skip_locked=True)
                .limit(batch_size)
                .all()
            )

            for package in packages:
                package.status = PackageStatus.RETIDO.value
                package.retained_at = now
                package.retention_tag = RetentionTag.ANTIGO.value
                package.version += 1

                db.session.add(
                    CondoPackageEvent(
                        package_id=package.id,
                        event_type=PackageEventType.RETENCAO_APLICADA.value,
                        from_status=PackageStatus.RECEBIDO.value,
                        to_status=PackageStatus.RETIDO.value,
                        actor_type="SYSTEM",
                        actor_user_id=operator_id,
                        source=EventSource.JOB.value,
                        payload_json={"cutoff": cutoff.isoformat()},
                    )
                )

            return len(packages)
```

### Por que este service e o centro do modulo

Porque ele impede os erros classicos:

1. dois operadores entregando o mesmo pacote ao mesmo tempo
2. job de retencao brigando com entrega manual
3. Telegram alterando estado do pacote
4. frontend mudando status por conta propria
5. callback duplicado registrando ciencia duas vezes

### Controle de concorrencia recomendado

1. `SELECT ... FOR UPDATE` nas mutacoes unitarias
2. `FOR UPDATE SKIP LOCKED` nos jobs em lote
3. `idempotency_key` nos callbacks e confirmacoes externas
4. `version` para suporte a controle otimista quando necessario

## 4. Blueprint Flask inicial

Arquivo sugerido:

- `galint_flask/views/condominial.py`

O blueprint deve continuar fino. Ele valida entrada, chama o service e devolve resposta. Ele nao decide regra de estado.

### Esqueleto inicial

```python
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ..services.condo_package_service import CondoPackageService


blueprint = Blueprint("condominial", __name__, url_prefix="/condominial")


@blueprint.post("/packages/receive")
@login_required
def receive_package():
    payload = request.get_json() or {}
    package_id = CondoPackageService.receive_package(
        resident_id=int(payload.get("resident_id")),
        operator_id=str(current_user.matricula),
        codigo_barras=payload.get("codigo_barras"),
        tracking_code=payload.get("tracking_code"),
        carrier_name=payload.get("carrier_name"),
        origin_label=payload.get("origin_label"),
        notes=payload.get("notes"),
    )
    return jsonify({"success": True, "package_id": package_id})


@blueprint.post("/packages/<int:package_id>/deliver")
@login_required
def deliver_package(package_id: int):
    payload = request.get_json() or {}
    CondoPackageService.deliver_package(
        package_id=package_id,
        operator_id=str(current_user.matricula),
        idempotency_key=str(payload.get("idempotency_key") or f"deliver:{package_id}:{current_user.matricula}"),
    )
    return jsonify({"success": True, "package_id": package_id})


@blueprint.post("/packages/<int:package_id>/acknowledge")
def acknowledge_package(package_id: int):
    payload = request.get_json() or {}
    CondoPackageService.acknowledge_package(
        package_id=package_id,
        resident_id=int(payload.get("resident_id")),
        source=str(payload.get("source") or "API"),
        idempotency_key=str(payload.get("idempotency_key")),
    )
    return jsonify({"success": True, "package_id": package_id})


@blueprint.post("/internal/retention/run")
@login_required
def run_retention():
    processed = CondoPackageService.retain_expired_packages(operator_id=str(current_user.matricula))
    return jsonify({"success": True, "processed": processed})
```

### Observacoes sobre o blueprint

1. `acknowledge` nao deve depender do login do operador se a confirmacao vier do morador por link assinado, app proprio ou callback confiavel
2. as rotas de leitura podem ser separadas em web e API depois
3. a rota de retencao pode migrar para CLI, scheduler ou worker dedicado sem mudar o service

## Checklist de implementacao segura

Antes de subir esse modulo em producao, validar:

1. tabela de moradores criada e separada de `usuarios`
2. pacote sem atributo de canal como verdade principal
3. transacoes com lock nas mutacoes principais
4. outbox de notificacao separado do status do pacote
5. idempotencia em callbacks externos
6. jobs em lote usando `skip_locked`
7. trilha de eventos auditavel desde o primeiro dia
8. politica de retencao configuravel e visivel no painel

## Decisao final deste documento

O modulo condominial deve nascer assim:

- PostgreSQL como banco autoritativo
- Package como verdade do dominio
- PackageEvent como trilha
- NotificationAttempt como efeito colateral controlado
- PackageService como unico writer
- Blueprint fino

Se qualquer parte disso for afrouxada, o modulo tende a repetir no dominio condominial o mesmo tipo de ambiguidade semantica que o GALINT ja precisou corrigir no dominio de estoque.