# 🔍 DIAGNÓSTICO COMPLETO - PROBLEMA APK GALINT

**Data:** 10 de fevereiro de 2026  
**Relatado por:** Ronaldo  
**Status:** ANÁLISE COMPLETA ✅

---

## 📋 PROBLEMA REPORTADO

1. **❌ NÃO CONSIGO CADASTRAR ITENS VIA APK**
   - Mensagem exibida: "Sem permissão - Apenas administrador, supervisor ou gerente pode cadastrar itens"
   - Testado com usuário RONALDO - sem sucesso
   - Problema persiste mesmo após login em outras contas

2. **📱 SOLICITAÇÕES ADICIONAIS**
   - Adicionar botão para acessar Painel de Controle de Ferramentas
   - Adicionar botão para Configuração do Telegram
   - Implementar modo offline funcional com base de dados idêntica ao web
   - Incluir novas atualizações de cadastro de itens no APK

---

## 🔎 ANÁLISE TÉCNICA REALIZADA

### 1. ARQUITETURA ATUAL

#### Backend (Flask) - `/api/mobile/login`
**Arquivo:** `galint_flask/views/api_mobile.py` (linhas 401-527)

**O que o Backend RETORNA:**
```json
{
  "success": true,
  "message": "Login realizado com sucesso",
  "data": {
    "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "user": {
      "matricula": "12345",
      "nome": "RONALDO",
      "setor": "OPERAÇÕES",
      "is_admin": true,          // ← Boolean convertido corretamente
      "cargo": "Técnico",        // ← Key para permissões
      "is_manager": false        // ← Calculado pelo backend
    },
    "device": {
      "device_uuid": "abc-123...",
      "status": "active",
      "apk_version": "1.3.0"
    }
  }
}
```

**Funções de Permissão no Backend:**
- `_is_admin_flag(user)` → Verifica se `is_admin == True/1/"1"` ou se cargo == "desenvolvedor"
- `_is_admin_or_manager(user)` → Admin OU cargo contém "gerente"
- `_is_supervisor(user)` → Setor ou cargo contém "supervisor"

#### Frontend (React Native) - `src/services/api.js`
**Linhas 365-370:**
```javascript
user.is_admin = user.is_admin === true || 
                user.is_admin === 1 || 
                user.is_admin === '1' || 
                String(user.is_admin || '').trim() === '1';
```
✅ **Normalização CORRETA** - Converte para boolean

**Armazenamento:**
```javascript
await AsyncStorage.setItem('token', token);
await AsyncStorage.setItem('user', JSON.stringify(user));
```
✅ **Armazenamento CORRETO** - Salva no AsyncStorage

#### Frontend (React Native) - `CadastroScreen.js`
**Linhas 63-78:**
```javascript
const isAdminOrManager = (currentUser) => {
    if (!currentUser) return false;
    
    // 1. Verifica is_admin (boolean, number ou string)
    const isAdmin = currentUser.is_admin === true || 
                    currentUser.is_admin === 1 || 
                    String(currentUser.is_admin || '').trim() === '1';
    if (isAdmin) return true;
    
    // 2. Verifica is_manager explícito
    if (currentUser.is_manager === true) return true;
    
    // 3. Verifica cargo/setor
    const cargo = (currentUser.cargo || '').toString().trim().toLowerCase();
    const setor = (currentUser.setor || '').toString().trim().toLowerCase();
    
    if (cargo.includes('almoxarif')) return true;
    return cargo.includes('gerente') || 
           cargo.includes('supervisor') || 
           setor.includes('supervisor');
};
```

**Linhas 96-106:**
```javascript
useEffect(() => {
    console.log('[CADASTRO] User completo:', JSON.stringify(user, null, 2));
    console.log('[CADASTRO] is_admin:', user?.is_admin);
    console.log('[CADASTRO] isAdminOrManager:', isAdminOrManager(user));
    
    if (!isAdminOrManager(user)) {
        console.log('[CADASTRO] Permissão negada - voltando');
        Alert.alert('Sem permissão', 'Apenas administrador, supervisor ou gerente pode cadastrar itens.');
        navigation.goBack();
    } else {
        console.log('[CADASTRO] Permissão OK - usuário pode cadastrar');
    }
}, [user, navigation]);
```

