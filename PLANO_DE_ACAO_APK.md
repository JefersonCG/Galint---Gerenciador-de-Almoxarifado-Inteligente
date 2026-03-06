# 📋 PLANO DE AÇÃO COMPLETO - GALINT APK

## 🎯 OBJETIVO

Resolver problema de permissão no APK e implementar todas as funcionalidades solicitadas:
1. ✅ **Corrigir permissão de cadastro** (CONCLUÍDO)
2. ⏳ Adicionar botão para Painel de Controle de Ferramentas
3. ⏳ Adicionar botão para Configuração do Telegram
4. ⏳ Implementar modo offline funcional com base idêntica ao web
5. ⏳ Gerar novo APK com todas as atualizações

---

# 📜 PASSO A PASSO DETALHADO

## 🔴 FASE 1: CORREÇÃO IMEDIATA (JÁ CONCLUÍDA ✅)

### Passo 1.1: Diagnóstico do Problema ✅
**Ação:** Identificar causa raiz do erro de permissão  
**Status:** ✅ CONCLUÍDO

**Problema encontrado:**
- Bug no código mobile: verificava apenas `cargo.includes('gerente')`, ignorando `setor.includes('gerente')`
- Usuário RONALDO tem `setor = "GERENTE"` mas `cargo = vazio`
- Código não permitia acesso mesmo com `is_admin = 1`

**Arquivos afetados:**
- `galint-mobile/src/screens/CadastroScreen.js` (linha 76)
- `galint-mobile/src/screens/CadastroMultiploScreen.js` (linha 43)

### Passo 1.2: Aplicar Correção no Código ✅
**Ação:** Corrigir lógica de verificação de permissões  
**Status:** ✅ CONCLUÍDO

**Alterações realizadas:**

**Arquivo 1:** `CadastroScreen.js`
```javascript
// ANTES (bug):
return cargo.includes('gerente') || cargo.includes('supervisor') || setor.includes('supervisor');

// DEPOIS (corrigido):
return cargo.includes('gerente') || 
       setor.includes('gerente') ||    // ← ADICIONADO
       cargo.includes('supervisor') || 
       setor.includes('supervisor');
```

**Arquivo 2:** `CadastroMultiploScreen.js`
```javascript
// ANTES (bug):
return cargo.includes('supervisor') || setor.includes('supervisor');

// DEPOIS (corrigido):
return cargo.includes('supervisor') || 
       cargo.includes('gerente') ||    // ← ADICIONADO
       setor.includes('supervisor') || 
       setor.includes('gerente');      // ← ADICIONADO
```

---

## 🟡 FASE 2: ADICIONAR BOTÕES DE ACESSO (30 MINUTOS)

### Passo 2.1: Modificar MenuScreen para Adicionar Botões

**Arquivo:** `galint-mobile/src/screens/MenuScreen.js` (ou `EstoqueScreen.js` se for o menu principal)

**Ação:** Adicionar dois novos botões no layout principal

**Código a adicionar:**

#### 2.1.1 Importar módulo Linking
```javascript
// No topo do arquivo, adicionar ao import do React Native:
import {
    View,
    Text,
    TouchableOpacity,
    StyleSheet,
    Alert,
    Linking,  // ← ADICIONAR ESTE
    // ... outros imports existentes
} from 'react-native';
```

#### 2.1.2 Adicionar State para Servidor
```javascript
// Dentro do componente, adicionar useState:
const [serverConfig, setServerConfig] = useState({ ip: '', port: '' });

// Adicionar useEffect para carregar config:
useEffect(() => {
    const loadConfig = async () => {
        try {
            const ip = await AsyncStorage.getItem('serverIP');
            const port = await AsyncStorage.getItem('serverPort');
            if (ip && port) {
                setServerConfig({ ip, port });
            }
        } catch (error) {
            console.error('Erro ao carregar config:', error);
        }
    };
    loadConfig();
}, []);
```

