# GALINT Mobile - Atualizações UI/UX e Rastreabilidade

## 📋 Resumo das Mudanças

### ✅ Concluído
1. **Formulário Web** - Redesenhado com estilo "Soft Depth"
   - Layout de página única contínua
   - Sombras suaves e profundidade visual
   - Campos condicionais com destaque dinâmico
   - Mobile-first responsivo

### 🔧 Pendências Mobile

## 1. Problema: Administrador Não Consegue Cadastrar

### Diagnóstico
- ✅ Backend API está correto (`/api/mobile/estoque` verifica `is_admin` ou `supervisor`)
- ❌ Mobile pode estar enviando token inválido ou user object incompleto

### Checklist de Correção

#### A. Verificar Autenticação no Login
Arquivo: `galint-mobile/src/screens/LoginScreen.js`

```javascript
// Após login bem-sucedido, garantir que user.is_admin seja salvo corretamente
const user = response.data.user;
console.log('[LOGIN] User completo:', JSON.stringify(user, null, 2));

// Verificar se is_admin está vindo como boolean, int ou string
if (user) {
    // Normalizar is_admin para boolean
    user.is_admin = user.is_admin === true || 
                    user.is_admin === 1 || 
                    user.is_admin === '1' || 
                    String(user.is_admin || '').trim() === '1';
    
    await AsyncStorage.setItem('user', JSON.stringify(user));
}
```

#### B. Verificar Envio do Token
Arquivo: `galint-mobile/src/services/api.js`

```javascript
// No método cadastrarItem, garantir que token está sendo enviado
async cadastrarItem(itemData) {
    const token = await AsyncStorage.getItem('token');
    console.log('[API] Token:', token ? 'presente' : 'ausente');
    console.log('[API] Cadastrando:', itemData);
    
    // Verificar se headers Authorization está correto
    const response = await this.client.post('/api/mobile/estoque', itemData, {
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        }
    });
}
```

#### C. Debug no CadastroScreen
Arquivo: `galint-mobile/src/screens/CadastroScreen.js`

```javascript
// Adicionar logs detalhados
useEffect(() => {
    console.log('[CADASTRO] User:', JSON.stringify(user, null, 2));
    console.log('[CADASTRO] is_admin:', user?.is_admin);
    console.log('[CADASTRO] isAdminOrManager:', isAdminOrManager(user));
    
    if (!isAdminOrManager(user)) {
        console.log('[CADASTRO] Permissão negada - voltando');
        Alert.alert('Sem permissão', 'Apenas administrador, supervisor ou gerente pode cadastrar itens.');
        navigation.goBack();
    }
}, [user]);
```

### Solução Rápida (Temporária)
Se o problema persistir, adicionar bypass temporário para debug:

```javascript
// Em CadastroScreen.js - APENAS PARA DEBUG
const BYPASS_PERMISSION_CHECK = true; // REMOVER DEPOIS

useEffect(() => {
    if (!BYPASS_PERMISSION_CHECK && !isAdminOrManager(user)) {
        Alert.alert('Sem permissão', 'Apenas administrador, supervisor ou gerente pode cadastrar itens.');
        navigation.goBack();
    }
}, [user]);
```

## 2. Adicionar Campos de Rastreabilidade ao Mobile

### Arquivos a Modificar

#### A. CadastroScreen.js - Adicionar Campos

```javascript
const [formData, setFormData] = useState({
    codigo_barras: route.params?.barcode || '',
    nota_fiscal: '',
    descricao: '',
    marca: '',
    categoria: 'Material Elétrico',
    localizacao: '',
    quantidade: '',
    unidade: 'Unidade',
    numero_serie: '',
    modelo: '',
    // NOVOS CAMPOS DE RASTREABILIDADE
    data_entrada: '',
    data_fabricacao: '',
    data_validade: '',
    tipo_embalagem: '',
    grandeza_referencia: '',
    densidade: '',
});
```

#### B. Adicionar DatePicker no UI

