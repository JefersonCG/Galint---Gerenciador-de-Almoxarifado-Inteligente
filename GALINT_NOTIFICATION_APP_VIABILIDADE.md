# GALINT Notification App - Estudo de Viabilidade (SOMENTE LEITURA)

## 📋 Sumário Executivo

Este documento apresenta um estudo de viabilidade completo para criação de um **aplicativo nativo de notificações e consulta** para o sistema GALINT, operando exclusivamente em rede interna, como alternativa ao uso do Telegram Bot.

**⚠️ ESCOPO DEFINIDO - SOMENTE 3 FUNCIONALIDADES:**
1. 🔔 **Receber notificações** de saídas e retiradas (visualização apenas)
2. 📸 **Pesquisar estoque** via scanner de código de barras (consulta apenas)
3. 📊 **Baixar TODOS os relatórios** disponíveis no sistema (PDF)

**❌ O QUE ESTE APP NÃO FAZ:**
- Registro de entradas (use GALINT Mobile)
- Registro de saídas (use GALINT Mobile)
- Registro de devoluções (use GALINT Mobile)
- Alteração de dados (app é READ-ONLY)

### Objetivo Principal
Desenvolver um APK Android dedicado para **monitoramento e consulta** do almoxarifado com funcionalidades de:
- ✅ Recebimento de notificações push em tempo real (retiradas/saídas apenas - VISUALIZAÇÃO)
- ✅ Consulta de estoque via câmera (código de barras/QR Code) - SOMENTE CONSULTA
- ✅ Download de todos os relatórios disponíveis no sistema (PDF)
- ✅ Visualização de histórico de movimentações
- ❌ **NÃO faz** registro de entradas/saídas (isso permanece no GALINT Mobile)

---

## 🎯 Visão Geral do Sistema

### Contexto Atual
**Sistema Existente:**
- **GALINT Mobile**: App React Native para gestão de estoque (entradas/saídas/custódia)
- **GALINT Backend**: Flask/Python com PostgreSQL
- **Telegram Bot**: Sistema de notificações via API do Telegram

**Motivação para App Nativo:**
1. **Independência de serviços externos** (Telegram)
2. **Controle total sobre dados** sensíveis
3. **Funcionalidade offline/rede interna** sem internet
4. **Personalização completa** da experiência do usuário
5. **Foco em monitoramento** sem comprometer operações (apenas leitura)

**⚠️ IMPORTANTE - Separação de Responsabilidades:**
- **GALINT Mobile**: Registra entradas, saídas, devoluções, custódia (OPERACIONAL)
- **GALINT Notification App**: Monitora, consulta, recebe alertas (INFORMACIONAL)

### Escopo do Novo App

```
┌─────────────────────────────────────────────────┐
│      GALINT Notification App (SOMENTE LEITURA)  │
│                                                 │
│  📱 Aplicativo Android Nativo                   │
│  🔒 Rede Interna (LAN/Wi-Fi)                   │
│  🔔 Notificações (Retiradas/Saídas)            │
│  📸 Scanner (Consulta de Estoque)              │
│  📊 Download de Relatórios (PDF)               │
│  📜 Visualização de Histórico                  │
│  👤 Autenticação via Token JWT                  │
│                                                 │
│  ❌ NÃO REGISTRA ENTRADAS/SAÍDAS               │
└─────────────────────────────────────────────────┘
         │                     │
         │                     │
         ▼                     ▼
┌──────────────┐      ┌──────────────┐
│ GALINT Flask │      │  PostgreSQL  │
│   Backend    │◄────►│   Database   │
│  (REST API)  │      │ (READ-ONLY)  │
└──────────────┘      └──────────────┘
         ▲
         │
         │ (Registros via GALINT Mobile)
         │
┌──────────────┐
│ GALINT Mobile│
│   (React     │
│   Native)    │
└──────────────┘
```

---

## 🏗️ Arquitetura Proposta

### 1. Stack Tecnológico Recomendado

#### **Opção A: React Native (Recomendado)**
**Vantagens:**
- ✅ Reutilização de 70%+ do código do GALINT Mobile existente
- ✅ Equipe já familiarizada com a tecnologia
- ✅ Compartilhamento de componentes (Camera, Scanner, Login)
- ✅ Desenvolvimento mais rápido (2-3 semanas)
- ✅ Manutenção unificada
- ✅ Suporte a notificações push nativas

**Stack Completa:**
```javascript
// Frontend
- React Native 0.73+
- TypeScript
- React Navigation
- Axios (HTTP Client)
- AsyncStorage (Cache local)
- react-native-vision-camera (Câmera)
- react-native-barcode-scanner
- expo-notifications (Push local)
- socket.io-client (WebSocket)

// Backend (Já existe)
- Flask + Flask-SocketIO (WebSocket)
- JWT Authentication
- PostgreSQL
```

#### **Opção B: Flutter**
**Vantagens:**
- ✅ Performance superior (compilado nativo)
- ✅ UI extremamente fluida
- ❌ Equipe precisa aprender nova tecnologia
- ❌ Desenvolvimento mais lento (6-8 semanas)
- ⚠️ Não compartilha código com GALINT Mobile

