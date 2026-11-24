// Lançar entrada com NF de um item que já existe (2.2.3). Pedido do usuário em 21/11/2026: no ☰ do
// item lido na Conferência, um lançamento prático: quantidade, chave de acesso LIDA pela câmera (não
// há campo para digitar a chave nem o número da NF: o número, a série e o CNPJ saem da própria
// chave, como em Documentos Fiscais do site), datas e valor. Grava pela mesma rota da tela de
// Documentos Fiscais (/api/mobile/documentos-fiscais), com financeiro, estoque e aviso.
//
// Cadastro pelo código lido (2.2.6). Pedido do usuário em 23/11/2026: quando o código lido não existe,
// o app pergunta se quer cadastrar e abre ESTA tela (route.params.codigoNovo), com o mesmo formulário
// e a mesma gravação; só entram descrição, categoria e unidade do item novo. A rota cria o item em
// pré-cadastro, como faz o site com item novo vindo de NF: o saldo entra quando o pré-cadastro é
// concluído no site.
//
// Marca (2.2.7). O usuário achou em 24/11/2026: "no cadastro não tem a opção marca". Entra entre
// Categoria e Unidade, opcional como no "Lançar entrada com NF" do site (nova_marca na mesma rota).
//
// Nome padrão (2.3.0, 24/11/2026): na descrição do item novo, enquanto se digita, aparecem até 6 nomes —
// primeiro os de grupo (produto genérico), depois os já cadastrados; tocar põe o nome (e a unidade do
// grupo). Pedido do usuário: "quero que o grupo seja o nome padrão para cadastro".
//
// Última NF no cartão (2.2.9, 24/11/2026): número em vermelho e data à direita do saldo, pedido do
// usuário com desenho; "já lançado nesta NF" quando a última NF do item é a mesma lida na tela.
//
// Prova real (2.2.8, 24/11/2026). Na NF 617377, 4 rolos de fita viraram 40 rolos: para item com
// embalagem, o servidor lê a quantidade em embalagens, e esta tela mostrava "Quantidade (metro)". Agora
// o rótulo diz a unidade que o servidor usa ("Quantidade (rolos)"), a conta aparece enquanto se digita
// ("4 rolos × 10 = 40 metros no estoque · 4 × R$ 59,90 = R$ 239,60") e, ao lançar, o app pergunta se o
// cálculo é este mesmo (pedido do usuário). Conta em utils/provaReal.js, igual à do site.
import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    FlatList,
    Image,
    Keyboard,
    KeyboardAvoidingView,
    Modal,
    Platform,
    ScrollView,
    StyleSheet,
    Text,
    TouchableOpacity,
    Vibration,
    View,
} from 'react-native';
import TextInput from '../components/UpperTextInput';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { DateTimePickerAndroid } from '@react-native-community/datetimepicker';

import ApiService from '../services/api';
import InactivityService from '../services/inactivityService';
import DoneModal from '../components/DoneModal';
import ItemPhotoLinkModal from '../components/ItemPhotoLinkModal';
import { resolvePhotoUri } from '../components/StockCountPanel';
import { heroPalette, heroSoftShadow } from '../theme/heroTheme';
import { computeProof, factorFromItem, unitLabel } from '../utils/provaReal';