#### 2.1.3 Adicionar Botões no Render
```javascript
{/* Seção de Acesso Rápido */}
<View style={styles.sectionContainer}>
    <Text style={styles.sectionTitle}>🔗 Acesso Rápido</Text>
    
    {/* Botão Painel de Ferramentas */}
    <TouchableOpacity
        style={[styles.actionButton, { backgroundColor: '#8b5cf6' }]}
        onPress={() => {
            const url = `http://${serverConfig.ip}:${serverConfig.port}/ferramentas/painel`;
            Linking.openURL(url)
                .then(() => console.log('Painel aberto no navegador'))
                .catch(() => {
                    Alert.alert(
                        'Erro',
                        'Não foi possível abrir o navegador.\n\nURL: ' + url,
                        [
                            { text: 'Copiar URL', onPress: () => Clipboard.setString(url) },
                            { text: 'OK' }
                        ]
                    );
                });
        }}
        disabled={!serverConfig.ip}
    >
        <Text style={styles.buttonIcon}>🔧</Text>
        <Text style={styles.buttonText}>Painel de Ferramentas</Text>
        {!serverConfig.ip && <Text style={styles.buttonSubtext}>(Configure servidor)</Text>}
    </TouchableOpacity>
    
    {/* Botão Configuração Telegram */}
    <TouchableOpacity
        style={[styles.actionButton, { backgroundColor: '#0088cc' }]}
        onPress={() => {
            const url = `http://${serverConfig.ip}:${serverConfig.port}/telegram/config`;
            Linking.openURL(url)
                .then(() => console.log('Config Telegram aberta no navegador'))
                .catch(() => {
                    Alert.alert(
                        'Erro',
                        'Não foi possível abrir o navegador.\n\nURL: ' + url,
                        [
                            { text: 'Copiar URL', onPress: () => Clipboard.setString(url) },
                            { text: 'OK' }
                        ]
                    );
                });
        }}
        disabled={!serverConfig.ip}
    >
        <Text style={styles.buttonIcon}>📱</Text>
        <Text style={styles.buttonText}>Configuração Telegram</Text>
        {!serverConfig.ip && <Text style={styles.buttonSubtext}>(Configure servidor)</Text>}
    </TouchableOpacity>
</View>
```

#### 2.1.4 Adicionar Estilos
```javascript
const styles = StyleSheet.create({
    // ... estilos existentes ...
    
    sectionContainer: {
        marginVertical: 15,
        paddingHorizontal: 20,
    },
    sectionTitle: {
        fontSize: 16,
        fontWeight: 'bold',
        color: '#1f2937',
        marginBottom: 10,
    },
    actionButton: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 15,
        paddingHorizontal: 20,
        borderRadius: 12,
        marginBottom: 10,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.1,
        shadowRadius: 4,
        elevation: 3,
    },
    buttonIcon: {
        fontSize: 24,
        marginRight: 12,
    },
    buttonText: {
        fontSize: 16,
        fontWeight: '600',
        color: '#fff',
        flex: 1,
    },
    buttonSubtext: {
        fontSize: 11,
        color: 'rgba(255,255,255,0.7)',
        fontStyle: 'italic',
    },
});
```

**Tempo estimado:** 30 minutos

---

## 🟢 FASE 3: MODO OFFLINE COMPLETO (2-4 HORAS)

### Passo 3.1: Implementar Serviço de Sincronização

**Arquivo NOVO:** `galint-mobile/src/services/dbSync.js`

**Código completo:**
```javascript
/**
 * Serviço de sincronização bidirecional (online/offline)
 */
import ApiService from './api';
import { 
    listPendingOps, 
    markPendingOpSynced, 
    markPendingOpFailed, 
    incrementPendingRetry,
    clearSyncedOps 
} from './offlineDb';

/**
 * Sincroniza todas as operações pendentes com o servidor
 * @returns {Promise<{success: boolean, synced: number, failed: number}>}
 */