#### **Opção C: Kotlin Nativo**
**Vantagens:**
- ✅ Performance máxima
- ✅ Acesso total APIs Android
- ❌ Desenvolvimento mais demorado (8-12 semanas)
- ❌ Curva de aprendizado alta
- ❌ Zero reuso de código

### **🎖️ Decisão Recomendada: React Native**
**Motivo:** Melhor relação custo-benefício, reaproveitamento de código e conhecimento da equipe.

---

## 📡 Arquitetura de Notificações

### Sistema de Push Notifications (Rede Interna)

Existem 3 abordagens viáveis:

#### **1. WebSocket + Background Service (Recomendado)**

```
┌──────────────┐                    ┌──────────────┐
│    Flask     │                    │   Android    │
│   Backend    │                    │     App      │
│              │                    │              │
│ ┌──────────┐ │   WebSocket WSS   │ ┌──────────┐ │
│ │SocketIO  │◄├────────────────────┤►│ Socket   │ │
│ │ Server   │ │  (10.0.0.245:5000)│ │ Client   │ │
│ └──────────┘ │                    │ └──────────┘ │
│              │                    │      │       │
│              │   Event emitted    │      ▼       │
│              │   "new_withdrawal" │ ┌──────────┐ │
│              │                    │ │Background│ │
│              │                    │ │ Service  │ │
│              │                    │ └────┬─────┘ │
│              │                    │      │       │
│              │                    │      ▼       │
│              │                    │ ┌──────────┐ │
│              │                    │ │  Native  │ │
│              │                    │ │  Notif.  │ │
│              │                    │ └──────────┘ │
└──────────────┘                    └──────────────┘
```

**Implementação:**

```python
# Backend: galint_flask/notification_service.py
from flask_socketio import SocketIO, emit, join_room

socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on('connect')
def handle_connect():
    user_id = request.args.get('user_id')
    join_room(f'user_{user_id}')
    emit('connected', {'status': 'ok'})

def notify_withdrawal(saida_ids: list[int], user_id: str):
    """Envia notificação via WebSocket"""
    notification_data = {
        'type': 'withdrawal',
        'title': 'Nova Retirada',
        'body': f'{len(saida_ids)} item(ns) retirado(s)',
        'data': {
            'saida_ids': saida_ids,
            'timestamp': datetime.utcnow().isoformat()
        }
    }
    socketio.emit('notification', notification_data, room=f'user_{user_id}')
```

```typescript
// App: services/NotificationService.ts
import io from 'socket.io-client';
import notifee from '@notifee/react-native';
import BackgroundService from 'react-native-background-actions';

class NotificationService {
  private socket: any;
  
  async initialize(userId: string, token: string) {
    // Conectar ao WebSocket
    this.socket = io('ws://10.0.0.245:5000', {
      auth: { token },
      query: { user_id: userId },
      transports: ['websocket']
    });
    
    // Ouvir eventos
    this.socket.on('notification', async (data: any) => {
      await this.displayNotification(data);
    });
    
    // Iniciar serviço em background
    await BackgroundService.start(this.backgroundTask, {
      taskName: 'GALINT Notifications',
      taskTitle: 'GALINT',
      taskDesc: 'Monitorando notificações...',
      taskIcon: { name: 'ic_launcher' }
    });
  }
  
  private async displayNotification(data: any) {
    await notifee.displayNotification({
      title: data.title,
      body: data.body,
      android: {
        channelId: 'galint-notifications',
        importance: AndroidImportance.HIGH,
        pressAction: {
          id: 'default',
          launchActivity: 'default'
        },
        smallIcon: 'ic_notification',
        color: '#2563eb',
        vibrationPattern: [300, 500],
        sound: 'default'
      },
      data: data.data
    });
  }
  
  private backgroundTask = async (taskData: any) => {
    await new Promise(async (resolve) => {
      // Mantém conexão ativa mesmo em background
      while (BackgroundService.isRunning()) {
        if (!this.socket.connected) {
          this.socket.connect();
        }
        await new Promise(r => setTimeout(r, 30000)); // Check a cada 30s
      }
    });
  };
}

export default new NotificationService();
```

**Vantagens:**
- ✅ Funciona 100% em rede interna (sem internet)
- ✅ Notificações em tempo real (< 1 segundo)
- ✅ Persistente mesmo com app em background
- ✅ Baixo consumo de bateria (WebSocket eficiente)
- ✅ Não depende de serviços externos

**Desvantagens:**
- ⚠️ Requer serviço em background sempre ativo
- ⚠️ Android 12+ tem restrições de background (mitigável)

#### **2. Polling + Local Notifications**

```typescript
// Verificar novas notificações a cada 60 segundos
setInterval(async () => {
  const response = await fetch('http://10.0.0.245:5000/api/notifications/pending');
  const notifications = await response.json();
  
  notifications.forEach(notif => {
    notifee.displayNotification({...});
  });
}, 60000);
```

**Vantagens:**
- ✅ Implementação mais simples
- ✅ Compatível com todas versões Android

**Desvantagens:**
- ❌ Atraso de até 60 segundos
- ❌ Maior consumo de bateria
- ❌ Possível duplicação de notificações