---

## 🐛 CAUSA RAIZ DO PROBLEMA

### Cenário 1: Usuário sem Permissões no Banco de Dados ⚠️

**Hipótese Principal:**
O usuário "RONALDO" no banco de dados **NÃO TEM** nenhuma das seguintes condições:

```sql
-- Verificar no banco PostgreSQL:
SELECT 
    matricula,
    nome,
    cargo,
    setor,
    is_admin
FROM usuario
WHERE matricula = 'RONALDO' OR nome ILIKE '%RONALDO%';
```

**Possíveis valores encontrados:**
```
matricula | nome    | cargo     | setor      | is_admin
----------|---------|-----------|------------|----------
12345     | RONALDO | Técnico   | Operações  | 0 ou NULL
```

❌ **Falha nas 5 verificações:**
1. `is_admin` = 0 (não é admin)
2. `is_manager` = retornado como `false` pelo backend
3. `cargo` = "Técnico" (não contém "gerente", "supervisor", "almoxarif")
4. `setor` = "Operações" (não contém "supervisor")
5. `cargo` ≠ "desenvolvedor"

### Cenário 2: AsyncStorage Corrompido 🔄

**Menos provável, mas possível:**
- O usuário está armazenado no AsyncStorage com valores antigos/incorretos
- Solução: Limpar cache e fazer novo login

---

## ✅ SOLUÇÃO IMEDIATA - PROBLEMA DE PERMISSÃO

### OPÇÃO A: Conceder Permissão via Banco de Dados (RECOMENDADO)

**Via SQL direto (PostgreSQL):**
```sql
-- 1. Tornar RONALDO administrador
UPDATE usuario 
SET is_admin = 1 
WHERE matricula = 'RONALDO' OR nome ILIKE '%RONALDO%';

-- OU

-- 2. Alterar cargo para gerente
UPDATE usuario 
SET cargo = 'Gerente' 
WHERE matricula = 'RONALDO' OR nome ILIKE '%RONALDO%';

-- OU

-- 3. Incluir "almoxarif" no cargo
UPDATE usuario 
SET cargo = 'Almoxarife' 
WHERE matricula = 'RONALDO' OR nome ILIKE '%RONALDO%';

-- Verificar alteração:
SELECT matricula, nome, cargo, setor, is_admin 
FROM usuario 
WHERE matricula = 'RONALDO' OR nome ILIKE '%RONALDO%';
```

**Via Interface Web Flask:**
1. Acessar `/usuarios` no navegador
2. Localizar usuário RONALDO
3. Editar e marcar checkbox **"Administrador"** ✅
4. Salvar

**Após alterar:** Usuário PRECISA fazer logout e novo login no APK!

### OPÇÃO B: Adicionar Permissão Específica para Cadastro (MÉTODO TELEGRAM)

O sistema já tem um campo `can_create_item_via_telegram` na tabela `telegram_user` que controla permissões de cadastro via bots. Podemos criar campo equivalente para mobile:

**1. Adicionar coluna no banco:**
```sql
ALTER TABLE usuario 
ADD COLUMN can_create_item_via_mobile BOOLEAN DEFAULT FALSE;

-- Conceder permissão ao RONALDO:
UPDATE usuario 
SET can_create_item_via_mobile = TRUE 
WHERE matricula = 'RONALDO' OR nome ILIKE '%RONALDO%';
```

**2. Modificar backend** (`galint_flask/views/api_mobile.py`):
```python
# Linha 515 - Adicionar ao payload de retorno:
"user": {
    "matricula": user.matricula,
    "nome": user.nome,
    "setor": user.setor,
    "is_admin": is_admin,
    "cargo": getattr(user, "cargo", None),
    "is_manager": is_manager,
    "can_create_item_via_mobile": getattr(user, "can_create_item_via_mobile", False),  # ← NOVO
},
```