export async function syncPendingOperations() {
    console.log('[Sync] 🔄 Iniciando sincronização...');
    
    const pending = await listPendingOps();
    
    if (pending.length === 0) {
        console.log('[Sync] ✅ Nenhuma operação pendente');
        return { success: true, synced: 0, failed: 0 };
    }
    
    console.log(`[Sync] 📦 ${pending.length} operação(ões) pendente(s)`);
    
    let syncedCount = 0;
    let failedCount = 0;
    const errors = [];
    
    for (const op of pending) {
        try {
            console.log(`[Sync] ⏳ Processando ${op.operation_type} (ID: ${op.id})...`);
            
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
                    console.warn(`[Sync] ⚠️ Tipo desconhecido: ${op.operation_type}`);
                    await markPendingOpFailed(op.id);
                    failedCount++;
                    errors.push(`Tipo desconhecido: ${op.operation_type}`);
                    continue;
            }
            
            if (result?.success !== false) {
                await markPendingOpSynced(op.id);
                syncedCount++;
                console.log(`[Sync] ✅ ${op.operation_type} sincronizado (ID: ${op.id})`);
            } else {
                await incrementPendingRetry(op.id);
                failedCount++;
                const errorMsg = result?.message || 'Erro desconhecido';
                console.error(`[Sync] ❌ ${op.operation_type} falhou: ${errorMsg}`);
                errors.push(`${op.operation_type}: ${errorMsg}`);
            }
            
        } catch (error) {
            await incrementPendingRetry(op.id);
            failedCount++;
            const errorMsg = error?.message || String(error);
            console.error(`[Sync] ❌ Erro ao sincronizar ${op.operation_type}:`, error);
            errors.push(`${op.operation_type}: ${errorMsg}`);
        }
        
        // Pequeno delay para não sobrecarregar servidor
        await new Promise(resolve => setTimeout(resolve, 100));
    }
    
    // Limpar operações antigas já sincronizadas (mais de 7 dias)
    try {
        await clearSyncedOps(7);
    } catch (error) {
        console.warn('[Sync] Falha ao limpar operações antigas:', error);
    }
    
    console.log(`[Sync] 🏁 Concluído: ${syncedCount} OK, ${failedCount} falhas`);
    
    return { 
        success: true, 
        synced: syncedCount, 
        failed: failedCount,
        errors 
    };
}

/**
 * Agenda sincronização periódica em background
 * @param {number} intervalMinutes - Intervalo em minutos
 * @returns {number} - ID do interval para cancelar depois
 */
export function schedulePeriodicSync(intervalMinutes = 5) {
    console.log(`[Sync] 📅 Agendando sync a cada ${intervalMinutes} minutos`);
    
    const intervalMs = intervalMinutes * 60 * 1000;
    
    return setInterval(async () => {
        try {
            const isOnline = await ApiService.isOnline();
            if (isOnline) {
                const result = await syncPendingOperations();
                if (result.synced > 0 || result.failed > 0) {
                    console.log(`[Sync] 📊 Sync periódico: ${result.synced} OK, ${result.failed} falhas`);
                }
            }
        } catch (error) {
            console.error('[Sync] ❌ Erro no sync periódico:', error);
        }
    }, intervalMs);
}

export default {
    syncPendingOperations,
    schedulePeriodicSync,
};
```

### Passo 3.2: Modificar Serviço de API para Download Completo

**Arquivo:** `galint-mobile/src/services/api.js`

**Localizar função `login()` (linha ~335) e adicionar:**

```javascript
async login(username, password) {
    try {
        // ... código existente de autenticação ...
        
        if (!success || !token || !user) {
            return { success: false, message: payload?.message || 'Erro ao fazer login' };
        }

        // Normalizar is_admin
        if (user) {
            // ... código existente de normalização ...
        }

        await AsyncStorage.setItem('token', token);
        await AsyncStorage.setItem('user', JSON.stringify(user));
        this.token = token;
        
        // ⭐ NOVO: Baixar estoque completo para modo offline
        try {
            console.log('[Login] 📥 Baixando estoque completo para modo offline...');
            const estoqueResponse = await this.client.get('/api/mobile/estoque', {
                headers: { Authorization: `Bearer ${token}` },
                timeout: 30000, // 30 segundos
            });
            
            if (estoqueResponse.data?.data && Array.isArray(estoqueResponse.data.data)) {
                const itens = estoqueResponse.data.data;
                await upsertItems(itens); // Salvar no SQLite local
                console.log(`[Login] ✅ ${itens.length} itens salvos para modo offline`);
                
                // Salvar timestamp do último sync
                await AsyncStorage.setItem('last_full_sync', new Date().toISOString());
            }
        } catch (offlineError) {
            console.warn('[Login] ⚠️ Falha ao baixar estoque offline:', offlineError.message);
            // Não bloquear login se falhar
        }
        
        console.log('[Login] ✅ Login concluído com sucesso');
        return { success: true, user };
        
    } catch (error) {
        // ... código existente de tratamento de erro ...
    }
}
```

### Passo 3.3: Adicionar Indicador Visual de Sincronização

**Arquivo:** `galint-mobile/src/screens/MenuScreen.js` (ou `EstoqueScreen.js`)

**Adicionar ao componente:**

```javascript
import { syncPendingOperations } from '../services/dbSync';
import { listPendingOps } from '../services/offlineDb';

// Dentro do componente:
const [pendingCount, setPendingCount] = useState(0);
const [syncing, setSyncing] = useState(false);
const [lastSync, setLastSync] = useState(null);