#### **3. Firebase Cloud Messaging (FCM) - Servidor Local**

É possível configurar um servidor FCM local, mas é complexo e não vale a pena para rede interna.

---

## 📸 Scanner de Código de Barras

### Implementação com react-native-vision-camera

```typescript
// components/BarcodeScanner.tsx
import { Camera, useCameraDevice, useCodeScanner } from 'react-native-vision-camera';

export function BarcodeScanner() {
  const device = useCameraDevice('back');
  
  const codeScanner = useCodeScanner({
    codeTypes: ['ean-13', 'code-128', 'qr'],
    onCodeScanned: async (codes) => {
      const barcode = codes[0]?.value;
      if (barcode) {
        // Buscar item no estoque
        const response = await fetch(`http://10.0.0.245:5000/api/mobile/item/${barcode}`);
        const item = await response.json();
        
        // Exibir detalhes do item
        navigation.navigate('ItemDetails', { item });
      }
    }
  });
  
  if (!device) return <Text>Câmera não disponível</Text>;
  
  return (
    <Camera
      style={StyleSheet.absoluteFill}
      device={device}
      isActive={true}
      codeScanner={codeScanner}
    />
  );
}
```

**Funcionalidades (SOMENTE CONSULTA):**
- ✅ Leitura de EAN-13, Code-128, QR Code
- ✅ Busca automática no estoque
- ✅ Exibição de saldo, categoria, localização
- ✅ Visualização de histórico de movimentações
- ✅ Botão para gerar relatório do item
- ❌ **NÃO** registra saída/entrada (use GALINT Mobile para isso)

---

## 📊 Funcionalidades Detalhadas

### 1. Tela de Notificações

```typescript
interface Notification {
  id: string;
  type: 'withdrawal' | 'entry' | 'low_stock' | 'return';
  title: string;
  body: string;
  timestamp: Date;
  read: boolean;
  data: {
    saida_ids?: number[];
    entrada_ids?: number[];
    item_codigo?: string;
    usuario_matricula?: string;
  };
}
```

**Layout:**
```
┌─────────────────────────────────┐
│  🔔 Notificações     [Filter▼]  │
├──────────Saída                  │
│  5 itens retirados              │
│  João Silva - há 2 min          │
│  [Ver Detalhes] [Gerar PDF]     │
│                                 │
├─────────────────────────────────┤
│                                 │
│  ⚠️ Estoque Baixo               │
│  Martelo 500g - 3 unid.         │
│  há 15 min                      │
│  [Ver Item] [Gerar Relatório]   │
│                                 │
├─────────────────────────────────┤
│                                 │
│  ↩️ Devolução Recebida          │
│  Furadeira - Maria Costa        │
│  há 1 hora                      │
│  [Ver Detalhes]                 │
│                                 │
└─────────────────────────────────┘

⚠️ IMPORTANTE: Apenas visualização
Para registrar saídas/entradas,
use o GALINT Mobile.
│                                 │
└─────────────────────────────────┘
```

### 2. Consulta de Estoque

**Métodos de Pesquisa:**
1. Scanner de código de barras (câmera)
2. Busca por texto (descrição/código)
3. Filtro por categoria
4. Últimos visualizados

**Informações Exibidas:**
```typescript
interface ItemDetails {
  codigo: string;
  descricao: string;
  categoria: string;
  saldo: number;
  unidade: string;
  localizacao: string;
  estoque_minimo: number;
  status: 'ok' | 'baixo' | 'critico';
  barcode_image?: string;
  ultimas_movimentacoes: Movement[];
}
```

### 3. Relatórios (TODOS os relatórios disponíveis no sistema)

**Tipos de Relatórios Disponíveis:**

| Relatório | Formato | Endpoint Existente | Descrição |
|-----------|---------|-------------------|-----------|
| Saídas do Dia | PDF/JPEG | `/api/telegram/relatorio-saidas-dia` | Todas as saídas de hoje |
| Histórico do Usuário | PDF | `/api/reports/usuario/{matricula}` | Movimentações por funcionário |
| Estoque Crítico | PDF | `/movimentos/alertas-estoque/pdf` | Itens abaixo estoque mínimo |
| Movimentações por Item | PDF | `/api/reports/item/{codigo}` | Histórico de um item específico |
| Relatório de Ferramentas | PDF | `/api/reports/ferramentas` | Ferramentas em custódia |
| Resumo de Estoque | PDF (TODOS os relatórios):**
```typescript
// Serviço completo de relatórios
class ReportService {
  private baseUrl = 'http://10.0.0.245:5000';
  