```javascript
import DateTimePicker from '@react-native-community/datetimepicker';

// Adicionar nova seção após "Classificação"
<View style={styles.sectionCard}>
    <Text style={styles.sectionTitle}>Rastreabilidade</Text>
    
    <View style={styles.inputGroup}>
        <Text style={styles.label}>Data de Entrada</Text>
        <TouchableOpacity
            style={styles.dateInput}
            onPress={() => setShowDateEntrada(true)}
        >
            <Text style={styles.dateText}>
                {formData.data_entrada || 'Selecionar data'}
            </Text>
        </TouchableOpacity>
        {showDateEntrada && (
            <DateTimePicker
                value={formData.data_entrada ? new Date(formData.data_entrada) : new Date()}
                mode="date"
                display="default"
                onChange={(event, selectedDate) => {
                    setShowDateEntrada(false);
                    if (selectedDate) {
                        setFormData({
                            ...formData,
                            data_entrada: selectedDate.toISOString().split('T')[0]
                        });
                    }
                }}
            />
        )}
    </View>
    
    <View style={styles.inputGroup}>
        <Text style={styles.label}>Data de Fabricação</Text>
        <TouchableOpacity
            style={styles.dateInput}
            onPress={() => setShowDateFabricacao(true)}
        >
            <Text style={styles.dateText}>
                {formData.data_fabricacao || 'Selecionar data'}
            </Text>
        </TouchableOpacity>
        {showDateFabricacao && (
            <DateTimePicker
                value={formData.data_fabricacao ? new Date(formData.data_fabricacao) : new Date()}
                mode="date"
                display="default"
                onChange={(event, selectedDate) => {
                    setShowDateFabricacao(false);
                    if (selectedDate) {
                        setFormData({
                            ...formData,
                            data_fabricacao: selectedDate.toISOString().split('T')[0]
                        });
                    }
                }}
            />
        )}
    </View>
    
    <View style={styles.inputGroup}>
        <Text style={styles.label}>Data de Validade</Text>
        <TouchableOpacity
            style={styles.dateInput}
            onPress={() => setShowDateValidade(true)}
        >
            <Text style={styles.dateText}>
                {formData.data_validade || 'Selecionar data'}
            </Text>
        </TouchableOpacity>
        {showDateValidade && (
            <DateTimePicker
                value={formData.data_validade ? new Date(formData.data_validade) : new Date()}
                mode="date"
                display="default"
                onChange={(event, selectedDate) => {
                    setShowDateValidade(false);
                    if (selectedDate) {
                        setFormData({
                            ...formData,
                            data_validade: selectedDate.toISOString().split('T')[0]
                        });
                        calcularDiasValidade(selectedDate);
                    }
                }}
            />
        )}
        <Text style={styles.validadeInfo}>{diasValidadeText}</Text>
    </View>
</View>
```

#### C. Adicionar Seção de Unidades Dinâmicas

```javascript
<View style={styles.sectionCard}>
    <Text style={styles.sectionTitle}>Unidades Dinâmicas</Text>
    
    <View style={styles.inputGroup}>
        <Text style={styles.label}>Tipo de Embalagem</Text>
        <View style={styles.radioGroup}>
            {['Lata', 'Rolo', 'Pacote', 'Caixa', 'Nenhum'].map((tipo) => (
                <TouchableOpacity
                    key={tipo}
                    style={styles.radioOption}
                    onPress={() => {
                        setFormData({
                            ...formData,
                            tipo_embalagem: tipo === 'Nenhum' ? '' : tipo
                        });
                    }}
                >
                    <View style={[
                        styles.radioCircle,
                        formData.tipo_embalagem === (tipo === 'Nenhum' ? '' : tipo) && styles.radioCircleSelected
                    ]}>
                        {formData.tipo_embalagem === (tipo === 'Nenhum' ? '' : tipo) && (
                            <View style={styles.radioCircleInner} />
                        )}
                    </View>
                    <Text style={styles.radioLabel}>{tipo}</Text>
                </TouchableOpacity>
            ))}
        </View>
    </View>
    
    {formData.tipo_embalagem && (
        <View style={styles.conditionalFields}>
            <View style={styles.inputGroup}>
                <Text style={styles.label}>{getGrandezaLabel()}</Text>
                <TextInput
                    style={styles.input}
                    value={formData.grandeza_referencia}
                    onChangeText={(text) => {
                        setFormData({...formData, grandeza_referencia: text});
                        calcularConversao();
                    }}
                    placeholder="Ex: 18"
                    keyboardType="decimal-pad"
                />
                <Text style={styles.hintText}>{getGrandezaHint()}</Text>
            </View>
            
            {formData.tipo_embalagem === 'Lata' && (
                <View style={styles.inputGroup}>
                    <Text style={styles.label}>Densidade (kg/L)</Text>
                    <TextInput
                        style={styles.input}
                        value={formData.densidade}
                        onChangeText={(text) => {
                            setFormData({...formData, densidade: text});
                            calcularConversao();
                        }}
                        placeholder="Ex: 1.5"
                        keyboardType="decimal-pad"
                    />
                    <Text style={styles.hintText}>Para converter kg em litros</Text>
                </View>
            )}
            
            {conversaoPreview && (
                <View style={styles.conversionPreview}>
                    <Text style={styles.conversionTitle}>Preview de Conversão:</Text>
                    <Text style={styles.conversionText}>{conversaoPreview}</Text>
                </View>
            )}
        </View>
    )}
</View>
```

