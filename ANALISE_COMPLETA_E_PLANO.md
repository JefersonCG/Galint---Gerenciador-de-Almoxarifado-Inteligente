# 📱 ANÁLISE COMPLETA DO GALINT MOBILE + PLANO DE IMPLEMENTAÇÃO

**Data:** 14/02/2026  
**Versão Atual:** 1.0.0  
**Objetivo:** Paridade total com Flask Web + Melhorias Críticas

---

## 🔍 1. ANÁLISE DO CÓDIGO ATUAL

### ✅ **O QUE JÁ EXISTE E FUNCIONA:**

#### **Infraestrutura Offline:**
- ✅ **SQLite Local** (`offlineDb.js`)
  - Tabelas: `items` (cache de estoque) + `pending_ops` (fila de sincronização)
  - Métodos: `upsertItem`, `searchItems`, `addPendingOp`
  
- ✅ **Sincronização Automática** (`dbSync.js`)
  - Ciclo de 5 em 5 segundos
  - Push de operações pendentes
  - Pull de estoque atualizado

- ✅ **Detecção de Rede** (NetInfo)
  - Monitora conexão WiFi/dados
  - Aciona sincronização quando reconecta

#### **Funcionalidades Implementadas:**
- ✅ Login/Autenticação com JWT
- ✅ Scanner de código de barras
- ✅ Retirada de Material (individual)
- ✅ **Retirada Múltipla** (JÁ EXISTE na API! `retirar_multipla`)
- ✅ Devolução de Ferramenta (individual)
- ✅ Devolução de Material (individual)
- ✅ Retirada Fracionada de Líquidos
- ✅ Cadastro de itens
- ✅ Cadastro múltiplo
- ✅ Edição de itens (MASTER apenas)
- ✅ Relatórios (Diário, Mensal, Histórico)
- ✅ Controle de Ferramentas
- ✅ Sistema de permissões (master, gerencia, operacional)
- ✅ Auto-logout por inatividade (6 minutos)
- ✅ Heartbeat service (detecta desconexão)
- ✅ OTA Updates via Expo

---

## ⚠️ 2. PROBLEMAS IDENTIFICADOS

### 🔴 **CRÍTICO: Modo Offline Não Funciona Completamente**

**Problema Relatado pelo Usuário:**
> "O modo offline não funciona, após perder rede, não acesso a base de dados não registro nada, ficou algo inútil."

**Análise Técnica:**

#### **Causa Raiz:**
1. **Cache Local Insuficiente:**
   - O SQLite só armazena itens que foram buscados/acessados antes
   - Se o usuário perde conexão e tenta buscar um item novo, não encontra
   - Não há sincronização "full snapshot" do estoque na inicialização

2. **Falta de Feedback Visual:**
   - Não há indicador claro de "Offline Mode"
   - Usuário não sabe se está online ou offline
   - Não mostra quantas operações estão pendentes

3. **Sincronização Silenciosa:**
   - Sync Service roda em background sem notificar usuário
   - Se falhar, usuário não é informado
   - Não há retry manual

4. **dependência de Busca:**
   - O sistema carrega `searchOfflineItems('')` (busca vazia)
   - Se o banco local está vazio, não mostra nada
   - Não há pre-loading de itens frequentes

#### **Solução Necessária:**

```javascript
// Implementar:
1. Pre-cache de estoque completo ao fazer login
2. Banner visual: 🟢 Online | 🟡 Offline (X ops pendentes) | 🔄 Sincronizando
3. Botão manual "Sincronizar Agora"
4. Notificação de sucesso: "✅ 5 operações sincronizadas"
5. Retry automático com backoff exponencial
6. Persistência de último snapshot (mesmo sem internet)
```

---

### 🟡 **FUNCIONALIDADES AUSENTES:**

#### **1. Retirada Múltipla de Ferramentas** ⚠️
**Status:** API existe (`/api/mobile/retirar_multipla`), mas NÃO HÁ TELA no mobile