  async downloadReport(type: string, params: any) {
    const endpoints = {
      'saidas_dia': '/api/telegram/relatorio-saidas-dia',
      'usuario': `/api/reports/usuario/${params.matricula}`,
      'estoque_critico': '/movimentos/alertas-estoque/pdf',
      'item': `/api/reports/item/${params.codigo}`,
      'ferramentas': '/api/reports/ferramentas',
      'estoque_geral': '/api/reports/estoque-geral',
      'movimentacoes': `/api/reports/movimentacoes?inicio=${params.inicio}&fim=${params.fim}`,
      'categoria': `/api/reports/categoria/${params.categoria}`
    };
    
    const endpoint = endpoints[type];
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      headers: {
        'Authorization': `Bearer ${token}`,
      }
    });
    
    const blob = await response.blob();
    const filename = `Relatorio_${type}_${Date.now()}.pdf`;
    
    // Salvar em Download/Galint/
    const path = await RNFS.writeFile(
      `${RNFS.DownloadDirectoryPath}/Galint/${filename}`,
      blob,
      'base64'
    );
    
    // Abrir com visualizador nativo
    await FileViewer.open(path);
    
    // Notificar usuário
    Toast.show({
      text: `✓ Relatório salvo em Downloads/Galint/`,
      duration: 3000
    });
  }
  
  // Lista de todos os relatórios disponíveis
  getAvailableReports() {
    return [
      { id: 'saidas_dia', name: 'Saídas do Dia', icon: '📦', params: [] },
      { id: 'usuario', name: 'Histórico de Funcionário', icon: '👤', params: ['matricula'] },
      { id: 'estoque_critico', name: 'Estoque Crítico', icon: '⚠️', params: [] },
      { id: 'item', name: 'Movimentações de Item', icon: '🔍', params: ['codigo'] },
      { id: 'ferramentas', name: 'Ferramentas em Custódia', icon: '🔧', params: [] },
      { id: 'estoque_geral', name: 'Resumo Geral', icon: '📊', params: [] },
      { id: 'movimentacoes', name: 'Movimentações por Período', icon: '📅', params: ['inicio', 'fim'] },
      { id: 'categoria', name: 'Itens por Categoria', icon: '📂', params: ['categoria'] }
    ];
  }
  );
  
  // Abrir com visualizador nativo
  await FileViewer.open(path);
}
```

### 4. Histórico de Movimentações

**Filtros:**
- Data (hoje, últimos 7 dias, últimos 30 dias, personalizado)
- Tipo (saídas, entradas, devoluções)
- Usuário
- Item/Categoria

**Lista com Pull-to-Refresh:**
```typescript
<FlatList
  data={movements}
  refreshing={loading}
  onRefresh={loadMovements}
  renderItem={({ item }) => (
    <MovementCard
      type={item.type}
      usuario={item.usuario.nome}
      item={item.item.descricao}
      quantidade={item.quantidade}
      timestamp={item.timestamp}
      onPress={() => navigation.navigate('MovementDetails', { id: item.id })}
    />
  )}
/>
```

---

## 🔒 Segurança e Autenticação

### 1. Autenticação JWT (Mesma do GALINT Mobile)

```typescript
// Login flow
async function login(matricula: string, senha: string) {
  const response = await fetch('http://10.0.0.245:5000/api/mobile/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ matricula, senha })
  });
  
  const { access_token, user } = await response.json();
  
  // Salvar token localmente
  await AsyncStorage.setItem('auth_token', access_token);
  await AsyncStorage.setItem('user', JSON.stringify(user));
  
  // Inicializar serviço de notificações
  await NotificationService.initialize(user.id, access_token);
  
  return { token: access_token, user };
}
```

### 2. Comunicação Segura

- **HTTPS/WSS**: Certificado SSL auto-assinado para rede interna
- **Token Refresh**: Renovação automática a cada 24h
- **Timeout de Sessão**: 7 dias de inatividade

### 3. Permissões Android

```xml
<!-- android/app/src/main/AndroidManifest.xml -->
<manifest>
  <uses-permission android:name="android.permission.CAMERA" />
  <uses-permission android:name="android.permission.INTERNET" />
  <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
  <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
  <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
  <uses-permission android:name="android.permission.WAKE_LOCK" />
  <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" />
</manifest>
```

---

## ⚡ Performance e Otimização

### 1. Cache Local

```typescript
// Armazenar dados frequentemente acessados
class CacheService {
  private cache = new Map<string, any>();
  
  async get(key: string, fetcher: () => Promise<any>, ttl: number = 300000) {
    const cached = this.cache.get(key);
    
    if (cached && Date.now() - cached.timestamp < ttl) {
      return cached.data;
    }
    
    const data = await fetcher();
    this.cache.set(key, { data, timestamp: Date.now() });
    return data;
  }
}

// Uso
const items = await cache.get('items_list', 
  () => fetch('/api/mobile/items').then(r => r.json()),
  600000 // 10 minutos
);
```

### 2. Lazy Loading

```typescript
// Carregar notificações em lotes
<FlatList
  data={notifications}
  onEndReached={loadMoreNotifications}
  onEndReachedThreshold={0.5}
  initialNumToRender={20}
  maxToRenderPerBatch={10}
/>
```

### 3. Otimização de Imagens

```typescript
// Redimensionar imagens de relatórios
import ImageResizer from 'react-native-image-resizer';

const resized = await ImageResizer.createResizedImage(
  uri,
  800,
  1200,
  'JPEG',
  80
);
```

---

## 🔧 Requisitos Técnicos

### Backend (GALINT Flask)

**Novos Endpoints Necessários:**

```python
# galint_flask/views/api_notifications.py