// Verificar operações pendentes periodicamente
useEffect(() => {
    const checkPending = async () => {
        try {
            const ops = await listPendingOps();
            setPendingCount(ops.length);
            
            // Carregar último sync
            const lastSyncStr = await AsyncStorage.getItem('last_full_sync');
            if (lastSyncStr) {
                setLastSync(new Date(lastSyncStr));
            }
        } catch (error) {
            console.error('[Menu] Erro ao verificar pendências:', error);
        }
    };
    
    checkPending();
    const interval = setInterval(checkPending, 10000); // A cada 10s
    
    return () => clearInterval(interval);
}, []);

// Função para sincronizar manualmente
const handleManualSync = async () => {
    if (syncing) return;
    
    setSyncing(true);
    try {
        const result = await syncPendingOperations();
        
        Alert.alert(
            'Sincronização Concluída',
            `✅ ${result.synced} operação(ões) enviada(s)\n` +
            `${result.failed > 0 ? `❌ ${result.failed} falha(s)` : ''}`,
            [{ text: 'OK' }]
        );
        
        // Atualizar contador
        const ops = await listPendingOps();
        setPendingCount(ops.length);
        
    } catch (error) {
        Alert.alert('Erro', 'Falha ao sincronizar: ' + error.message);
    } finally {
        setSyncing(false);
    }
};

// No render, adicionar badge de sincronização:
{pendingCount > 0 && (
    <View style={styles.syncBadge}>
        <View style={styles.syncBadgeHeader}>
            <Text style={styles.syncBadgeIcon}>⚠️</Text>
            <Text style={styles.syncBadgeText}>
                {pendingCount} operação(ões) pendente(s)
            </Text>
        </View>
        
        <TouchableOpacity 
            style={[styles.syncButton, syncing && styles.syncButtonDisabled]}
            onPress={handleManualSync}
            disabled={syncing}
        >
            <Text style={styles.syncButtonIcon}>{syncing ? '⏳' : '🔄'}</Text>
            <Text style={styles.syncButtonText}>
                {syncing ? 'Sincronizando...' : 'Sincronizar Agora'}
            </Text>
        </TouchableOpacity>
    </View>
)}

{lastSync && (
    <Text style={styles.lastSyncText}>
        Última sincronização: {formatLastSync(lastSync)}
    </Text>
)}
```

**Adicionar estilos:**
```javascript
const styles = StyleSheet.create({
    // ... estilos existentes ...
    
    syncBadge: {
        backgroundColor: '#fef3c7',
        borderLeftWidth: 4,
        borderLeftColor: '#f59e0b',
        padding: 15,
        marginHorizontal: 20,
        marginVertical: 10,
        borderRadius: 8,
    },
    syncBadgeHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: 10,
    },
    syncBadgeIcon: {
        fontSize: 20,
        marginRight: 8,
    },
    syncBadgeText: {
        fontSize: 14,
        fontWeight: '600',
        color: '#92400e',
        flex: 1,
    },
    syncButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#f59e0b',
        paddingVertical: 10,
        paddingHorizontal: 15,
        borderRadius: 6,
        marginTop: 5,
    },
    syncButtonDisabled: {
        backgroundColor: '#d1d5db',
    },
    syncButtonIcon: {
        fontSize: 16,
        marginRight: 6,
    },
    syncButtonText: {
        color: '#fff',
        fontSize: 14,
        fontWeight: '600',
    },
    lastSyncText: {
        fontSize: 12,
        color: '#6b7280',
        textAlign: 'center',
        marginTop: 5,
    },
});

// Função helper para formatar data:
const formatLastSync = (date) => {
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'agora há pouco';
    if (diffMins < 60) return `há ${diffMins} minuto(s)`;
    
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `há ${diffHours} hora(s)`;
    
    const diffDays = Math.floor(diffHours / 24);
    return `há ${diffDays} dia(s)`;
};
```

### Passo 3.4: Integrar Sync Periódico no App Principal

**Arquivo:** `galint-mobile/App.js`

```javascript
import { syncPendingOperations, schedulePeriodicSync } from './src/services/dbSync';