#### D. Adicionar Lógica de Conversão

```javascript
const calcularConversao = () => {
    const tipo = formData.tipo_embalagem;
    const qtd = parseFloat(formData.quantidade) || 0;
    const grandeza = parseFloat(formData.grandeza_referencia) || 0;
    const densidade = parseFloat(formData.densidade) || 0;
    
    if (!tipo || qtd === 0 || grandeza === 0) {
        setConversaoPreview('');
        return;
    }
    
    let preview = '';
    
    switch(tipo) {
        case 'Lata':
            const kg = qtd * grandeza;
            preview = `${qtd} latas = ${kg.toFixed(2)} kg`;
            if (densidade > 0) {
                const litros = kg / densidade;
                preview += `\n${kg.toFixed(2)} kg = ${litros.toFixed(2)} litros`;
            }
            break;
        case 'Rolo':
            const metros = qtd * grandeza;
            preview = `${qtd} rolos = ${metros.toFixed(2)} metros`;
            break;
        case 'Pacote':
        case 'Caixa':
            const unidades = qtd * grandeza;
            const tipoNome = tipo === 'Pacote' ? 'pacotes' : 'caixas';
            preview = `${qtd} ${tipoNome} = ${unidades.toFixed(0)} unidades`;
            break;
    }
    
    setConversaoPreview(preview);
};

const calcularDiasValidade = (date) => {
    if (!date) {
        setDiasValidadeText('');
        return;
    }
    
    const hoje = new Date();
    const validade = new Date(date);
    const diffTime = validade - hoje;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    
    if (diffDays < 0) {
        setDiasValidadeText(`⚠️ Produto vencido há ${Math.abs(diffDays)} dias`);
    } else if (diffDays <= 30) {
        setDiasValidadeText(`⚠️ Vence em ${diffDays} dias`);
    } else {
        setDiasValidadeText(`✓ Vence em ${diffDays} dias`);
    }
};

const getGrandezaLabel = () => {
    switch(formData.tipo_embalagem) {
        case 'Lata': return 'Peso por Lata (kg)';
        case 'Rolo': return 'Comprimento por Rolo (metros)';
        case 'Pacote': return 'Unidades por Pacote';
        case 'Caixa': return 'Unidades por Caixa';
        default: return 'Grandeza de Referência';
    }
};

const getGrandezaHint = () => {
    switch(formData.tipo_embalagem) {
        case 'Lata': return 'Ex: 18 kg por lata';
        case 'Rolo': return 'Ex: 100 metros por rolo';
        case 'Pacote': return 'Ex: 50 unidades por pacote';
        case 'Caixa': return 'Ex: 100 unidades por caixa';
        default: return '';
    }
};
```

#### E. Atualizar handleSubmit

```javascript
const dataToSend = {
    codigo_barras: String(formData.codigo_barras || '').trim(),
    descricao: String(formData.descricao || '').trim(),
    categoria: String(formData.categoria || 'Material Eletrico').trim(),
    localizacao: String(formData.localizacao || '').trim(),
    marca: String(formData.marca || '').trim(),
    nota_fiscal: String(formData.nota_fiscal || '').trim(),
    quantidade: quantidadeInt,
    unidade: String(formData.unidade || 'Unidade').trim() || 'Unidade',
    
    // NOVOS CAMPOS
    data_entrada: formData.data_entrada || null,
    data_fabricacao: formData.data_fabricacao || null,
    data_validade: formData.data_validade || null,
    tipo_embalagem: formData.tipo_embalagem || null,
    grandeza_referencia: formData.grandeza_referencia ? parseFloat(formData.grandeza_referencia) : null,
    densidade: formData.densidade ? parseFloat(formData.densidade) : null,
};
```

#### F. Adicionar Estilos Soft Depth