@blueprint.get('/api/notifications/pending')
@token_required
def get_pending_notifications(current_user):
    """Retorna notificações não lidas do usuário"""
    notifications = Notification.query.filter_by(
        user_id=current_user.id,
        read=False
    ).order_by(Notification.created_at.desc()).limit(50).all()
    
    return jsonify([n.to_dict() for n in notifications])

@blueprint.post('/api/notifications/<int:id>/read')
@token_required
def mark_as_read(current_user, id):
    """Marca notificação como lida"""
    notification = Notification.query.get_or_404(id)
    notification.read = True
    db.session.commit()
    return jsonify({'success': True})

@blueprint.delete('/api/notifications/<int:id>')
@token_required
def delete_notification(current_user, id):
    """Remove notificação"""
    notification = Notification.query.get_or_404(id)
    db.session.delete(notification)
    db.session.commit()
    return jsonify({'success': True})
```

**Modelo de Banco de Dados:**

```python
# galint_flask/models.py

class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # withdrawal, entry, low_stock
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text)
    data = db.Column(db.JSON)  # Dados adicionais (IDs, etc)
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('Usuario', backref='notifications')
```

**Migração:**

```bash
# Criar migração
flask db migrate -m "add_notifications_table"
flask db upgrade
```

### Infraestrutura

**Servidor:**
- CPU: 2+ cores
- RAM: 4GB+ (Flask + SocketIO)
- Rede: Gigabit LAN (rede interna)
- IP Fixo: 10.0.0.245 (já configurado)

**Android:**
- Android 8.0+ (API 26+)
- Câmera com autofoco
- 100MB espaço de armazenamento
- Conexão Wi-Fi na mesma rede do servidor

---

## 📊 Comparativo: Telegram Bot vs App Nativo (SOMENTE LEITURA)

| Critério | Telegram Bot | App Nativo (Read-Only) |
|----------|--------------|------------------------|
| **Custo de Desenvolvimento** | ⚪ Baixo (já existe) | 🔴 Médio (2 semanas) |
| **Manutenção** | 🟢 Baixa | 🟢 Baixa (sem lógica de escrita) |
| **Dependência Externa** | 🔴 Total (Telegram API) | 🟢 Zero |
| **Funciona Offline** | 🔴 Não | 🟢 Sim (rede interna) |
| **Performance** | 🟡 Boa | 🟢 Excelente |
| **Personalização** | 🔴 Limitada | 🟢 Total |
| **Segurança de Dados** | 🟡 Passa por servidor externo | 🟢 100% interno |
| **Scanner de Barras** | 🔴 Não nativo | 🟢 Nativo otimizado |
| **Relatórios** | 🟡 Parcial (2-3 tipos) | 🟢 Completo (8+ tipos) |
| **Experiência do Usuário** | 🟡 Genérica | 🟢 Otimizada |
| **Notificações Push** | 🟢 Excelente | 🟢 Excelente |
| **Custo Operacional** | 🟢 Zero | 🟢 Zero (rede interna) |
| **Registro de Entradas/Saídas** | 🔴 Não | 🔴 Não (propositalmente) |

### Vantagens do App Nativo

1. **✅ Independência Total**
   - Funciona mesmo sem internet
   - Não depende de APIs externas
   - Controle total sobre infraestrutura

2. **✅ Segurança Aprimorada**
   - Dados não saem da rede interna
   - LGPD/compliance facilitado
   - Sem risco de vazamento via Telegram

3. **✅ Funcionalidades Exclusivas** (consulta apenas)
   - Download de TODOS os relatórios do sistema (8+ tipos)
   - Interface focada em monitoramento e consulta
   - Separação clara: consulta no App, operação no Mobileflow específico
   - Integração profunda com backend

4. **✅ Performance Superior**
   - Carregamento mais rápido
   - Menor latência de rede (LAN vs Internet)
   - Cache local eficiente

5. **✅ Profissionalismo**
   - Marca própria (GALINT)
   - Experiência consistente
   - Sem propagandas/distrações

### Desvantagens do App Nativo

1. **❌ Custo Inicial de Desenvolvimento**
   - 2-4 semanas de desenvolvimento
   - Testes e homologação
   - Documentação

2. **❌ Manutenção Adicional**
   - Atualizações de segurança Android
   - Correções de bugs
   - Novas funcionalidades

3. **❌ Distribuição Manual**
   - Não está em Google Play (rede interna)
   - Instalação via APK direto
   - Usuários precisam habilitar "Origens desconhecidas"

4. **❌ Limitado ao Android**
   - Telegram funciona em qualquer plataforma
   - App nativo seria apenas Android (iOS requer desenvolvimento separado)

---

## 💰 Estimativa de Esforço

### Desenvolvimento Inicial

| Tarefa | Tempo Estimado | Prioridade |
|--------|----------------|------------|
| Setup projeto React Native | 4h | Alta |
| Tela de login (reuso do GALINT Mobile) | 2h | Alta |
| Integração WebSocket + Notificações | 16h | Alta |
| Tela de listagem de notificações | 8h | Alta |
| Scanner de código de barras | 12h | Alta |
| Consulta de estoque (SOMENTE LEITURA) | 6h | Alta |
| Download de relatórios (8 tipos) | 12h | Alta |
| Histórico de movimentações (visualização) | 6h | Média |
| Configurações e preferências | 4h | Baixa |
| Testes e ajustes | 10h | Alta |
| **TOTAL** | **80h (~2 semanas)** | - |

### Backend (Flask)

| Tarefa | Tempo Estimado | Prioridade |
|--------|----------------|------------|
| Modelo de Notification + migração | 2h | Alta |
| Endpoints de API (/notifications/*) | 4h | Alta |
| Integração SocketIO (já existe base) | 6h | Alta |
| Adaptação do TelegramService | 4h | Alta |
| Testes e validação | 4h | Média |
| **TOTAL** | **20h (~3 dias)** | - |

### **Total Geral: 100 horas (~2.5 semanas com 1 desenvolvedor)**

---

## 🚀 Roadmap de Implementação3 funcionalidades principais

✅ Funcionalidades:
1. **Notificações** (Recebimento de alertas de saídas/retiradas)
   - Login/autenticação
   - Recebimento de notificações push via WebSocket
   - Lista de notificações (leitura, marcar como lida, excluir)
   - Detalhes de movimentação (visualização apenas)

2. **Consulta de Estoque** (Scanner de código de barras)
   - Scanner de EAN-13, Code-128, QR Code
   - Exibição de saldo e informações do item
   - Histórico de movimentações do item

3.**Relatórios completos** (todos os 8 tipos disponíveis)
- Filtros avançados de consulta de estoque
- Busca por texto (descrição/código)
- Histórico de movimentações com filtros (data, tipo, usuário)
- Preferências do usuário (tema, idioma, sons)
- Cache offline de consultas recentes

🎯 Entregável: App completo (SOMENTE LEITURA)
- Scanner básico de código de barras

🎯 Entregável: APK testável com funcionalidade core

### **Fase 2: Funcionalidades Avançadas - Semana 3**

✅ Adicionar:
- Consulta de estoque completa
- Filtros e busca avançada
- Download de relatórios
- Histórico de movimentações
- Preferências do usuário

🎯 Entregável: App completo para homologação

### **Fase 3: Polimento e Testes - Semana 4**

✅ Focos:
- Testes com usuários reais
- Correção de bugs
- Otimização de performance
- Documentação para usuários
- Criação de manual de instalação

🎯 Entregável: App pronto para produção

### **Fase 4: Distribuição e Treinamento**

✅ Atividades:
- Instalação em dispositivos dos usuários
- Treinamento da equipe
- Monitoramento inicial
- Coleta de feedback
- Ajustes finais

---

## 📱 Distribuição do APK

### Opções de Distribuição (Rede Interna)

#### **Opção 1: Servidor HTTP Interno (Recomendado)**

```python
# galint_flask/views/apk_download.py