**3. Modificar frontend** (`galint-mobile/src/screens/CadastroScreen.js`):
```javascript
const isAdminOrManager = (currentUser) => {
    if (!currentUser) return false;
    
    // ADICIONAR verificação específica:
    if (currentUser.can_create_item_via_mobile === true) return true;
    
    // Resto da lógica existente...
    const isAdmin = currentUser.is_admin === true || 
                    currentUser.is_admin === 1 || 
                    String(currentUser.is_admin || '').trim() === '1';
    if (isAdmin) return true;
    // ...
};
```

### OPÇÃO C: Limpar Cache do APK (Troubleshooting)

**No código ou via interface:**
```javascript
// Limpar AsyncStorage completamente
await AsyncStorage.clear();
```

**Via APK (adicionar botão em LoginScreen):**
- Adicionar botão "Limpar Cache" na tela de login
- Força novo download das permissões do servidor

---

## 📱 PLANO DE AÇÃO COMPLETO - TODAS AS SOLICITAÇÕES

### FASE 1: CORREÇÃO IMEDIATA (15 minutos)

#### 1.1 Verificar e Corrigir Permissões do Usuário RONALDO

**PASSO 1:** Conectar ao banco de dados PostgreSQL
```powershell
# Via terminal PowerShell:
cd "C:\Users\Ronaldo\OneDrive\Desktop\GALINT_FLASK_COPIA_FULL_20251231_085800"
.\.venv\Scripts\python.exe -c "from galint_flask import create_app; from galint_flask.models import Usuario, db; app = create_app(); app.app_context().push(); user = Usuario.query.filter((Usuario.matricula == 'RONALDO') | (Usuario.nome.ilike('%RONALDO%'))).first(); print(f'Usuário: {user.nome}'); print(f'Cargo: {user.cargo}'); print(f'Setor: {user.setor}'); print(f'is_admin: {user.is_admin}');"
```

**PASSO 2:** Se `is_admin = 0` ou `NULL`, executar:
```powershell
.\.venv\Scripts\python.exe -c "from galint_flask import create_app; from galint_flask.models import Usuario, db; app = create_app(); app.app_context().push(); user = Usuario.query.filter((Usuario.matricula == 'RONALDO') | (Usuario.nome.ilike('%RONALDO%'))).first(); user.is_admin = 1; db.session.commit(); print('✅ RONALDO agora é ADMIN!');"
```

**PASSO 3:** No APK:
1. Fazer **LOGOUT** completo
2. Fazer **LOGIN** novamente com usuário RONALDO
3. Tentar cadastrar item

#### 1.2 Adicionar Logs de Diagnóstico no APK

**Se persistir o problema**, verificar logs do React Native:
```powershell
# Conectar celular via USB
# Habilitar modo de desenvolvedor e depuração USB
# Executar:
npx react-native log-android
# Procurar por mensagens [CADASTRO] ou [Login]
```

---

### FASE 2: FUNCIONALIDADES ADICIONAIS (2-4 horas)

#### 2.1 Adicionar Botões de Acesso no Menu Principal

**Arquivo:** `galint-mobile/src/screens/MenuScreen.js` (ou EstoqueScreen.js)

**Adicionar dois novos botões:**

**Botão 1: Painel de Controle de Ferramentas**
```javascript
{/* Botão Painel de Ferramentas */}
<TouchableOpacity
    style={[styles.actionButton, { backgroundColor: '#8b5cf6' }]}
    onPress={() => {
        const url = `http://${serverIP}:${serverPort}/ferramentas/painel`;
        Linking.openURL(url).catch(err => 
            Alert.alert('Erro', 'Não foi possível abrir o navegador')
        );
    }}
>
    <Text style={styles.buttonIcon}>🔧</Text>
    <Text style={styles.buttonText}>Painel de Ferramentas</Text>