// Dentro do componente App ou após login bem-sucedido:
useEffect(() => {
    let syncInterval = null;
    
    // Iniciar sync periódico quando app estiver online
    const startPeriodicSync = async () => {
        const isOnline = await ApiService.isOnline();
        if (isOnline) {
            // Sync imediato ao iniciar
            syncPendingOperations();
            
            // Agendar sync a cada 5 minutos
            syncInterval = schedulePeriodicSync(5);
        }
    };
    
    startPeriodicSync();
    
    // Limpar interval ao desmontar
    return () => {
        if (syncInterval) {
            clearInterval(syncInterval);
        }
    };
}, []);
```

**Tempo estimado:** 3-4 horas

---

## 🔵 FASE 4: GERAÇÃO DO NOVO APK (1 HORA)

### Passo 4.1: Atualizar Versão do App

**Arquivo:** `galint-mobile/app.json`

```json
{
  "expo": {
    "name": "GALINT Almoxarifado",
    "slug": "galint-almoxarifado",
    "version": "1.3.1",              // ← INCREMENTAR (era 1.3.0)
    "orientation": "portrait",
    "icon": "./assets/galint-logo.png",
    "android": {
      "versionCode": 14,              // ← INCREMENTAR (era 13)
      "package": "com.sublimemax.galint",
      "adaptiveIcon": {
        "foregroundImage": "./assets/galint-logo.png",
        "backgroundColor": "#FFFFFF"
      },
      "permissions": [
        "CAMERA",
        "READ_EXTERNAL_STORAGE",
        "WRITE_EXTERNAL_STORAGE"
      ]
    }
  }
}
```

### Passo 4.2: Instalar Dependências (se houver novas)

**Terminal PowerShell:**
```powershell
cd galint-mobile
npm install
```

### Passo 4.3: Build APK via EAS

**Opção A: Build em Cloud (Recomendado)**

```powershell
# 1. Logar no EAS (se ainda não logou):
npx eas-cli login

# 2. Configurar build (se primeira vez):
npx eas build:configure

# 3. Executar build:
npx eas build --profile preview --platform android

# Aguardar 20-40 minutos
# Link do build aparecerá no console
# Exemplo: https://expo.dev/accounts/seu-usuario/projects/galint/builds/abc123

# 4. Quando concluir, baixar APK:
# O link de download aparecerá no terminal
# Ou acessar: https://expo.dev/accounts/seu-usuario/projects/galint/builds
```

**Opção B: Build Local (Mais Rápido, Requer Android SDK)**

```powershell
# 1. Preparar projeto:
cd galint-mobile
npx expo prebuild --platform android

# 2. Build APK:
cd android
.\gradlew assembleRelease

# APK gerado em:
# android\app\build\outputs\apk\release\app-release.apk

# 3. Copiar APK para local acessível:
Copy-Item "app\build\outputs\apk\release\app-release.apk" "..\..\galint-1.3.1.apk"
```

### Passo 4.4: Assinar APK (se build local)

**Se o APK não estiver assinado:**

```powershell
# 1. Criar keystore (primeira vez):
keytool -genkey -v -keystore galint-release-key.jks -keyalg RSA -keysize 2048 -validity 10000 -alias galint-key

# 2. Assinar APK:
jarsigner -verbose -sigalg SHA256withRSA -digestalg SHA-256 -keystore galint-release-key.jks galint-1.3.1.apk galint-key

# 3. Otimizar (zipalign):
zipalign -v 4 galint-1.3.1.apk galint-1.3.1-aligned.apk
```

**Tempo estimado:** 40-60 minutos (dependendo do método)

---

## 🟣 FASE 5: INSTALAÇÃO E TESTES (30 MINUTOS)

### Passo 5.1: Instalar Novo APK no Dispositivo

**Método 1: Via USB (Recomendado)**

```powershell
# 1. Conectar celular via USB
# 2. Habilitar Depuração USB no celular:
#    Configurações → Sobre o telefone → Tocar 7x em "Número da versão"
#    Configurações → Sistema → Opções do desenvolvedor → Depuração USB ✓

# 3. Instalar APK:
adb install -r galint-1.3.1.apk
# (-r = substituir versão existente)