@blueprint.get('/downloads/galint-notifications.apk')
def download_notification_apk():
    """Disponibiliza APK para download"""
    apk_path = Path(__file__).parent.parent / 'static' / 'apk' / 'galint-notifications-v1.0.0.apk'
    
    return send_file(
        apk_path,
        as_attachment=True,
        download_name='GALINT-Notificacoes.apk',
        mimetype='application/vnd.android.package-archive'
    )
```

**URL de acesso:** `http://10.0.0.245:5000/downloads/galint-notifications.apk`

**Processo de instalação:**
1. Usuário acessa URL pelo navegador Android
2. Baixa APK (15-25 MB)
3. Android solicita permissão para instalar
4. Usuário confirma instalação
5. App instalado e pronto para uso

#### **Opção 2: QR Code**

```python
import qrcode

def generate_apk_qr():
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data('http://10.0.0.245:5000/downloads/galint-notifications.apk')
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img.save('static/apk_qr.png')
```

Usuário apenas escaneia QR Code e faz download direto.

#### **Opção 3: Compartilhamento via Bluetooth/NFC**

Para ambientes onde rede é instável, pode-se transferir APK via:
- Bluetooth (app SHAREit, Xender)
- Android Beam (NFC)
- Pen drive OTG

---

## 🔄 Atualização do App

### Sistema de Versionamento

```typescript
// App verifica versão ao iniciar
async function checkForUpdates() {
  const currentVersion = '1.0.0';
  
  const response = await fetch('http://10.0.0.245:5000/api/app-version');
  const { latest_version, download_url, required } = await response.json();
  
  if (latest_version !== currentVersion) {
    Alert.alert(
      'Atualização Disponível',
      `Nova versão ${latest_version} disponível.`,
      [
        { text: 'Depois', style: 'cancel' },
        { 
          text: 'Atualizar', 
          onPress: () => Linking.openURL(download_url)
        }
      ],
      { cancelable: !required }
    );
  }
}
```

### Backend - Controle de Versão

```python
@blueprint.get('/api/app-version')
def get_app_version():
    return jsonify({
        'latest_version': '1.1.0',
        'download_url': 'http://10.0.0.245:5000/downloads/galint-notifications.apk',
        'required': False,  # Se True, força atualização
        'changelog': ['Correção de bugs', 'Melhorias de performance']
    })
```

---

## 🛡️ Segurança e LGPD

### Dados Armazenados Localmente

