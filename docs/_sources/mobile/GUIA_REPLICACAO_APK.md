# 🔄 Guia Completo de Replicação do APK GALINT Mobile

**Objetivo**: Replicar todas as alterações do APK de atualização em um novo ambiente de desenvolvimento e gerar novo APK via EAS Build.

**Tempo estimado**: 2-3 horas (primeira vez) | 30-45 minutos (replicações futuras)

---

## 📋 Índice

1. [Pré-requisitos](#pré-requisitos)
2. [Configuração do Ambiente](#configuração-do-ambiente)
3. [Setup do Projeto Mobile](#setup-do-projeto-mobile)
4. [Alterações no Backend](#alterações-no-backend)
5. [Alterações no Mobile](#alterações-no-mobile)
6. [Build e Deploy via EAS](#build-e-deploy-via-eas)
7. [Troubleshooting](#troubleshooting)

---

## 🎯 Pré-requisitos

### Sistema Operacional
- ✅ Windows 10/11, macOS ou Linux
- ✅ Mínimo 8GB RAM (16GB recomendado)
- ✅ 5GB espaço livre em disco

### Softwares Necessários

#### 1. Node.js (v18 ou superior)
```powershell
# Verificar versão instalada
node --version

# Se não estiver instalado, baixe em:
# https://nodejs.org/pt-br (versão LTS)
```

**Instalação no Windows**:
1. Baixe o instalador MSI do site oficial
2. Execute o instalador (marque "Add to PATH")
3. Reinicie o terminal
4. Verifique: `node --version` e `npm --version`

#### 2. Git
```powershell
# Verificar instalação
git --version

# Baixar em: https://git-scm.com/download/win
```

#### 3. Python 3.10+ (para backend)
```powershell
# Verificar versão
python --version

# Baixar em: https://www.python.org/downloads/
```

#### 4. PostgreSQL 16+ (banco de dados)
```powershell
# Verificar instalação
psql --version

# Baixar em: https://www.postgresql.org/download/
```

---

## ⚙️ Configuração do Ambiente

### Passo 1: Instalar Expo CLI Globalmente

```powershell
# Instalar Expo CLI
npm install -g expo-cli

# Verificar instalação
expo --version

# Se der erro de permissão no Windows, execute como Administrador
```

### Passo 2: Instalar EAS CLI

```powershell
# Instalar EAS CLI (para build de APK)
npm install -g eas-cli

# Verificar instalação
eas --version
```

### Passo 3: Criar Conta Expo (se não tiver)

```powershell
# Fazer login no EAS
eas login

# Ou criar nova conta em: https://expo.dev/signup
```

**Importante**: Anote suas credenciais!
- Username: _____________
- Email: _____________
- Password: _____________

### Passo 4: Configurar Ambiente Python (Backend)

```powershell
# Navegar para pasta do projeto backend
cd "C:\caminho\para\seu\projeto\backend"

# Criar ambiente virtual
python -m venv .venv

# Ativar ambiente virtual
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# Windows CMD:
.venv\Scripts\activate.bat

# Instalar dependências
pip install -r requirements.txt
```

---

## 📱 Setup do Projeto Mobile

### Passo 1: Estrutura de Diretórios

Certifique-se de ter a seguinte estrutura:

```
seu-projeto/
├── backend/                    # Flask app
│   ├── galint_flask/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── services/
│   │   └── views/
│   ├── .env
│   └── requirements.txt
│
└── galint-mobile/             # React Native app
    ├── src/
    │   ├── screens/
    │   ├── services/
    │   └── navigation/
    ├── app.json
    ├── package.json
    └── eas.json
```

### Passo 2: Inicializar Projeto Mobile (se não existir)

Se você está começando do zero:

```powershell
# Criar novo projeto Expo
npx create-expo-app galint-mobile

# Navegar para pasta do projeto
cd galint-mobile

# Instalar dependências necessárias
npm install @react-navigation/native @react-navigation/stack
npm install react-native-screens react-native-safe-area-context
npm install expo-barcode-scanner
npm install axios
```

### Passo 3: Copiar Projeto Existente

Se você já tem o código-fonte:

```powershell
# Navegar para pasta mobile
cd galint-mobile

# Instalar dependências
npm install

# Verificar se tudo está ok
npm run doctor  # Expo diagnostics
```

---

## 🔧 Alterações no Backend

### 1. Criar Endpoint de Retirada Mobile

**Arquivo**: `galint_flask/views/mobile.py`

Adicione ou edite:

```python
@bp.route('/retirar', methods=['POST'])
@token_required
def retirar_mobile(current_user):
    """Registra retirada de material pelo app mobile."""
    try:
        data = request.get_json()
        codigo = data.get('codigo')
        quantidade = data.get('quantidade')
        observacao = data.get('observacao', '')
        local_servico = data.get('local_servico', '')

        # Validações
        if not codigo:
            return jsonify({'success': False, 'message': 'Código do item é obrigatório'}), 400

        try:
            quantidade = int(quantidade)
            if quantidade <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Quantidade inválida'}), 400

        # Buscar item
        item = Item.query.filter(
            (Item.codigo_item == codigo) | 
            (Item.codigo_barras == codigo)
        ).first()

        if not item:
            return jsonify({'success': False, 'message': 'Item não encontrado'}), 404

        # Verificar saldo
        try:
            saldo_atual = item.get_saldo_atual()
        except Exception:
            saldo_atual = item.quantidade if hasattr(item, 'quantidade') else 0

        if saldo_atual < quantidade:
            return jsonify({
                'success': False, 
                'message': f'Saldo insuficiente. Disponível: {saldo_atual}'
            }), 400

        # Registrar saída
        saida = Saida()
        saida.codigo_item = item.codigo_item
        saida.quantidade = quantidade
        saida.matricula = current_user.matricula
        saida.data_saida = datetime.now()
        saida.observacao = observacao.upper()
        saida.local_servico = local_servico.upper()

        db.session.add(saida)

        # Atualizar saldo do item
        if hasattr(item, 'quantidade'):
            item.quantidade -= quantidade

        db.session.commit()

        # Buscar saldo atualizado
        try:
            novo_saldo = item.get_saldo_atual()
        except Exception:
            novo_saldo = item.quantidade if hasattr(item, 'quantidade') else None

        # Notificar via Telegram (opcional)
        try:
            from ..services.telegram_service import TelegramService
            TelegramService.notify_withdrawal(
                user=current_user,
                item=item,
                quantidade=quantidade,
                saida_id=saida.id_saida
            )
        except Exception as e:
            logger.warning(f"Falha ao enviar notificação Telegram: {e}")

        return jsonify({
            'success': True,
            'message': 'Retirada registrada com sucesso',
            'data': {
                'saida_id': saida.id_saida,
                'item': {
                    'codigo': item.codigo_item,
                    'descricao': item.descricao,
                    'saldo': novo_saldo
                }
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.exception("Erro ao registrar retirada mobile")
        return jsonify({
            'success': False, 
            'message': f'Erro ao processar retirada: {str(e)}'
        }), 500
```

### 2. Melhorar Endpoint de Login

**Arquivo**: `galint_flask/views/mobile.py`

Edite a função `login_mobile`:

```python
@bp.route('/login', methods=['POST'])
def login_mobile():
    """Autentica usuário por matrícula OU nome."""
    try:
        data = request.get_json()
        matricula_ou_nome = str(data.get('matricula', '')).strip()
        senha = data.get('senha', '')

        if not matricula_ou_nome or not senha:
            return jsonify({
                'success': False, 
                'message': 'Matrícula/Nome e senha são obrigatórios'
            }), 400

        # Tentar buscar por matrícula (numérico)
        if matricula_ou_nome.isdigit():
            user = Usuario.query.filter_by(matricula=matricula_ou_nome).first()
        else:
            # Buscar por nome (case-insensitive, fuzzy match)
            users = Usuario.query.filter(
                Usuario.nome.ilike(f'%{matricula_ou_nome}%')
            ).all()

            if len(users) == 0:
                user = None
            elif len(users) == 1:
                user = users[0]
            else:
                # Múltiplos resultados: retornar para desambiguação
                return jsonify({
                    'success': False,
                    'ambiguous': True,
                    'message': 'Múltiplos usuários encontrados. Seja mais específico ou use a matrícula.',
                    'matches': [
                        {'matricula': u.matricula, 'nome': u.nome}
                        for u in users[:10]  # Limitar a 10 resultados
                    ]
                }), 400

        if not user:
            return jsonify({
                'success': False, 
                'message': 'Usuário não encontrado'
            }), 404

        # Verificar senha
        if not user.check_password(senha):
            return jsonify({
                'success': False, 
                'message': 'Senha incorreta'
            }), 401

        # Gerar token JWT
        token = jwt.encode(
            {
                'matricula': user.matricula,
                'exp': datetime.utcnow() + timedelta(days=30)
            },
            current_app.config['SECRET_KEY'],
            algorithm='HS256'
        )

        return jsonify({
            'success': True,
            'message': 'Login realizado com sucesso',
            'data': {
                'token': token,
                'user': {
                    'matricula': user.matricula,
                    'nome': user.nome,
                    'setor': user.setor,
                    'is_admin': getattr(user, 'is_admin', 0) == 1
                }
            }
        }), 200

    except Exception as e:
        logger.exception("Erro no login mobile")
        return jsonify({
            'success': False, 
            'message': f'Erro no servidor: {str(e)}'
        }), 500
```

### 3. Atualizar Imports e Registrar Blueprint

**Arquivo**: `galint_flask/__init__.py`

Certifique-se de que o blueprint mobile está registrado:

```python
# Importar blueprint
from .views import mobile

# Registrar blueprint
app.register_blueprint(mobile.bp)
```

### 4. Testar Backend

```powershell
# Ativar ambiente virtual
.\.venv\Scripts\Activate.ps1

# Rodar servidor de desenvolvimento
python -m flask run --host=0.0.0.0 --port=5000

# Ou usar Waitress (produção)
waitress-serve --host=0.0.0.0 --port=5000 --call galint_flask:create_app
```

**Testar endpoint de retirada**:

```powershell
# POST /api/mobile/retirar
$headers = @{
    "Authorization" = "Bearer SEU_TOKEN_AQUI"
    "Content-Type" = "application/json"
}

$body = @{
    codigo = "ABC123"
    quantidade = 5
    observacao = "TESTE DE RETIRADA"
    local_servico = "ALMOXARIFADO"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:5000/api/mobile/retirar" -Method POST -Headers $headers -Body $body
```

---

## 📱 Alterações no Mobile

### 1. Criar RetiradaScreen

**Arquivo**: `galint-mobile/src/screens/RetiradaScreen.js`

Crie o arquivo completo:

```javascript
import React, { useMemo, useState } from 'react';
import {
    View,
    Text,
    TextInput,
    TouchableOpacity,
    StyleSheet,
    Alert,
    ScrollView,
    KeyboardAvoidingView,
    Platform,
    ActivityIndicator,
} from 'react-native';
import ApiService from '../services/api';

function sanitizeIntText(text) {
    if (text == null) return '';
    return String(text).replace(/[^0-9]/g, '');
}

export default function RetiradaScreen({ navigation, route }) {
    const user = route.params?.user;
    const item = route.params?.item;

    const [quantidade, setQuantidade] = useState('');
    const [observacao, setObservacao] = useState('');
    const [localServico, setLocalServico] = useState('');
    const [loading, setLoading] = useState(false);

    const saldoAtual = useMemo(() => {
        const q = Number(item?.quantidade ?? 0);
        return Number.isFinite(q) ? q : 0;
    }, [item]);

    const handleSubmit = async () => {
        const quantidadeInt = parseInt(sanitizeIntText(quantidade), 10);
        if (Number.isNaN(quantidadeInt) || quantidadeInt <= 0) {
            Alert.alert('Erro', 'Informe uma quantidade válida (inteiro > 0).');
            return;
        }

        if (!item?.id && !item?.codigo_barras) {
            Alert.alert('Erro', 'Item inválido. Volte e selecione novamente.');
            return;
        }

        setLoading(true);
        try {
            const codigo = String(item.id || item.codigo_barras).trim();
            const result = await ApiService.registrarRetirada({
                codigo,
                quantidade: quantidadeInt,
                observacao: String(observacao || '').toUpperCase(),
                local_servico: String(localServico || '').toUpperCase(),
            });

            if (!result.success) {
                Alert.alert('Erro', result.message);
                return;
            }

            const saidaId = result.data?.saida_id;
            const novoSaldo = result.data?.item?.saldo ?? result.data?.item?.quantidade;

            Alert.alert(
                'Sucesso',
                `Retirada registrada${saidaId ? ` (ID ${saidaId})` : ''}.\nNovo saldo: ${novoSaldo ?? 'OK'}`,
                [
                    {
                        text: 'Nova Retirada',
                        onPress: () => {
                            setQuantidade('');
                            setObservacao('');
                            setLocalServico('');
                        }
                    },
                    { text: 'Voltar', onPress: () => navigation.goBack() }
                ]
            );
        } catch (e) {
            Alert.alert('Erro', 'Falha ao registrar retirada');
        } finally {
            setLoading(false);
        }
    };

    return (
        <KeyboardAvoidingView 
            style={styles.container} 
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        >
            <ScrollView 
                contentContainerStyle={styles.scroll} 
                keyboardShouldPersistTaps="handled"
            >
                <View style={styles.card}>
                    <Text style={styles.title}>Retirada de Material</Text>

                    <View style={styles.itemBox}>
                        <Text style={styles.itemName}>
                            {(item?.descricao || item?.nome || '').toString().toUpperCase()}
                        </Text>
                        <Text style={styles.itemLine}>
                            Código: {(item?.codigo_barras || item?.id || '').toString()}
                        </Text>
                        <Text style={styles.itemLine}>Saldo atual: {saldoAtual}</Text>
                    </View>

                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Quantidade *</Text>
                        <TextInput
                            style={styles.input}
                            value={quantidade}
                            onChangeText={(text) => setQuantidade(sanitizeIntText(text))}
                            placeholder="Quantidade"
                            keyboardType="numeric"
                        />
                    </View>

                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Local de Serviço</Text>
                        <TextInput
                            style={styles.input}
                            value={localServico}
                            onChangeText={(text) => setLocalServico(String(text || '').toUpperCase())}
                            placeholder="EX: BLOCO A - APTO 201"
                            autoCapitalize="characters"
                        />
                    </View>

                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Observação</Text>
                        <TextInput
                            style={[styles.input, styles.textArea]}
                            value={observacao}
                            onChangeText={(text) => setObservacao(String(text || '').toUpperCase())}
                            placeholder="OBSERVAÇÕES ADICIONAIS"
                            multiline
                            numberOfLines={3}
                            autoCapitalize="characters"
                        />
                    </View>

                    <TouchableOpacity 
                        style={[styles.button, loading && styles.buttonDisabled]}
                        onPress={handleSubmit}
                        disabled={loading}
                    >
                        {loading ? (
                            <ActivityIndicator color="#fff" />
                        ) : (
                            <Text style={styles.buttonText}>Registrar Retirada</Text>
                        )}
                    </TouchableOpacity>
                </View>
            </ScrollView>
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#f5f5f5',
    },
    scroll: {
        padding: 16,
    },
    card: {
        backgroundColor: '#fff',
        padding: 20,
        borderRadius: 12,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.1,
        shadowRadius: 4,
        elevation: 3,
    },
    title: {
        fontSize: 24,
        fontWeight: 'bold',
        color: '#333',
        marginBottom: 20,
        textAlign: 'center',
    },
    itemBox: {
        backgroundColor: '#f8f8f8',
        padding: 15,
        borderRadius: 8,
        marginBottom: 20,
        borderLeftWidth: 4,
        borderLeftColor: '#007bff',
    },
    itemName: {
        fontSize: 18,
        fontWeight: 'bold',
        color: '#333',
        marginBottom: 8,
    },
    itemLine: {
        fontSize: 14,
        color: '#666',
        marginTop: 4,
    },
    inputGroup: {
        marginBottom: 16,
    },
    label: {
        fontSize: 14,
        fontWeight: '600',
        color: '#333',
        marginBottom: 8,
    },
    input: {
        backgroundColor: '#fff',
        borderWidth: 1,
        borderColor: '#ddd',
        borderRadius: 8,
        padding: 12,
        fontSize: 16,
    },
    textArea: {
        height: 80,
        textAlignVertical: 'top',
    },
    button: {
        backgroundColor: '#007bff',
        paddingVertical: 14,
        borderRadius: 8,
        alignItems: 'center',
        marginTop: 10,
    },
    buttonDisabled: {
        backgroundColor: '#ccc',
    },
    buttonText: {
        color: '#fff',
        fontSize: 16,
        fontWeight: 'bold',
    },
});
```

### 2. Atualizar ScannerScreen

**Arquivo**: `galint-mobile/src/screens/ScannerScreen.js`

Adicione suporte ao modo `withdraw`:

```javascript
// No início do componente, extrair mode dos params
export default function ScannerScreen({ navigation, route }) {
    const mode = route.params?.mode || 'lookup';  // 'lookup' ou 'withdraw'
    const user = route.params?.user;
    
    // ... resto do código

    const handleBarCodeScanned = async ({ type, data }) => {
        setScanned(true);
        
        try {
            // Se modo retirada, navegar direto para RetiradaScreen
            if (mode === 'withdraw') {
                // Buscar dados do item primeiro
                const item = await ApiService.buscarItemPorCodigo(data);
                
                if (!item) {
                    Alert.alert('Erro', 'Item não encontrado');
                    setScanned(false);
                    return;
                }
                
                navigation.navigate('Retirada', { item, user });
                return;
            }
            
            // Modo lookup: comportamento padrão
            navigation.navigate('Detalhes', { itemId: data });
            
        } catch (e) {
            Alert.alert('Erro', 'Falha ao processar código');
            setScanned(false);
        }
    };

    // ... resto do código
}
```

### 3. Adicionar Botão Retirar no EstoqueScreen

**Arquivo**: `galint-mobile/src/screens/EstoqueScreen.js`

Adicione botão antes ou depois da lista:

```javascript
export default function EstoqueScreen({ navigation, route }) {
    const user = route.params?.user;
    
    // ... resto do código de busca e filtros
    
    return (
        <View style={styles.container}>
            {/* Barra de busca existente */}
            <View style={styles.searchContainer}>
                {/* ... */}
            </View>
            
            {/* NOVO: Botão Retirar */}
            <TouchableOpacity
                style={styles.withdrawButton}
                onPress={() => navigation.navigate('Scanner', { mode: 'withdraw', user })}
            >
                <Text style={styles.withdrawButtonText}>📤 Retirar Material</Text>
            </TouchableOpacity>
            
            {/* Lista de itens existente */}
            <FlatList
                data={filteredItems}
                // ... resto da FlatList
            />
        </View>
    );
}

// Adicionar aos estilos
const styles = StyleSheet.create({
    // ... estilos existentes
    
    withdrawButton: {
        backgroundColor: '#FF6B35',
        paddingVertical: 12,
        paddingHorizontal: 20,
        borderRadius: 8,
        marginHorizontal: 16,
        marginBottom: 10,
        alignItems: 'center',
        flexDirection: 'row',
        justifyContent: 'center',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.2,
        shadowRadius: 3,
        elevation: 3,
    },
    withdrawButtonText: {
        color: '#fff',
        fontSize: 16,
        fontWeight: 'bold',
    },
});
```

### 4. Atualizar CadastroScreen

**Arquivo**: `galint-mobile/src/screens/CadastroScreen.js`

Faça as seguintes alterações:

```javascript
// No topo do arquivo, adicionar helpers
function toUpper(text) {
    return String(text || '').toUpperCase();
}

function sanitizeIntText(text) {
    if (text == null) return '';
    return String(text).replace(/[^0-9]/g, '');
}

export default function CadastroScreen({ navigation, route }) {
    const user = route.params?.user;
    
    // Definir teclado numérico adaptativo
    const numericKeyboardType = Platform.OS === 'ios' ? 'number-pad' : 'numeric';
    
    // Estado inicial com quantidade VAZIA (não '0')
    const [formData, setFormData] = useState({
        codigo_barras: '',
        descricao: '',
        categoria: '',
        localizacao: '',
        marca: '',
        quantidade: '',  // ← MUDANÇA: era '0', agora ''
        estoque_minimo: '',
        numero_nota_fiscal: '',
        // ... outros campos
    });
    
    // ... resto do código
    
    return (
        <ScrollView style={styles.container}>
            {/* Campo Descrição */}
            <View style={styles.inputGroup}>
                <Text style={styles.label}>Descrição *</Text>
                <TextInput
                    style={styles.input}
                    value={formData.descricao}
                    onChangeText={(text) => 
                        setFormData(p => ({ ...p, descricao: toUpper(text) }))
                    }
                    placeholder="DESCRIÇÃO DO ITEM"
                    autoCapitalize="characters"
                />
            </View>
            
            {/* Campo Categoria */}
            <View style={styles.inputGroup}>
                <Text style={styles.label}>Categoria</Text>
                <TextInput
                    style={styles.input}
                    value={formData.categoria}
                    onChangeText={(text) => 
                        setFormData(p => ({ ...p, categoria: toUpper(text) }))
                    }
                    placeholder="CATEGORIA"
                    autoCapitalize="characters"
                />
            </View>
            
            {/* Campo Quantidade */}
            <View style={styles.inputGroup}>
                <Text style={styles.label}>Quantidade *</Text>
                <TextInput
                    style={styles.input}
                    value={formData.quantidade}
                    onChangeText={(text) => 
                        setFormData(p => ({ ...p, quantidade: sanitizeIntText(text) }))
                    }
                    placeholder="Quantidade"
                    keyboardType={numericKeyboardType}  // ← MUDANÇA: usar teclado numérico
                />
            </View>
            
            {/* Campo NF */}
            <View style={styles.inputGroup}>
                <Text style={styles.label}>Número da Nota Fiscal</Text>
                <TextInput
                    style={styles.input}
                    value={formData.numero_nota_fiscal}
                    onChangeText={(text) => 
                        setFormData(p => ({ ...p, numero_nota_fiscal: sanitizeIntText(text) }))
                    }
                    placeholder="NF"
                    keyboardType={numericKeyboardType}  // ← MUDANÇA: usar teclado numérico
                />
            </View>
            
            {/* Aplicar mesma lógica para outros campos... */}
        </ScrollView>
    );
}
```

### 5. Atualizar EditarItemScreen

**Arquivo**: `galint-mobile/src/screens/EditarItemScreen.js`

Mesmas alterações do CadastroScreen:
- Uppercase em textos
- Teclado numérico em campos numéricos
- Campos vazios (não "0")

### 6. Atualizar ApiService

**Arquivo**: `galint-mobile/src/services/api.js`

Adicione método `registrarRetirada`:

```javascript
class ApiService {
    // ... métodos existentes (login, buscarItens, etc.)
    
    async registrarRetirada(data) {
        try {
            const token = await AsyncStorage.getItem('authToken');
            if (!token) {
                throw new Error('Token não encontrado. Faça login novamente.');
            }
            
            const response = await axios.post(
                `${this.baseURL}/retirar`,
                data,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json',
                    },
                }
            );
            
            return response.data;
        } catch (error) {
            console.error('Erro ao registrar retirada:', error);
            
            if (error.response?.status === 401) {
                throw new Error('Sessão expirada. Faça login novamente.');
            }
            
            return {
                success: false,
                message: error.response?.data?.message || 'Erro ao registrar retirada',
            };
        }
    }
    
    async buscarItemPorCodigo(codigo) {
        try {
            const token = await AsyncStorage.getItem('authToken');
            if (!token) {
                throw new Error('Token não encontrado');
            }
            
            const response = await axios.get(
                `${this.baseURL}/itens/${codigo}`,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                    },
                }
            );
            
            return response.data.data;
        } catch (error) {
            console.error('Erro ao buscar item:', error);
            return null;
        }
    }
}

export default new ApiService();
```

### 7. Registrar Rotas no Navigator

**Arquivo**: `galint-mobile/App.js` (ou onde estão as rotas)

Adicione rota para RetiradaScreen:

```javascript
import RetiradaScreen from './src/screens/RetiradaScreen';

// Dentro do Stack.Navigator
<Stack.Navigator>
    <Stack.Screen name="Login" component={LoginScreen} />
    <Stack.Screen name="Home" component={HomeScreen} />
    <Stack.Screen name="Estoque" component={EstoqueScreen} />
    <Stack.Screen name="Scanner" component={ScannerScreen} />
    <Stack.Screen name="Cadastro" component={CadastroScreen} />
    <Stack.Screen name="Editar" component={EditarItemScreen} />
    
    {/* NOVA ROTA */}
    <Stack.Screen 
        name="Retirada" 
        component={RetiradaScreen}
        options={{ title: 'Retirar Material' }}
    />
</Stack.Navigator>
```

---

## 🏗️ Build e Deploy via EAS

### Passo 1: Configurar EAS

**Arquivo**: `galint-mobile/eas.json`

Crie ou edite o arquivo:

```json
{
  "cli": {
    "version": ">= 5.9.0"
  },
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal"
    },
    "preview": {
      "android": {
        "buildType": "apk"
      },
      "distribution": "internal"
    },
    "production": {
      "android": {
        "buildType": "app-bundle"
      }
    }
  },
  "submit": {
    "production": {}
  }
}
```

### Passo 2: Configurar app.json

**Arquivo**: `galint-mobile/app.json`

Verifique/atualize:

```json
{
  "expo": {
    "name": "GALINT Mobile",
    "slug": "galint-mobile",
    "version": "1.1.0",
    "orientation": "portrait",
    "icon": "./assets/icon.png",
    "userInterfaceStyle": "light",
    "splash": {
      "image": "./assets/splash.png",
      "resizeMode": "contain",
      "backgroundColor": "#ffffff"
    },
    "android": {
      "package": "com.seudominio.galint",
      "versionCode": 2,
      "permissions": [
        "CAMERA",
        "READ_EXTERNAL_STORAGE",
        "WRITE_EXTERNAL_STORAGE"
      ],
      "adaptiveIcon": {
        "foregroundImage": "./assets/adaptive-icon.png",
        "backgroundColor": "#ffffff"
      }
    },
    "plugins": [
      [
        "expo-barcode-scanner",
        {
          "cameraPermission": "Permitir $(PRODUCT_NAME) acessar sua câmera para escanear códigos de barras."
        }
      ]
    ]
  }
}
```

**Importante**: Incremente `versionCode` a cada build!

### Passo 3: Fazer Login no EAS

```powershell
cd galint-mobile

# Login (se não estiver logado)
eas login

# Verificar conta
eas whoami
```

### Passo 4: Configurar Projeto no EAS

```powershell
# Primeira vez: configurar projeto
eas build:configure

# Responda às perguntas:
# - Create a new project? Yes
# - Project name: galint-mobile
# - Android package: com.seudominio.galint
```

### Passo 5: Fazer Build do APK

```powershell
# Build do APK (modo preview)
eas build --platform android --profile preview

# Aguarde (pode levar 10-30 minutos)
# Você receberá um link para download quando concluir
```

**Monitorar Build**:
```powershell
# Ver progresso em tempo real
eas build:list

# Ou acesse: https://expo.dev/accounts/[seu-username]/projects/galint-mobile/builds
```

### Passo 6: Download e Instalação

Quando o build terminar:

1. Você receberá um link por email e no terminal
2. Link será algo como: `https://expo.dev/artifacts/eas/[id].apk`
3. Baixe o APK
4. Transfira para dispositivo Android
5. Instale (pode precisar habilitar "Fontes desconhecidas")

**Ou use QR Code**:
```powershell
# Gerar QR code para download
eas build:list

# Escanear QR code no celular para baixar direto
```

---

## 🐛 Troubleshooting

### Problema 1: `eas: command not found`

**Solução**:
```powershell
# Reinstalar EAS CLI globalmente
npm uninstall -g eas-cli
npm install -g eas-cli

# Verificar instalação
eas --version

# Se ainda não funcionar, adicionar npm global ao PATH
npm config get prefix
# Adicionar [resultado]\node_modules\.bin ao PATH
```

### Problema 2: Build falha com erro de dependências

**Solução**:
```powershell
cd galint-mobile

# Limpar node_modules
rm -rf node_modules
rm package-lock.json

# Reinstalar
npm install

# Tentar build novamente
eas build --platform android --profile preview --clear-cache
```

### Problema 3: "Invalid credentials"

**Solução**:
```powershell
# Fazer logout e login novamente
eas logout
eas login

# Verificar credenciais
eas whoami
```

### Problema 4: APK não instala no celular

**Soluções**:
1. Habilitar "Fontes desconhecidas" nas configurações do Android
2. Verificar se há espaço suficiente
3. Desinstalar versão antiga antes de instalar nova
4. Verificar se `versionCode` foi incrementado no `app.json`

### Problema 5: Backend retorna erro 401 (Unauthorized)

**Solução**:
```javascript
// Verificar se token está sendo enviado corretamente
// Em ApiService.js:
console.log('Token:', token);
console.log('Headers:', headers);

// No backend, adicionar log:
@token_required
def retirar_mobile(current_user):
    print(f"User autenticado: {current_user.matricula}")
    # ... resto do código
```

### Problema 6: Scanner não funciona

**Solução**:
```javascript
// Verificar permissões em app.json
"android": {
  "permissions": [
    "CAMERA"
  ]
}

// Solicitar permissão explicitamente
import { Camera } from 'expo-camera';

const [hasPermission, setHasPermission] = useState(null);

useEffect(() => {
  (async () => {
    const { status } = await Camera.requestCameraPermissionsAsync();
    setHasPermission(status === 'granted');
  })();
}, []);
```

### Problema 7: Uppercase não funciona

**Solução**:
```javascript
// Verificar se está usando .toUpperCase() corretamente
onChangeText={(text) => setLocalServico(String(text || '').toUpperCase())}

// E também no submit:
observacao: String(observacao || '').toUpperCase()
```

### Problema 8: Build demora muito

**Normal!** Build via EAS pode levar:
- 10-15 minutos em horários normais
- 20-30 minutos em horários de pico
- Primeira build: pode levar até 45 minutos

**Dicas para acelerar**:
```powershell
# Usar cache (padrão)
eas build --platform android --profile preview

# Não limpar cache (mais rápido em rebuilds)
# Mas se houver problemas, limpe:
eas build --platform android --profile preview --clear-cache
```

---

## ✅ Checklist Final

Antes de fazer o build, verifique:

### Backend
- [ ] Endpoint `/api/mobile/retirar` criado e testado
- [ ] Endpoint `/api/mobile/login` aceita nome e matrícula
- [ ] Servidor rodando e acessível
- [ ] Token JWT configurado corretamente
- [ ] Banco de dados com tabela `saidas` atualizada

### Mobile
- [ ] RetiradaScreen.js criado
- [ ] ScannerScreen.js com modo `withdraw`
- [ ] EstoqueScreen.js com botão "Retirar"
- [ ] CadastroScreen.js com uppercase e teclado numérico
- [ ] EditarItemScreen.js com mesmas melhorias
- [ ] ApiService.js com método `registrarRetirada`
- [ ] Rotas registradas no navigator
- [ ] `app.json` com `versionCode` incrementado
- [ ] `eas.json` configurado corretamente

### EAS
- [ ] Conta Expo criada e login feito
- [ ] EAS CLI instalado (`eas --version` funciona)
- [ ] Projeto configurado (`eas build:configure`)
- [ ] Build iniciado sem erros

### Testes
- [ ] Login funciona (matrícula e nome)
- [ ] Scanner abre câmera
- [ ] Retirada registra no banco
- [ ] Uppercase funciona em todos os campos
- [ ] Teclado numérico aparece em campos de número
- [ ] Campos numéricos iniciam vazios

---

## 📚 Comandos de Referência Rápida

```powershell
# === BACKEND ===
# Ativar venv
.\.venv\Scripts\Activate.ps1

# Rodar servidor
python -m flask run --host=0.0.0.0 --port=5000

# Ou com Waitress
waitress-serve --host=0.0.0.0 --port=5000 --call galint_flask:create_app


# === MOBILE ===
# Navegar para pasta mobile
cd galint-mobile

# Instalar dependências
npm install

# Rodar em desenvolvimento (Expo Go)
npx expo start

# Login no EAS
eas login

# Verificar conta
eas whoami

# Configurar projeto
eas build:configure

# Build APK
eas build --platform android --profile preview

# Build AAB (Google Play)
eas build --platform android --profile production

# Ver lista de builds
eas build:list

# Cancelar build em andamento
eas build:cancel


# === TROUBLESHOOTING ===
# Limpar cache
npm cache clean --force
rm -rf node_modules package-lock.json
npm install

# Limpar cache do Expo
npx expo start -c

# Rebuild com cache limpo
eas build --platform android --profile preview --clear-cache


# === GIT (VERSIONAMENTO) ===
# Commit antes de build
git add .
git commit -m "feat: adicionar funcionalidade de retirada mobile"
git push origin main

# Tag de versão
git tag -a v1.1.0 -m "Versão 1.1.0 - Retirada mobile"
git push origin v1.1.0
```

---

## 📖 Documentação Adicional

- **Expo EAS Build**: https://docs.expo.dev/build/introduction/
- **Expo Go**: https://docs.expo.dev/get-started/expo-go/
- **React Navigation**: https://reactnavigation.org/docs/getting-started
- **Expo Barcode Scanner**: https://docs.expo.dev/versions/latest/sdk/bar-code-scanner/
- **APK vs AAB**: https://docs.expo.dev/build-reference/apk/

---

## 🎓 Próximos Passos

Após replicar com sucesso:

1. **Testar extensivamente** em diferentes dispositivos
2. **Coletar feedback** dos usuários
3. **Implementar melhorias** do roadmap
4. **Configurar CI/CD** para builds automáticos
5. **Publicar na Google Play Store** (opcional)

---

## 📞 Suporte

Se encontrar problemas não listados neste guia:

1. Consulte logs do EAS: `eas build:list` → clicar no build → ver logs
2. Consulte logs do Expo: `npx expo start` → ver console
3. Consulte logs do backend: verificar arquivo `log/` ou console do Flask

---

**Versão do Guia**: 1.0  
**Data**: 12 de janeiro de 2026  
**Testado em**: Windows 11, Node.js v20, Expo SDK 51, EAS CLI 5.9+  
**Tempo estimado**: 2-3 horas (primeira vez) | 30-45 minutos (replicações futuras)

✅ **Guia completo e pronto para uso!**