function isoDate(date) {
    const pad = (value) => String(value).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function brDate(iso) {
    if (!iso) return '';
    const [year, month, day] = iso.split('-');
    return `${day}/${month}/${year}`;
}

function parseIso(iso) {
    if (!iso) return new Date();
    const [year, month, day] = iso.split('-').map(Number);
    return new Date(year, month - 1, day);
}

function documentLabel(entry) {
    const numero = String(entry?.numero || '').trim();
    const tipo = String(entry?.tipo_documento || '').toLowerCase();
    if (tipo === 'nf') return `NF ${numero}`;
    if (tipo === 'cupom') return `Cupom ${numero}`;
    return numero;
}

function sameDocumentNumber(a, b) {
    const clean = (value) => String(value || '').replace(/\D/g, '').replace(/^0+/, '');
    return Boolean(clean(a)) && clean(a) === clean(b);
}

function groupKey(key) {
    return String(key || '').replace(/(\d{4})(?=\d)/g, '$1 ');
}

function normalizeDecimal(text) {
    return String(text || '').replace(/[^0-9.,]/g, '').replace(',', '.');
}

// As mesmas unidades internas do site (inventory.BASE_ITEM_UNIT_OPTIONS), se a configuração não vier.
const UNIDADES = ['Unidade', 'Par', 'Metro', 'Quilo', 'Litro'];

export default function EntradaNFScreen({ navigation, route }) {
    const [fotoNova, setFotoNova] = useState(null);
    const [photoModal, setPhotoModal] = useState(false);
    const codigoNovo = String(route.params?.codigoNovo || '').trim();
    const [criado, setCriado] = useState(null); // item que esta tela acabou de cadastrar
    const novo = Boolean(codigoNovo) && !criado;
    const baseItem = criado || route.params?.item || (codigoNovo ? { codigo: codigoNovo } : {});
    const item = fotoNova ? { ...baseItem, foto_url: fotoNova } : baseItem;
    const codigo = String(item.codigo || item.codigo_barras || item.id || '').trim();
    const [descricao, setDescricao] = useState('');
    // Nome padrão (2.3.0): sugestões enquanto se digita a descrição; grupos primeiro.
    const [sugestoesNome, setSugestoesNome] = useState([]);
    const nomeEscolhido = useRef('');
    const [categoria, setCategoria] = useState('');
    const [marca, setMarca] = useState('');
    const [unidade, setUnidade] = useState('Unidade');
    const [opcoes, setOpcoes] = useState({ categorias: [], unidades: UNIDADES });
    const [escolhendoCategoria, setEscolhendoCategoria] = useState(false);
    const [permission, requestPermission] = useCameraPermissions();
    const [quantidade, setQuantidade] = useState('');
    const [valor, setValor] = useState('');
    const [emissao, setEmissao] = useState('');
    const [recebimento, setRecebimento] = useState(isoDate(new Date()));
    const [nota, setNota] = useState(null); // { chave, numero, serie, modelo, cnpj, fornecedor, fornecedorId }
    const [lendo, setLendo] = useState(false);
    const [consultando, setConsultando] = useState(false);
    const [erro, setErro] = useState('');
    const [salvando, setSalvando] = useState(false);
    const [done, setDone] = useState(null);
    const [photoFailed, setPhotoFailed] = useState(false);
    // Última NF do item (2.2.9): número e data no cartão; "já lançado nesta NF" quando é a mesma da tela.
    const [ultimaEntrada, setUltimaEntrada] = useState(null);
    const lido = useRef(false);

    useLayoutEffect(() => {
        navigation.setOptions({ title: novo ? 'Cadastrar item' : 'Lançar entrada' });
    }, [navigation, novo]);

    useEffect(() => {
        if (codigoNovo || !codigo) return undefined;
        let ativo = true;
        ApiService.getUltimaEntrada(codigo).then((ultima) => {
            if (ativo) setUltimaEntrada(ultima);
        });
        return () => {
            ativo = false;
        };
    }, [codigo, codigoNovo]);

    // Nome padrão: busca as sugestões 250 ms depois de parar de digitar (não depois de escolher uma).
    useEffect(() => {
        if (!codigoNovo) return undefined;
        const termo = descricao.trim();
        if (termo.length < 2 || termo === nomeEscolhido.current) {
            setSugestoesNome([]);
            return undefined;
        }
        let ativo = true;
        const timer = setTimeout(() => {
            ApiService.getSugestoesNome(termo).then((lista) => {
                if (ativo) setSugestoesNome(lista.slice(0, 6));
            });
        }, 250);
        return () => {
            ativo = false;
            clearTimeout(timer);
        };
    }, [codigoNovo, descricao]);

    // Item novo: categorias e unidades do cadastro do site.
    useEffect(() => {
        if (!codigoNovo) return undefined;
        let ativo = true;
        ApiService.getDocumentosFiscaisConfig().then((result) => {
            if (!ativo) return;
            if (!result?.success) {
                setErro(result?.offline ? 'Sem conexão com o servidor.' : (result?.message || 'Não foi possível carregar as categorias.'));
                return;
            }
            const data = result.data || {};
            setOpcoes({
                categorias: Array.isArray(data.categorias) ? data.categorias : [],
                unidades: Array.isArray(data.unidades_base) && data.unidades_base.length ? data.unidades_base : UNIDADES,
            });
        });
        return () => {
            ativo = false;
        };
    }, [codigoNovo]);

    const abrirLeitor = useCallback(async () => {
        InactivityService.recordActivity();
        setErro('');
        if (!permission?.granted) {
            const answer = await requestPermission();
            if (!answer?.granted) return;
        }
        lido.current = false;
        setLendo(true);
    }, [permission?.granted, requestPermission]);

    // Código de barras do DANFE (Code128, 44 dígitos) ou QR da NFC-e (a chave vem dentro do endereço).
    const aoLer = useCallback(async ({ data }) => {
        const match = String(data || '').replace(/\s+/g, '').match(/\d{44}/);
        if (!match || lido.current) return;
        lido.current = true;
        Vibration.vibrate(60);
        setLendo(false);
        setConsultando(true);
        const result = await ApiService.lerChaveAcesso(match[0]);
        setConsultando(false);
        if (!result.success) {
            setNota(null);
            setErro(result.message || 'Não foi possível ler a chave.');
            return;
        }
        const chave = result.chave || {};
        setNota({
            chave: chave.chave_acesso,
            numero: chave.numero_documento,
            serie: chave.serie,
            modelo: chave.modelo_label,
            cnpj: chave.cnpj_emitente,
            fornecedor: result.fornecedor?.nome || result.documento?.fornecedor_nome || null,
            fornecedorId: result.fornecedor?.id || null,
        });
        // Nota que já está no GALINT: as datas dela.
        if (result.documento?.data_emissao) setEmissao(String(result.documento.data_emissao).slice(0, 10));
        if (result.documento?.data_recebimento) setRecebimento(String(result.documento.data_recebimento).slice(0, 10));
    }, []);

    const escolherData = useCallback((atual, definir) => {
        InactivityService.recordActivity();
        DateTimePickerAndroid.open({
            value: parseIso(atual),
            mode: 'date',
            maximumDate: new Date(),
            onChange: (event, date) => {
                if (event?.type === 'set' && date) definir(isoDate(date));
            },
        });
    }, []);

    const quantidadeNum = Number(normalizeDecimal(quantidade));
    // Item novo não tem embalagem (entra na unidade escolhida); item existente segue o cadastro.
    const embalagem = useMemo(
        () => (novo ? { factor: 0, docUnit: unidade, baseUnit: unidade, packaged: false } : factorFromItem(item)),
        [item, novo, unidade],
    );
    const prova = computeProof({ quantity: quantidade, unitPrice: valor, ...embalagem });
    const unidadeQuantidade = unitLabel(embalagem.packaged ? embalagem.docUnit : embalagem.baseUnit, 2);
    const faltando = useMemo(() => {
        if (novo && !descricao.trim()) return 'Falta a descrição';
        if (novo && !categoria) return 'Falta a categoria';
        if (!(quantidadeNum > 0)) return 'Falta a quantidade';
        if (!nota) return 'Falta ler a chave';
        if (!emissao) return 'Falta a data de emissão';
        if (!recebimento) return 'Falta a data de recebimento';
        return '';
    }, [categoria, descricao, emissao, nota, novo, quantidadeNum, recebimento]);

    // Prova real: antes de gravar, pergunta se o cálculo é este mesmo.
    const confirmarLancamento = useCallback(() => {
        if (faltando || salvando || !prova) return;
        Keyboard.dismiss();
        const texto = [prova.stockText, prova.moneyText, prova.hint ? `⚠ ${prova.hint}` : ''].filter(Boolean).join('\n');
        Alert.alert('Prova real', `${texto}\n\nO cálculo é este mesmo?`, [
            { text: 'Corrigir', style: 'cancel' },
            { text: 'Confirmar', onPress: () => lancar() },
        ]);
    }, [faltando, salvando, prova]); // eslint-disable-line react-hooks/exhaustive-deps

    const lancar = useCallback(async () => {
        if (faltando || salvando) return;
        InactivityService.recordActivity();
        setSalvando(true);
        setErro('');
        const valorNum = Number(normalizeDecimal(valor));
        const descricaoNova = descricao.trim().toUpperCase();
        const result = await ApiService.registrarDocumentoFiscal({
            doc_mode: 'nf',
            finance_tipo_documento: 'nf',
            finance_origem_valor: 'compra_nf',
            finance_comprovacao_status: 'comprovado',
            codigo,
            ...(novo
                ? {
                    novo_codigo: codigo,
                    nova_descricao: descricaoNova,
                    nova_categoria: categoria,
                    nova_marca: marca.trim().toUpperCase() || undefined,
                    nova_unidade: unidade,
                }
                : {}),
            quantidade: quantidadeNum,
            nota_fiscal: nota.numero,
            chave_acesso: nota.chave,
            supplier_cnpj: nota.cnpj,
            supplier_name: nota.fornecedor || undefined,
            finance_supplier_id: nota.fornecedorId || undefined,
            data_emissao: emissao,
            data_recebimento: recebimento,
            preco_unitario: valorNum > 0 ? valorNum : undefined,
        });
        setSalvando(false);
        if (!result?.success) {
            setErro(result?.message || 'Não foi possível lançar a entrada.');
            return;
        }
        if (novo) {
            const itemCriado = { ...(result.data?.item || {}), codigo };
            itemCriado.descricao = itemCriado.descricao || descricaoNova;
            setCriado(itemCriado);
            setDone({
                title: 'Item cadastrado',
                itemName: itemCriado.descricao,
                summary: `NF ${nota.numero} • +${quantidade.replace('.', ',')}${result.data?.pre_cadastro_pendente ? '\nO saldo entra ao concluir o pré-cadastro no site.' : ''}`,
                photoUri: null,
                onFinish: () => {
                    setDone(null);
                    navigation.goBack();
                },
            });
            return;
        }
        setUltimaEntrada({ numero: nota.numero, tipo_documento: 'nf', data: recebimento });
        const saldo = result.data?.item?.saldo_display || result.data?.item?.saldo;
        setDone({
            title: 'Entrada lançada',
            itemName: item.descricao || 'Item',
            summary: `NF ${nota.numero} • +${quantidade.replace('.', ',')}${saldo != null ? ` • saldo agora: ${saldo}` : ''}`,
            photoUri: resolvePhotoUri(item),
            newLabel: 'Outra nota',
            onNew: () => {
                setDone(null);
                setNota(null);
                setQuantidade('');
                setValor('');
                setEmissao('');
            },
            onFinish: () => {
                setDone(null);
                navigation.goBack();
            },
        });
    }, [categoria, codigo, descricao, emissao, faltando, item, marca, navigation, nota, novo, quantidade, quantidadeNum, recebimento, salvando, unidade, valor]);

    const photoUri = photoFailed ? null : resolvePhotoUri(item);

    return (
        <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
            <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
                {novo ? (
                    <>
                        <View style={styles.itemRow}>
                            <View style={[styles.photo, styles.photoEmpty]}>
                                <Text style={styles.photoEmptyText}>📦</Text>
                            </View>
                            <View style={{ flex: 1 }}>
                                <Text style={styles.itemName}>Item novo</Text>
                                <Text style={styles.itemMeta}>{codigo}</Text>
                            </View>
                        </View>

                        <Text style={styles.label}>Descrição</Text>
                        <TextInput
                            style={[styles.input, styles.inputText]}
                            value={descricao}
                            onChangeText={setDescricao}
                            autoCapitalize="characters"
                            autoCorrect={false}
                            placeholder="Nome do item"
                            placeholderTextColor="#94a3b8"
                        />
                        {sugestoesNome.length ? (
                            <View style={styles.nomes}>
                                {sugestoesNome.map((sugestao) => (
                                    <TouchableOpacity
                                        key={`${sugestao.tipo}-${sugestao.nome}`}
                                        style={styles.nomeLinha}
                                        onPress={() => {
                                            const nome = String(sugestao.nome || '').toUpperCase();
                                            nomeEscolhido.current = nome;
                                            setDescricao(nome);
                                            setSugestoesNome([]);
                                            if (sugestao.unidade && opcoes.unidades.includes(sugestao.unidade)) setUnidade(sugestao.unidade);
                                        }}
                                        activeOpacity={0.8}
                                    >
                                        <Text style={styles.nomeTexto} numberOfLines={1}>{sugestao.nome}</Text>
                                        {sugestao.tipo === 'grupo' ? <Text style={styles.nomeGrupo}>grupo</Text> : null}
                                    </TouchableOpacity>
                                ))}
                            </View>
                        ) : null}

                        <Text style={styles.label}>Categoria</Text>
                        <TouchableOpacity style={styles.dateField} onPress={() => { Keyboard.dismiss(); setEscolhendoCategoria(true); }} activeOpacity={0.85}>
                            <Text style={categoria ? styles.dateText : styles.datePlaceholder} numberOfLines={1}>{categoria || 'Escolher'}</Text>
                        </TouchableOpacity>

                        <Text style={styles.label}>Marca</Text>
                        <TextInput
                            style={[styles.input, styles.inputText]}
                            value={marca}
                            onChangeText={setMarca}
                            autoCorrect={false}
                            placeholder="Opcional"
                            placeholderTextColor="#94a3b8"
                        />

                        <Text style={styles.label}>Unidade</Text>
                        <View style={styles.chips}>
                            {opcoes.unidades.map((opcao) => (
                                <TouchableOpacity
                                    key={opcao}
                                    style={[styles.chip, unidade === opcao && styles.chipOn]}
                                    onPress={() => setUnidade(opcao)}
                                    activeOpacity={0.85}
                                >
                                    <Text style={[styles.chipText, unidade === opcao && styles.chipTextOn]}>{opcao}</Text>
                                </TouchableOpacity>
                            ))}
                        </View>
                    </>
                ) : (
                <View style={styles.itemRow}>
                    {photoUri ? (
                        <Image source={{ uri: photoUri }} style={styles.photo} resizeMode="cover" onError={() => setPhotoFailed(true)} />
                    ) : (
                        <TouchableOpacity style={[styles.photo, styles.photoEmpty]} onPress={() => setPhotoModal(true)} activeOpacity={0.8} accessibilityLabel="Pôr foto no item">
                            <Text style={styles.photoEmptyText}>📷</Text>
                            <Text style={styles.photoAdd}>Pôr foto</Text>
                        </TouchableOpacity>
                    )}
                    <View style={{ flex: 1 }}>
                        <Text style={styles.itemName} numberOfLines={2}>{item.descricao || 'Item'}</Text>
                        <View style={styles.metaRow}>
                            <View style={{ flex: 1 }}>
                                <Text style={styles.itemMeta}>{codigo}</Text>
                                {item.saldo_display ? <Text style={styles.itemMeta}>Saldo: {item.saldo_display}</Text> : null}
                            </View>
                            {ultimaEntrada?.numero ? (
                                <View style={styles.lastEntry}>
                                    <Text style={styles.lastEntryNumber}>{documentLabel(ultimaEntrada)}</Text>
                                    {ultimaEntrada.data ? <Text style={styles.lastEntryDate}>{brDate(String(ultimaEntrada.data).slice(0, 10))}</Text> : null}
                                    {nota && sameDocumentNumber(nota.numero, ultimaEntrada.numero) ? <Text style={styles.lastEntrySame}>já lançado nesta NF</Text> : null}
                                </View>
                            ) : null}
                        </View>
                    </View>
                </View>
                )}

                <Text style={styles.label}>Chave de acesso</Text>
                {nota ? (
                    <TouchableOpacity style={styles.noteCard} onPress={abrirLeitor} activeOpacity={0.85}>
                        <Text style={styles.noteTitle}>NF {nota.numero} • série {nota.serie}</Text>
                        <Text style={styles.noteLine}>{nota.fornecedor ? `${nota.fornecedor} • ` : ''}{nota.cnpj}</Text>
                        <Text style={styles.noteKey}>{groupKey(nota.chave)}</Text>
                        <Text style={styles.noteAgain}>Ler outra chave</Text>
                    </TouchableOpacity>
                ) : (
                    <TouchableOpacity style={styles.scanButton} onPress={abrirLeitor} disabled={consultando} activeOpacity={0.85}>
                        {consultando ? <ActivityIndicator color={heroPalette.bg} /> : <Text style={styles.scanText}>📷  Ler a chave da nota</Text>}
                    </TouchableOpacity>
                )}

                <Text style={styles.label}>Quantidade ({unidadeQuantidade})</Text>
                <TextInput
                    style={styles.input}
                    value={quantidade}
                    onChangeText={(text) => setQuantidade(text.replace(/[^0-9.,]/g, ''))}
                    keyboardType="decimal-pad"
                    placeholder="0"
                    placeholderTextColor={heroPalette.textMuted}
                />

                <View style={styles.dateRow}>
                    <View style={{ flex: 1 }}>
                        <Text style={styles.label}>Emissão</Text>
                        <TouchableOpacity style={styles.dateField} onPress={() => escolherData(emissao, setEmissao)} activeOpacity={0.85}>
                            <Text style={emissao ? styles.dateText : styles.datePlaceholder}>{emissao ? brDate(emissao) : 'dd/mm/aaaa'}</Text>
                        </TouchableOpacity>
                    </View>
                    <View style={{ flex: 1 }}>
                        <Text style={styles.label}>Recebimento</Text>
                        <TouchableOpacity style={styles.dateField} onPress={() => escolherData(recebimento, setRecebimento)} activeOpacity={0.85}>
                            <Text style={styles.dateText}>{brDate(recebimento)}</Text>
                        </TouchableOpacity>
                    </View>
                </View>

                <Text style={styles.label}>Valor unitário (R$)</Text>
                <TextInput
                    style={styles.input}
                    value={valor}
                    onChangeText={(text) => setValor(text.replace(/[^0-9.,]/g, ''))}
                    keyboardType="decimal-pad"
                    placeholder="0,00"
                    placeholderTextColor={heroPalette.textMuted}
                />

                {prova ? (
                    <View style={[styles.prova, prova.suspicious && styles.provaAlerta]}>
                        <Text style={styles.provaTexto}>{prova.stockText}</Text>
                        {prova.moneyText ? <Text style={styles.provaTexto}>{prova.moneyText}</Text> : null}
                        {prova.hint ? <Text style={styles.provaDica}>⚠ {prova.hint}</Text> : null}
                    </View>
                ) : null}

                {erro ? <Text style={styles.error}>⚠ {erro}</Text> : null}

                <TouchableOpacity style={[styles.button, (faltando || salvando) && styles.buttonOff]} onPress={confirmarLancamento} disabled={Boolean(faltando) || salvando} activeOpacity={0.85}>
                    {salvando ? <ActivityIndicator color={heroPalette.bg} /> : <Text style={styles.buttonText}>{faltando || 'Lançar entrada'}</Text>}
                </TouchableOpacity>
            </ScrollView>

            <Modal visible={lendo} animationType="fade" onRequestClose={() => setLendo(false)}>
                <View style={styles.scanner}>
                    <CameraView
                        style={StyleSheet.absoluteFill}
                        facing="back"
                        autoFocus="on"
                        barcodeScannerSettings={{ barcodeTypes: ['code128', 'qr'] }}
                        onBarcodeScanned={lendo ? aoLer : undefined}
                    />
                    <View style={styles.scanFrame} pointerEvents="none" />
                    <Text style={styles.scanHint}>Aponte para o código de barras da nota</Text>
                    <TouchableOpacity style={styles.scanClose} onPress={() => setLendo(false)} activeOpacity={0.85}>
                        <Text style={styles.scanCloseText}>Fechar</Text>
                    </TouchableOpacity>
                </View>
            </Modal>

            <Modal visible={escolhendoCategoria} transparent animationType="fade" onRequestClose={() => setEscolhendoCategoria(false)}>
                <TouchableOpacity style={styles.pickerBackdrop} activeOpacity={1} onPress={() => setEscolhendoCategoria(false)}>
                    <View style={styles.pickerPanel}>
                        <Text style={styles.pickerTitle}>Categoria</Text>
                        <FlatList
                            data={opcoes.categorias}
                            keyExtractor={(opcao) => opcao}
                            ListEmptyComponent={<ActivityIndicator color={heroPalette.primaryStrong} style={{ marginVertical: 24 }} />}
                            renderItem={({ item: opcao }) => (
                                <TouchableOpacity
                                    style={[styles.pickerRow, categoria === opcao && styles.pickerRowOn]}
                                    onPress={() => {
                                        setCategoria(opcao);
                                        setEscolhendoCategoria(false);
                                    }}
                                >
                                    <Text style={styles.pickerRowText}>{opcao}</Text>
                                </TouchableOpacity>
                            )}
                        />
                    </View>
                </TouchableOpacity>
            </Modal>

            <ItemPhotoLinkModal
                item={item}
                visible={photoModal}
                onClose={() => setPhotoModal(false)}
                onSaved={(fotoUrl) => {
                    setPhotoModal(false);
                    setPhotoFailed(false);
                    setFotoNova(fotoUrl);
                }}
            />
            <DoneModal done={done} />
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: heroPalette.bg },
    scroll: { padding: 16, paddingBottom: 40 },
    itemRow: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 14, borderRadius: 18, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border, ...heroSoftShadow },
    photo: { width: 72, height: 72, borderRadius: 14, backgroundColor: '#fff' },
    photoEmpty: { alignItems: 'center', justifyContent: 'center', backgroundColor: heroPalette.panelAlt },
    photoEmptyText: { fontSize: 24 },
    photoAdd: { color: heroPalette.primary, fontSize: 11, fontWeight: '800', marginTop: 2 },
    itemName: { color: heroPalette.text, fontSize: 16, fontWeight: '800' },
    itemMeta: { color: heroPalette.textMuted, fontSize: 13, marginTop: 2 },
    metaRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 8 },
    lastEntry: { alignItems: 'flex-end' },
    lastEntryNumber: { color: '#ef4444', fontSize: 15, fontWeight: '900' },
    lastEntryDate: { color: heroPalette.text, fontSize: 15, fontWeight: '800' },
    lastEntrySame: { color: '#ef4444', fontSize: 12, fontWeight: '800', marginTop: 2 },
    label: { color: heroPalette.textSoft, fontSize: 14, fontWeight: '800', marginTop: 18, marginBottom: 8 },
    scanButton: { height: 56, borderRadius: 16, backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center' },
    scanText: { color: heroPalette.bg, fontSize: 16, fontWeight: '900' },
    noteCard: { padding: 14, borderRadius: 16, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.borderStrong },
    noteTitle: { color: heroPalette.text, fontSize: 17, fontWeight: '900' },
    noteLine: { color: heroPalette.textSoft, fontSize: 13, marginTop: 4 },
    noteKey: { color: heroPalette.textMuted, fontSize: 12, marginTop: 6, letterSpacing: 0.5 },
    noteAgain: { color: heroPalette.primary, fontSize: 13, fontWeight: '800', marginTop: 8 },
    input: { backgroundColor: '#fff', color: '#0f172a', borderRadius: 14, paddingHorizontal: 16, height: 54, fontSize: 20, fontWeight: '800' },
    inputText: { fontSize: 16, fontWeight: '700' },
    chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
    chip: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 999, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border },
    chipOn: { backgroundColor: heroPalette.primaryStrong, borderColor: heroPalette.primaryStrong },
    chipText: { color: heroPalette.textSoft, fontSize: 15, fontWeight: '800' },
    chipTextOn: { color: heroPalette.bg },
    pickerBackdrop: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(2, 6, 23, 0.6)' },
    pickerPanel: { maxHeight: '70%', backgroundColor: heroPalette.panel, borderTopLeftRadius: 22, borderTopRightRadius: 22, paddingTop: 16, paddingBottom: 24, borderWidth: 1, borderColor: heroPalette.border },
    pickerTitle: { color: heroPalette.textMuted, fontSize: 13, fontWeight: '800', paddingHorizontal: 20, paddingBottom: 8 },
    pickerRow: { paddingHorizontal: 20, paddingVertical: 15, borderBottomWidth: 1, borderBottomColor: heroPalette.border },
    pickerRowOn: { backgroundColor: heroPalette.panelAlt },
    pickerRowText: { color: heroPalette.text, fontSize: 16, fontWeight: '700' },
    nomes: { marginTop: 6, borderRadius: 12, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border, overflow: 'hidden' },
    nomeLinha: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: heroPalette.border },
    nomeTexto: { flex: 1, color: heroPalette.text, fontSize: 15, fontWeight: '700' },
    nomeGrupo: { color: '#0f172a', backgroundColor: '#fbbf24', fontSize: 11, fontWeight: '900', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, overflow: 'hidden' },
    dateRow: { flexDirection: 'row', gap: 12 },
    dateField: { height: 54, borderRadius: 14, backgroundColor: '#fff', justifyContent: 'center', paddingHorizontal: 16 },
    dateText: { color: '#0f172a', fontSize: 17, fontWeight: '800' },
    datePlaceholder: { color: '#94a3b8', fontSize: 17, fontWeight: '700' },
    prova: { marginTop: 14, padding: 12, borderRadius: 14, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border, gap: 2 },
    provaAlerta: { borderColor: '#f59e0b', backgroundColor: 'rgba(245, 158, 11, 0.12)' },
    provaTexto: { color: heroPalette.text, fontSize: 15, fontWeight: '700' },
    provaDica: { color: '#fbbf24', fontSize: 14, fontWeight: '800', marginTop: 4 },
    error: { color: heroPalette.danger, fontSize: 14, fontWeight: '700', marginTop: 14, textAlign: 'center' },
    button: { marginTop: 22, height: 56, borderRadius: 16, backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center' },
    buttonOff: { opacity: 0.5 },
    buttonText: { color: heroPalette.bg, fontSize: 17, fontWeight: '900' },
    scanner: { flex: 1, backgroundColor: '#000', alignItems: 'center', justifyContent: 'center' },
    scanFrame: { width: '86%', height: 130, borderRadius: 16, borderWidth: 3, borderColor: heroPalette.primaryStrong },
    scanHint: { position: 'absolute', top: 70, color: '#fff', fontSize: 16, fontWeight: '800', textAlign: 'center', paddingHorizontal: 24 },
    scanClose: { position: 'absolute', bottom: 60, paddingHorizontal: 28, paddingVertical: 14, borderRadius: 14, backgroundColor: 'rgba(6,16,27,0.8)' },
    scanCloseText: { color: '#fff', fontSize: 16, fontWeight: '800' },
});