```typescript
// Apenas dados necessários em cache
interface LocalStorage {
  auth_token: string;           // JWT (expira em 7 dias)
  user: {
    id: string;
    matricula: string;
    nome: string;
    is_admin: boolean;
  };
  notifications_cache: Notification[]; // Últimas 50
  items_cache: Item[];          // Favoritos/recentes
  preferences: UserPreferences;  // Tema, notificações, etc
}
```

### Limpeza de Dados

```typescript
// Ao fazer logout
async function logout() {
  await AsyncStorage.clear();           // Limpa tudo
  await NotificationService.disconnect(); // Desconecta WebSocket
  navigation.reset({ index: 0, routes: [{ name: 'Login' }] });
}
```

### Conformidade LGPD

✅ **Princípios atendidos:**
- **Minimização**: Apenas dados essenciais são coletados
- **Finalidade**: Uso exclusivo para gestão de almoxarifado
- **Adequação**: Dados necessários para operação
- **Transparência**: Usuário sabe quais dados são usados
- **Segurança**: Comunicação criptografada (HTTPS/WSS)
- **Prevenção**: Dados não vazam para fora da empresa

---

## 📈 Métricas e Monitoramento

### Analytics Básico (Local)

```python
# Backend - tracker de uso
class AppUsageMetric(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    action = db.Column(db.String(100))  # 'scan', 'view_notification', 'download_report'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    metadata = db.Column(db.JSON)

# Rastrear eventos
@blueprint.post('/api/analytics/track')
@token_required
def track_event(current_user):
    data = request.get_json()
    metric = AppUsageMetric(
        user_id=current_user.id,
        action=data['action'],
        metadata=data.get('metadata', {})
    )
    db.session.add(metric)
    db.session.commit()
    return jsonify({'success': True})
```

### Dashboard de Uso (Admin)

```python
@blueprint.get('/admin/app-usage-stats')
@admin_required
def app_usage_stats():
    # Total de instalações ativas (últimos 7 dias)
    active_users = db.session.query(func.count(func.distinct(AppUsageMetric.user_id)))\
        .filter(AppUsageMetric.timestamp >= datetime.utcnow() - timedelta(days=7))\
        .scalar()
    
    # Ações mais comuns
    top_actions = db.session.query(AppUsageMetric.action, func.count())\
        .group_by(AppUsageMetric.action)\
        .order_by(func.count().desc())\
        .limit(10).all()
    
    return jsonify({
        'active_users': active_users,
        'top_actions': [{'action': a, 'count': c} for a, c in top_actions]
    })
```

---

## 🎨 Design UI/UX

### Identidade Visual

```typescript
// theme/colors.ts
export const theme = {
  primary: '#2563eb',      // Azul GALINT
  secondary: '#3b82f6',
  success: '#10b981',
  warning: '#f59e0b',
  danger: '#ef4444',
  background: '#f8f9fa',
  surface: '#ffffff',
  text: '#1f2937',
  textSecondary: '#6b7280',
  border: '#e5e7eb'
};
```