**Necessário:**
- Criar `RetiradaMultiplaScreen.js`
- Permitir selecionar múltiplas ferramentas
- Checkbox de seleção
- Confirmar tudo de uma vez

#### **2. Devolução Múltipla de Ferramentas** ❌
**Status:** NÃO EXISTE (nem API nem tela)

**Necessário:**
- Nova API no Flask: `/api/mobile/devolver_multipla_ferramentas`
- Nova tela: `DevolucaoMultiplaFerramentasScreen.js`
- Listar ferramentas ativas do funcionário
- Checkbox para selecionar várias
- Confirmar devolução em lote

#### **3. Devolução Múltipla de Materiais** ❌
**Status:** NÃO EXISTE

**Necessário:**
- Nova API no Flask: `/api/mobile/devolver_multipla_materiais`
- Nova tela: `DevolucaoMultiplaMaterialScreen.js`
- Similar à devolução de ferramentas

---

### 🟢 **MELHORIAS DE UX:**

#### **1. Remover "Estoque" da NavigationBar** ✅ SIMPLES
**Interpretação:** Usuário quer limpar ações ruins da tela principal

**Solução:** Na `EstoqueScreen.js`, remover botão/card que leva para uma tela de estoque pura (se existir)

#### **2. Melhorar Barra de Pesquisa**
**Atual:** Já tem autocomplete funcional
**Melhoria:** Adicionar histórico de buscas recentes (AsyncStorage)

---

## 🔗 3. SINCRONIZAÇÃO WEB ↔️ MOBILE

### **Funcionalidades Flask que FALTAM no Mobile:**

#### **A. Sistema de Unidades Dinâmicas** ⚠️
**Flask:** Detecta ROLO, PACOTE, CAIXA e pergunta:
- "Embalagem completa?" → Deduz embalagens inteiras
- "Unidades soltas?" → Sistema abre embalagens automaticamente

**Mobile:** NÃO TEM

**Solução:** Adicionar modal de seleção em `RetiradaScreen.js` e `DevolucaoMaterialScreen.js`

#### **B. Cálculo de "Saldo em Medidas"**
**Flask:** Exibe "26 rolos = 520 metros"

**Mobile:** Mostra apenas quantidade bruta

**Solução:** Formatar exibição no card de item

#### **C. Custódia Permanente vs Temporária**
**Flask:** Sistema diferencia ferramentas permanentes (sem alerta) de temporárias (alerta 30 dias)

**Mobile:** `FerramentasScreen.js` não faz essa distinção

**Solução:** Atualizar tela de ferramentas

---

## 🛠️ 4. PLANO DE IMPLEMENTAÇÃO

### **FASE 1: Correção Crítica do Modo Offline** (PRIORIDADE MÁXIMA)

#### **Etapa 1.1: Pre-cache Full Snapshot**
```javascript
// src/services/api.js
async preloadEstoqueCompleto() {
  const response = await this.client.get('/api/mobile/estoque/resumo');
  const items = response.data.items || [];
  await upsertItems(items); // Salva TUDO no SQLite
  await saveOnlineSnapshot({ totalItens: items.length, timestamp: Date.now() });
}

// Chamar no LoginScreen.js após sucesso:
await ApiService.preloadEstoqueCompleto();
```

#### **Etapa 1.2: Banner de Status de Conexão**
```javascript
// EstoqueScreen.js - Adicionar no topo
const [connectionStatus, setConnectionStatus] = useState('online');
const [pendingOpsCount, setPendingOpsCount] = useState(0);

// Render:
{connectionStatus === 'offline' && (
  <View style={styles.offlineBanner}>
    <Text>📵 Modo Offline - {pendingOpsCount} operações pendentes</Text>
    <TouchableOpacity onPress={handleManualSync}>
      <Text style={styles.syncButton}>🔄 Sincronizar</Text>
    </TouchableOpacity>
  </View>
)}
```