```javascript
const styles = StyleSheet.create({
    // ... estilos existentes ...
    
    // Estilo Soft Depth
    sectionCard: {
        backgroundColor: '#fff',
        borderRadius: 12,
        padding: 16,
        marginBottom: 16,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.1,
        shadowRadius: 6,
        elevation: 3,
    },
    
    conditionalFields: {
        backgroundColor: '#f9fafb',
        borderWidth: 1.5,
        borderColor: '#e5e7eb',
        borderRadius: 8,
        padding: 16,
        marginTop: 12,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.06,
        shadowRadius: 4,
        elevation: 1,
    },
    
    conversionPreview: {
        backgroundColor: '#dbeafe',
        borderLeftWidth: 4,
        borderLeftColor: '#3b82f6',
        borderRadius: 8,
        padding: 12,
        marginTop: 12,
    },
    
    conversionTitle: {
        fontSize: 12,
        fontWeight: '700',
        color: '#3b82f6',
        marginBottom: 6,
    },
    
    conversionText: {
        fontSize: 14,
        color: '#374151',
        lineHeight: 20,
    },
    
    dateInput: {
        borderWidth: 1,
        borderColor: '#d1d5db',
        borderRadius: 8,
        padding: 12,
        backgroundColor: '#f9fafb',
    },
    
    dateText: {
        fontSize: 16,
        color: '#111827',
    },
    
    validadeInfo: {
        marginTop: 6,
        fontSize: 12,
        fontWeight: '600',
    },
    
    radioGroup: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 12,
    },
    
    radioOption: {
        flexDirection: 'row',
        alignItems: 'center',
        marginRight: 16,
        marginBottom: 8,
    },
    
    radioCircle: {
        width: 20,
        height: 20,
        borderRadius: 10,
        borderWidth: 2,
        borderColor: '#3b82f6',
        marginRight: 6,
        justifyContent: 'center',
        alignItems: 'center',
    },
    
    radioCircleSelected: {
        borderColor: '#3b82f6',
    },
    
    radioCircleInner: {
        width: 10,
        height: 10,
        borderRadius: 5,
        backgroundColor: '#3b82f6',
    },
    
    radioLabel: {
        fontSize: 14,
        fontWeight: '600',
        color: '#374151',
    },
});
```

## 3. Instalar Dependências Necessárias

```bash
cd galint-mobile
npm install @react-native-community/datetimepicker
```

## 4. Atualizar API Backend (se necessário)

Verificar se o endpoint `/api/mobile/estoque` aceita os novos campos:

```python
# galint_flask/views/api_mobile.py - criar_item_estoque()
payload = {
    "codigo": codigo,
    "descricao": descricao,
    "categoria": data.get("categoria", "Material Elétrico"),
    "marca": data.get("marca", "").strip() or None,
    "unidade": (data.get("unidade") or "Unidade").strip() or "Unidade",
    "localizacao": data.get("localizacao", "").strip() or None,
    "nota_fiscal": data.get("nota_fiscal", "").strip() or None,
    
    # ADICIONAR NOVOS CAMPOS
    "data_entrada": data.get("data_entrada"),
    "data_fabricacao": data.get("data_fabricacao"),
    "data_validade": data.get("data_validade"),
    "tipo_embalagem": data.get("tipo_embalagem"),
    "grandeza_referencia": data.get("grandeza_referencia"),
    "densidade": data.get("densidade"),
}
```

## 5. Testar e Validar

### Checklist de Testes

- [ ] Login como administrador e verificar `user.is_admin` no console
- [ ] Tentar cadastrar item e verificar se permissão é concedida
- [ ] Preencher todos os campos de rastreabilidade
- [ ] Testar conversões dinâmicas (Lata, Rolo, Pacote, Caixa)
- [ ] Verificar cálculo de dias de validade
- [ ] Confirmar que backend recebe e salva novos campos
- [ ] Validar que barcode é gerado automaticamente no backend
- [ ] Testar modo offline (cadastro deve ser enfileirado)

## 6. Build do APK

Após todas as correções:

```bash
cd galint-mobile

# Incrementar versão no app.json
# "version": "1.1.0"

# Build com EAS
eas build --platform android --profile preview
```

## 7. Documentação Atualizada

Criar/Atualizar:
- [ ] `API_ENDPOINTS.md` - Adicionar novos campos de rastreabilidade
- [ ] `CHECKLIST_INSTALACAO.txt` - Atualizar versão
- [ ] `CHANGELOG.md` - Documentar mudanças da versão 1.1.0

## 📊 Resumo de Impacto

### Melhorias de UX
- ✅ Layout moderno e profissional (Soft Depth)
- ✅ Feedback visual imediato (conversões, validade)
- ✅ Campos condicionais com destaque dinâmico
- ✅ Mobile-first responsivo

### Funcionalidades Novas
- ✅ Sistema completo de rastreabilidade
- ✅ Geração automática de lote e barcode
- ✅ Conversões de unidades em tempo real
- ✅ Alertas de validade inteligentes

### Correções Críticas
- 🔧 Permissão de admin para cadastro (em análise)
- 🔧 Sincronização de campos web ↔ mobile

---

**Última atualização:** 31/01/2026  
**Autor:** GitHub Copilot (Senior UI/UX Engineer)