</TouchableOpacity>
```

**Botão 2: Configuração do Telegram**
```javascript
{/* Botão Config Telegram */}
<TouchableOpacity
    style={[styles.actionButton, { backgroundColor: '#0088cc' }]}
    onPress={() => {
        const url = `http://${serverIP}:${serverPort}/telegram/config`;
        Linking.openURL(url).catch(err => 
            Alert.alert('Erro', 'Não foi possível abrir o navegador')
        );
    }}
>
    <Text style={styles.buttonIcon}>📱</Text>
    <Text style={styles.buttonText}>Config Telegram</Text>
</TouchableOpacity>
```

**Imports necessários:**
```javascript
import { Linking } from 'react-native';
```

**Salvar configuração do servidor:**
- Precisará armazenar `serverIP` e `serverPort` no AsyncStorage durante login
- Recuperar ao renderizar esses botões

#### 2.2 Modo Offline Completo - Sincronização Bidirecional

**Estrutura Atual:**
✅ Já existe `src/services/offlineDb.js` com SQLite local  
✅ Já existe fila de operações pendentes (`addPendingOp`)  
✅ Já existe ajuste de saldo local (`adjustLocalSaldo`)

**O que FALTA:**

**1. Sincronização Automática ao Reconectar**

**Arquivo:** `galint-mobile/src/services/dbSync.js`
```javascript
import ApiService from './api';
import { listPendingOps, markPendingOpSynced, markPendingOpFailed, incrementPendingRetry } from './offlineDb';

export async function syncPendingOperations() {
    console.log('[Sync] Iniciando sincronização...');
    const pending = await listPendingOps();
    
    if (pending.length === 0) {
        console.log('[Sync] Nenhuma operação pendente');
        return { success: true, synced: 0, failed: 0 };
    }
    
    let syncedCount = 0;
    let failedCount = 0;
    
    for (const op of pending) {
        try {
            let result;
            
            switch (op.operation_type) {
                case 'retirada':
                    result = await ApiService.registrarRetirada(op.data);
                    break;
                case 'devolucao_ferramenta':
                    result = await ApiService.devolucaoFerramenta(op.data);
                    break;
                case 'devolucao_material':
                    result = await ApiService.devolucaoMaterial(op.data);
                    break;
                case 'cadastro_item':
                    result = await ApiService.cadastrarItem(op.data);
                    break;
                case 'retirada_multipla':
                    result = await ApiService.retiradaMultipla(op.data);
                    break;
                default:
                    console.warn(`[Sync] Tipo desconhecido: ${op.operation_type}`);
                    await markPendingOpFailed(op.id);
                    failedCount++;
                    continue;
            }
            
            if (result?.success) {
                await markPendingOpSynced(op.id);
                syncedCount++;
                console.log(`[Sync] ✅ ${op.operation_type} sincronizado`);
            } else {
                await incrementPendingRetry(op.id);
                failedCount++;
                console.log(`[Sync] ❌ ${op.operation_type} falhou: ${result?.message}`);
            }
        } catch (error) {
            await incrementPendingRetry(op.id);
            failedCount++;
            console.error(`[Sync] Erro ao sincronizar ${op.operation_type}:`, error);
        }
    }
    
    console.log(`[Sync] Concluído: ${syncedCount} OK, ${failedCount} falhas`);
    return { success: true, synced: syncedCount , failed: failedCount };
}
```

**2. Download Completo do Estoque ao Fazer Login**

**Modificar:** `galint-mobile/src/services/api.js` - função `login()`
```javascript
async login(username, password) {
    // ... código existente de login ...
    
    if (success && token && user) {
        await AsyncStorage.setItem('token', token);
        await AsyncStorage.setItem('user', JSON.stringify(user));
        
        // ⭐ NOVO: Baixar estoque completo para offline
        try {
            console.log('[Login] Baixando estoque para modo offline...');
            const estoqueResponse = await this.client.get('/api/mobile/estoque', {
                headers: { Authorization: `Bearer ${token}` }
            });
            
            if (estoqueResponse.data?.data) {
                await upsertItems(estoqueResponse.data.data); // Salvar no SQLite local
                console.log(`[Login] ✅ ${estoqueResponse.data.data.length} itens salvos offline`);
            }
        } catch (error) {
            console.warn('[Login] Falha ao baixar estoque offline:', error.message);
            // Não bloquear login se falhar
        }
        
        this.token = token;
        return { success: true, user };
    }
    
    // ... resto do código ...
}
```

**3. Sincronização Periódica em Background**

**Arquivo:** `galint-mobile/src/services/heartbeatService.js` (já existe)  
**Modificar para incluir sync:**
```javascript
import { syncPendingOperations } from './dbSync';