#### **Etapa 1.3: Sincronização Manual**
```javascript
const handleManualSync = async () => {
  setIsSyncing(true);
  const result = await ApiService.syncPendingOps();
  if (result.success && result.synced > 0) {
    Alert.alert('Sucesso', `✅ ${result.synced} operações sincronizadas`);
  }
  await loadEstoque('', true);
  setIsSyncing(false);
};
```

---

### **FASE 2: Novas Funcionalidades**

#### **Etapa 2.1: Retirada Múltipla de Ferramentas**

**2.1.1 - Criar API no Flask:**
```python
# galint_flask/views/api_mobile.py
@blueprint_mobile.post("/retirar_multipla_ferramentas")
@jwt_required()
def retirar_multipla_ferramentas():
    data = request.get_json()
    usuario_logado = get_jwt_identity()
    matricula_responsavel = data.get('matricula')
    itens = data.get('itens', [])  # [{ codigo, quantidade }, ...]
    
    resultados = []
    for item in itens:
        try:
            saida_id = inventory_service.registrar_saida(
                MovimentoPayload(
                    codigo=item['codigo'],
                    quantidade=item['quantidade'],
                    matricula=matricula_responsavel
                )
            )
            resultados.append({'codigo': item['codigo'], 'success': True, 'saida_id': saida_id})
        except Exception as e:
            resultados.append({'codigo': item['codigo'], 'success': False, 'error': str(e)})
    
    return jsonify({'success': True, 'resultados': resultados})
```

**2.1.2 - Criar Tela Mobile:**
```javascript
// src/screens/RetiradaMultiplaFerramentasScreen.js
// Lista ferramentas disponíveis
// Checkbox para selecionar múltiplas
// Botão "Confirmar Retirada"
```

#### **Etapa 2.2: Devolução Múltipla** (Similar ao 2.1)

---

### **FASE 3: Sincronização de Funcionalidades Flask**

#### **Etapa 3.1: Unidades Dinâmicas**
- Detectar tipo_embalagem_novo no item
- Mostrar modal de seleção
- Enviar `em_embalagens: true/false` na API

#### **Etapa 3.2: Saldo em Medidas**
- Formatar card: "26 rolos (520m disponíveis)"

---

### **FASE 4: Limpeza de UI**

#### **Etapa 4.1: Remover Tab Estoque**
- Verificar se há navegação de tabs (não encontrei)
- Se for um botão, removê-lo do grid de ações

---

## 📊 5. CHECKLIST DE IMPLEMENTAÇÃO

### ✅ **Concluído:**
- [x] Análise completa do código
- [x] Identificação de problemas
- [x] Plano detalhado

### 🔄 **Em Andamento:**
- [ ] Fase 1: Correção do modo offline
- [ ] Fase 2: Novas funcionalidades múltiplas
- [ ] Fase 3: Sincronização com Flask
- [ ] Fase 4: Limpeza de UI

### 📦 **Build Final:**
- [ ] Testar em dispositivo físico
- [ ] Validar modo offline
- [ ] Gerar APK com EAS
- [ ] Atualizar versão (1.1.0)

---

## 🎯 6. ESTIMATIVA DE TEMPO

| Fase | Descrição | Tempo Estimado |
|------|-----------|----------------|
| 1 | Correção do modo offline | 2-3 horas |
| 2 | Funcionalidades múltiplas (6 telas + 3 APIs) | 4-5 horas |
| 3 | Sincronização Flask | 2 horas |
| 4 | Limpeza UI | 30 min |
| **TOTAL** | | **8-10 horas** |

---

## 📝 7. PRÓXIMOS PASSOS

1. **Confirmar com usuário:**
   - Prioridade: Offline primeiro ou funcionalidades?
   - Confirmar interpretação de "eliminar estoque da parte inferior"

2. **Iniciar Implementação:**
   - Começar pela Fase 1 (crítico)
   - Testar cada fase antes de avançar

3. **Build e Deploy:**
   - Gerar APK de teste
   - Validar em produção simulada

---

**FIM DA ANÁLISE**