# Se aparecer erro "adb não reconhecido":
# Baixar Android Platform Tools: https://developer.android.com/studio/releases/platform-tools
```

**Método 2: Via WhatsApp/Email**

1. Enviar arquivo `galint-1.3.1.apk` para o celular via WhatsApp
2. Abrir arquivo no celular
3. Permitir instalação de fontes desconhecidas se solicitado:
   - Configurações → Segurança → Fontes desconhecidas ✓
4. Confirmar substituição da versão anterior

### Passo 5.2: Limpar Cache do App (IMPORTANTE!)

**No celular Android:**

1. Ir em: **Configurações → Apps → GALINT Almoxarifado**
2. Tocar em: **Armazenamento**
3. Tocar em: **Limpar dados** (não apenas cache!)
4. Confirmar

**Ou via ADB:**
```powershell
adb shell pm clear com.sublimemax.galint
```

### Passo 5.3: Checklist de Testes

**Teste 1: Login e Permissões**
- [ ] Fazer login com usuário RONALDO
- [ ] Verificar se consegue abrir tela de Cadastro
- [ ] Verificar se mensagem "Sem permissão" NÃO aparece
- [ ] Tentar cadastrar um item de teste

**Teste 2: Novos Botões**
- [ ] Verificar se botão "Painel de Ferramentas" aparece
- [ ] Tocar no botão → deve abrir navegador
- [ ] Verificar se botão "Config Telegram" aparece
- [ ] Tocar no botão → deve abrir navegador

**Teste 3: Modo Offline**
- [ ] Desabilitar WiFi e dados móveis
- [ ] Tentar pesquisar itens → deve funcionar (dados locais)
- [ ] Tentar cadastrar item → deve registrar como pendente
- [ ] Verificar badge "X operação(ões) pendente(s)"
- [ ] Reabilitar conexão
- [ ] Tocar em "Sincronizar Agora"
- [ ] Verificar se operações foram enviadas

**Teste 4: Funcionalidades Existentes (Regressão)**
- [ ] Escanear código de barras
- [ ] Registrar retirada de item
- [ ] Devolver ferramenta
- [ ] Gerar relatórios
- [ ] Visualizar estoque

---

## 📊 RESUMO DE TEMPO ESTIMADO

| Fase | Descrição | Tempo | Status |
|------|-----------|-------|--------|
| **1** | Correção imediata | 30 min | ✅ CONCLUÍDA |
| **2** | Adicionar botões | 30 min | ⏳ PENDENTE |
| **3** | Modo offline | 3-4h | ⏳ PENDENTE |
| **4** | Geração APK | 1h | ⏳ PENDENTE |
| **5** | Instalação e testes | 30 min | ⏳ PENDENTE |
| **TOTAL** | | **5-7 horas** | **20% concluído** |

---

## 🎯 PRÓXIMA AÇÃO IMEDIATA

### OPÇÃO 1: Build Rápido (Sem Offline Completo)
**Tempo:** 1.5 horas

1. ✅ Correção já aplicada
2. ⏳ Adicionar botões (30 min)
3. ⏳ Gerar APK (40 min)
4. ⏳ Instalar e testar (20 min)

### OPÇÃO 2: Build Completo (Com Tudo)
**Tempo:** 5-7 horas

1. ✅ Correção já aplicada
2. ⏳ Adicionar botões (30 min)
3. ⏳ Implementar modo offline completo (3-4h)
4. ⏳ Gerar APK (40 min)
5. ⏳ Instalar e testar (30 min)

---

## 📞 COMANDOS RÁPIDOS DE EMERGÊNCIA

**Verificar se usuário tem permissão:**
```powershell
.\.venv\Scripts\python.exe -c "from galint_flask import create_app; from galint_flask.models import Usuario; app = create_app(); ctx = app.app_context(); ctx.push(); user = Usuario.query.filter_by(matricula='MATRICULA').first(); print(f'is_admin: {user.is_admin}, cargo: {user.cargo}, setor: {user.setor}');"
```

**Tornar usuário admin rapidamente:**
```powershell
.\.venv\Scripts\python.exe -c "from galint_flask import create_app; from galint_flask.models import Usuario, db; app = create_app(); ctx = app.app_context(); ctx.push(); user = Usuario.query.filter_by(matricula='MATRICULA').first(); user.is_admin = 1; db.session.commit(); print('✅ OK');"
```

**Verificar logs do React Native:**
```powershell
# Conectar celular via USB
npx react-native log-android
# Procurar por [CADASTRO] ou [Login]
```

**Desinstalar APK antigo:**
```powershell
adb uninstall com.sublimemax.galint
```

---

## 📚 DOCUMENTAÇÃO GERADA

1. **DIAGNOSTICO_E_PLANO_APK.md** - Análise técnica completa
2. **CORRECAO_APLICADA_APK.md** - Detalhes da correção aplicada
3. **PLANO_DE_ACAO_APK.md** - Este documento (passo a passo)

---

**Plano criado por GitHub Copilot**  
**Data:** 10/02/2026 14:40  
**Versão:** 1.0