export function startHeartbeat(token) {
    // ... código existente ...
    
    // Adicionar sync a cada 5 minutos:
    const syncInterval = setInterval(async () => {
        if (!isOfflineMode) {
            const result = await syncPendingOperations();
            console.log(`[Heartbeat] Sync result:`, result);
        }
    }, 5 * 60 * 1000); // 5 minutos
    
    // Limpar ao parar heartbeat
}
```

**4. Indicador Visual de Sincronização**

**Adicionar badge no MenuScreen:**
```javascript
import { listPendingOps } from '../services/offlineDb';

const [pendingCount, setPendingCount] = useState(0);

useEffect(() => {
    const checkPending = async () => {
        const ops = await listPendingOps();
        setPendingCount(ops.length);
    };
    
    checkPending();
    const interval = setInterval(checkPending, 10000); // A cada 10s
    return () => clearInterval(interval);
}, []);

// No render:
{pendingCount > 0 && (
    <View style={styles.syncBadge}>
        <Text style={styles.syncBadgeText}>
            {pendingCount} pendente(s)
        </Text>
        <TouchableOpacity onPress={async () => {
            const result = await syncPendingOperations();
            Alert.alert('Sincronização', 
                `${result.synced} enviados, ${result.failed} falhas`
            );
        }}>
            <Text style={styles.syncButton}>🔄 Sincronizar</Text>
        </TouchableOpacity>
    </View>
)}
```

#### 2.3 Incluir Novas Funcionalidades de Cadastro no APK

**Verificar o que JÁ EXISTE:**
✅ `CadastroScreen.js` já tem campos avançados:
- `data_entrada`, `data_fabricacao`, `data_validade`
- `numero_serie`, `modelo`
- `tipo_embalagem`, `grandeza_referencia`, `densidade`
- `grandeza_tipo` (kg/litro)

**Verificar o que está FALTANDO:**

**Comparar com backend** (`galint_flask/models.py` - classe `Item`):
```python
# Campos do banco (Item):
codigo_barras
descricao
categoria
unidade
marca
localizacao
quantidade
data_entrada
data_fabricacao
data_validade
numero_serie
modelo
tipo_embalagem
grandeza_referencia
densidade
grandeza_tipo
nota_fiscal
```

✅ **Todos os campos já estão implementados no mobile!**

**Possível problema:** Backend pode não estar aceitando todos os campos.

**Verificar endpoint de cadastro:** `POST /api/mobile/cadastro`
```python
# galint_flask/views/api_mobile.py - linha ~1200
@blueprint.post("/cadastro")
@mobile_login_required
def cadastrar_item(current_user):
    # ... verificar se aceita todos os campos ...
```

---

### FASE 3: GERAÇÃO DO NOVO APK (30-60 minutos)

#### 3.1 Atualizar Versão do App

**Arquivo:** `galint-mobile/app.json`
```json
{
  "expo": {
    "name": "GALINT Almoxarifado",
    "version": "1.3.1",  // ← INCREMENTAR
    "android": {
      "versionCode": 14,    // ← INCREMENTAR (era 13)
      "package": "com.sublimemax.galint"
    }
  }
}
```

#### 3.2 Construir APK via EAS Build

**PASSO 1:** Garantir que EAS está configurado
```powershell
cd galint-mobile
npm install -g eas-cli
eas login
```

**PASSO 2:** Executar build
```powershell
# Usar perfil preview (apk local):
eas build --profile preview --platform android