### Navegação
Home (Modo Consulta)         │
│                                 │
│  ┌─────────────────────────┐   │
│  │ 📸 Consultar Estoque    │   │ Abre scanner
│  │    (Scanner de Barras)  │   │
│  └─────────────────────────┘   │
│                                 │
│  ┌─────────────────────────┐   │
│  │ 🔔 5 Novas Notificações │   │ Ver saídas/retiradas
│  └─────────────────────────┘   │
│                                 │
│  ┌─────────────────────────┐   │
│  │ 📊 Baixar Relatórios    │   │ Todos os PDFs
│  └─────────────────────────┘   │
│                                 │
│  ⚠️ Para registrar saídas:      │
│     Use o GALINT Mobileões │   │
│  └─────────────────────────┘   │
│                                 │
│  ┌─────────────────────────┐   │
│  │ 📊 Relatório do Dia     │   │
│  └─────────────────────────┘   │
│                                 │
└─────────────────────────────────┘
```

---

## 🔮 Futuras Expansões

### Fase 2 (Médio Prazo)
Avançado**
   - Cache inteligente de consultas recentes
   - Sincronização automática de notificações
   - Relatórios gerados offline (dados em cache)

2. **Dashboard Personalizado (Read-Only)
2. **Dashboard Personalizado**
   - Gráficos de movimentações
   - Alertas configuráveis
   - Widgets customizáveis

3. **Estatísticas Avançadas**
   - Gráficos de consumo de materiais
   - Análise de padrões de retirada
   - Alertas preditivos personalizados

4. **Suporte a Múltiplos Idiomas**
   - Português, Espanhol, Inglês

### Fase 3 (Longo Prazo)

1. **Versão iOS**
   - React Native facilita portabilidade
   - ~60% código compartilhado

2. **Versão Web Progressive (PWA)**
   - Acesso via navegador
   - Notificações via Service Worker

3. **Integração com Câmeras de Segurança**
   - Visualização de imagens de retiradas
   - Timeline sincronizada com movimentações

4. **IA para Análise de Padrões**
   - Alertas preditivos de ruptura
   - Sugestões de reposição inteligentes

---

## 🎯 Recomendação Final

### ✅ **VIÁVEL E RECOMENDADO**

**Motivos:**

1. **Retorno sobre Investimento (ROI)**
   - Investimento: ~100 horas desenvolvimento
   - Benefício: Independência total de serviços externos
   - Segurança: Dados 100% internos
   - Personalização: Ferramenta exatamente como necessário

2. **Aproveitamento de Recursos Existentes**
   - 70% código reutilizado do GALINT Mobile
   - Backend já pronto (apenas ajustes)
   - Expertise React Native já na equipe
   - Infraestrutura (servidor) já existe

3. **Timeline Realista**
   - MVP em 2 semanas
   - App completo em 1 mês
   - Sem dependências externas críticas

4. **Escalabilidade**
   - Base sólida para futuras funcionalidades
   - Fácil manutenção e evolução
   - Controle total sobre roadmap

### 📋 Próximos Passos

**Semana 1:**
1. ✅ Aprovar este documento de viabilidade
2. ✅ Definir prioridades de funcionalidades (MVP vs futuras)
3. ✅ Configurar ambiente de desenvolvimento
4. ✅ Criar repositório Git separado (`galint-notification-app`)

**Semana 2-3:**
5. ✅ Desenvolvimento do MVP
6. ✅ Testes internos
7. ✅ Ajustes baseados em feedback

**Semana 4:**
8. ✅ Homologação com usuários finais
9. ✅ Distribuição do APK
10. ✅ Treinamento e suporte

---

## 📞 Suporte e Documentação

### Estrutura de Arquivos Recomendada

```
galint-notification-app/
├── android/                 # Código Android nativo
├── ios/                     # (Futuro) Código iOS
├── src/
│   ├── components/          # Componentes reutilizáveis
│   ├── screens/             # Telas do app
│   ├── services/            # Lógica de negócio
│   │   ├── NotificationService.ts
│   │   ├── WebSocketService.ts
│   │   ├── ApiService.ts
│   │   └── BarcodeService.ts
│   ├── navigation/          # Navegação
│   ├── theme/               # Cores, estilos
│   ├── types/               # TypeScript types
│   └── utils/               # Utilitários
├── package.json
├── tsconfig.json
└── README.md
```

### Documentação de Instalação (Usuário Final)

```markdown
# GALINT Notificações - Guia de Instalação

## Requisitos
- Android 8.0 ou superior
- Conexão Wi-Fi na rede interna da empresa

## Passo a Passo

1. **Baixar APK**
   - Acesse: http://10.0.0.245:5000/downloads/galint-notifications.apk
   - Ou escaneie o QR Code no mural

2. **Habilitar Instalação**
   - Configurações → Segurança → Origens desconhecidas
   - Permitir instalação de apps de fontes desconhecidas

3. **Instalar**
   - Clique no arquivo baixado
   - Confirme instalação
   - Aguarde conclusão

4. **Abrir e Login**
   - Abra o app GALINT Notificações
   - Faça login com sua matrícula e senha
   - Permita notificações quando solicitado
 Você pode:**
   - ✅ Receber notificações de saídas/retiradas em tempo real
   - ✅ Usar o scanner para consultar estoque
   - ✅ Baixar todos os tipos de relatórios (PDF)
   - ❌ Para registrar entradas/saídas, use o **GALINT Mobile**ue
   - Baixe relatórios quando necessário
```

---

## 📝 Conclusão (SOMENTE LEITURA)** é **tecnicamente viável**, **estrategicamente vantajoso** e **financeiramente justificável**. 

Com investimento de aproximadamente **2 semanas de desenvolvimento**, a empresa terá:

✅ **Independência tecnológica** (zero dependência do Telegram)  
✅ **Segurança aprimorada** (dados 100% internos)  
✅ **3 funcionalidades principais** perfeitamente implementadas:
   1. 🔔 **Notificações** de saídas/retiradas
   2. 📸 **Consulta de estoque** via scanner
   3. 📊 **Download de TODOS os relatórios** (8+ tipos em PDF)

✅ **Separação de responsabilidades clara**:
   - **GALINT Mobile**: Operação (registra entradas/saídas)
   - **Notification App**: Monitoramento e consulta (SOMENTE LEITURA)

✅ **Menor complexidade** (sem lógica de escrita = menos bugs)nos)  
✅ **Funcionalidades customizadas** para o negócio  
✅ **Experiência otimizada** para os usuários  
✅ **Base sólida** para futuras expansões  

A recomendação é **prosseguir com o desenvolvimento**, iniciando pelo MVP em React Native, aproveitando a expertise existente e a infraestrutura já implantada.

---

**Documento elaborado em:** 16/02/2026  
**Versão:** 1.0  
**Status:** ✅ Aprovado para desenvolvimento  
**Autor:** Equipe Técnica GALINT  

---

## 📚 Referências Técnicas

- [React Native Documentation](https://reactnative.dev/docs/getting-started)
- [Flask-SocketIO](https://flask-socketio.readthedocs.io/)
- [Notifee React Native](https://notifee.app/)
- [React Navigation](https://reactnavigation.org/)
- [Vision Camera](https://react-native-vision-camera.com/)
- [Android Background Services](https://developer.android.com/guide/background)