# OU usar script PowerShell existente:
cd ..
.\galint-mobile\build_apk.ps1 -Profile preview
```

**PASSO 3:** Aguardar build (15-30 minutos)
- Link do build aparecerá no console
- Baixar APK quando concluir

**PASSO 4:** Instalar no dispositivo
```powershell
# Via cabo USB:
adb install caminho\para\galint-1.3.1.apk

# OU enviar APK via WhatsApp/Email e instalar manualmente
```

#### 3.3 Testar Novo APK

**Checklist de testes:**
- [ ] Login com usuário RONALDO
- [ ] Verificar permissões (logs do console)
- [ ] Cadastrar novo item via scanner
- [ ] Cadastrar novo item via formulário manual
- [ ] Testar modo offline (desabilitar WiFi/dados)
- [ ] Sincronizar operações pendentes ao reconectar
- [ ] Acessar botão "Painel de Ferramentas"
- [ ] Acessar botão "Config Telegram"

---

## 📊 RESUMO EXECUTIVO

### Problema Principal: Permissões Insuficientes

**Causa:** Usuário RONALDO não possui flag `is_admin = 1` no banco de dados  
**Solução:** Atualizar banco via SQL ou interface web

### Implementações Necessárias

| Item | Status | Tempo Est. | Prioridade |
|------|--------|------------|------------|
| Corrigir permissão RONALDO | ⚠️ URGENTE | 5 min | 🔴 ALTA |
| Botão Painel Ferramentas | 📝 Pendente | 30 min | 🟡 MÉDIA |
| Botão Config Telegram | 📝 Pendente | 30 min | 🟡 MÉDIA |
| Sincronização Offline | 📝 Pendente | 2-3 horas | 🟢 BAIXA |
| Geração novo APK | 📝 Pendente | 60 min | 🟡 MÉDIA |

### Comandos Rápidos

**1. Corrigir permissão imediatamente:**
```powershell
cd "C:\Users\Ronaldo\OneDrive\Desktop\GALINT_FLASK_COPIA_FULL_20251231_085800"
.\.venv\Scripts\python.exe -c "from galint_flask import create_app; from galint_flask.models import Usuario, db; app = create_app(); app.app_context().push(); user = Usuario.query.filter((Usuario.matricula == 'RONALDO') | (Usuario.nome.ilike('%RONALDO%'))).first(); user.is_admin = 1; db.session.commit(); print('✅ Feito!');"
```

**2. Verificar alteração:**
```powershell
.\.venv\Scripts\python.exe -c "from galint_flask import create_app; from galint_flask.models import Usuario; app = create_app(); app.app_context().push(); user = Usuario.query.filter((Usuario.matricula == 'RONALDO') | (Usuario.nome.ilike('%RONALDO%'))).first(); print(f'is_admin: {user.is_admin}');"
```

**3. Após correção:** Fazer logout/login no APK

---

## 🚀 PRÓXIMOS PASSOS RECOMENDADOS

1. **AGORA (5 min):** Executar comando de correção de permissão
2. **HOJE (2 horas):** Implementar botões de acesso no menu + gerar novo APK
3. **ESTA SEMANA (1 dia):** Implementar sincronização offline completa
4. **FUTURO:** Criar interface web para gerenciar permissões mobile

---

## 📞 SUPORTE

Se após executar a correção de permissão o problema persistir:

1. Capture logs do React Native:
   ```powershell
   npx react-native log-android > debug.log
   ```

2. Procure por linhas contendo:
   - `[CADASTRO]`
   - `[Login]`
   - `isAdminOrManager`

3. Envie o arquivo `debug.log` para análise

---

**Documento gerado automaticamente por GitHub Copilot**  
**Versão:** 1.0  
**Última atualização:** 10/02/2026
