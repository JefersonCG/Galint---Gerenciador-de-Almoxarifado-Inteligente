// Busca de material pelo que foi falado (ou digitado), 2.6.0. Pedido do usuário em 27/11/2026:
//   "aperto no microfone e falo 0265 e ele acha a parafusadeira da Wesco; falo 20 amperes ou 20A e ele procura os
//   itens com 20 A, zerados ou não; falo 'fio preto 2mm' ou 'fio de 2 e meio' e ele acha todos os fios; 'bucha de
//   redução' traz todas as buchas; temos itens com abreviação, tipo Adap. = adaptador".
//
// Como entende:
// - código: a fala só com números ("0265", "0 2 6 5") procura primeiro o código do item;
// - números falados por extenso viram algarismos ("vinte" → 20, "dois e meio" → 2,5, "meia polegada" → 0,5 pol);
// - unidades faladas viram a sigla e grudam no número ("20 amperes" = "20 A" = "20A"; "2 milímetros" = "2MM");
// - cada palavra falada precisa estar no item, mas vale abreviação e plural ("adaptador" acha "ADAP.", "redução"
//   acha "RED.", "buchas" acha "BUCHA") e erro pequeno do reconhecimento ("wasco" acha "WESCO");
// - número com palavras só ordena (o 2,5 sobe quando se fala "2"); só números (sem palavras) precisam bater;
// - zerados entram, depois dos que têm saldo quando empatam.
// Funções puras: o app passa a lista de itens da base do celular (services/localDb.js).

const SEM_ACENTO = /[̀-ͯ]/g;

const UNIDADES = {
    a: 'a', amp: 'a', amper: 'a', ampere: 'a', amperes: 'a', ampers: 'a', amperi: 'a',
    mm: 'mm', milimetro: 'mm', milimetros: 'mm', mili: 'mm',
    cm: 'cm', centimetro: 'cm', centimetros: 'cm',
    m: 'm', metro: 'm', metros: 'm', mt: 'm', mts: 'm',
    v: 'v', volt: 'v', volts: 'v', vca: 'v', vac: 'v',
    w: 'w', watt: 'w', watts: 'w',
    pol: 'pol', polegada: 'pol', polegadas: 'pol',
    kg: 'kg', quilo: 'kg', quilos: 'kg', kilo: 'kg', kilos: 'kg',
    g: 'g', grama: 'g', gramas: 'g',
    l: 'l', lt: 'l', litro: 'l', litros: 'l',
    ml: 'ml', mililitro: 'ml', mililitros: 'ml',
    kva: 'kva', hp: 'hp', cv: 'cv', bar: 'bar',
};

const NUMEROS = {
    zero: 0, um: 1, uma: 1, dois: 2, duas: 2, tres: 3, quatro: 4, cinco: 5, seis: 6, sete: 7, oito: 8, nove: 9,
    dez: 10, onze: 11, doze: 12, treze: 13, catorze: 14, quatorze: 14, quinze: 15, dezesseis: 16, dezasseis: 16,
    dezessete: 17, dezoito: 18, dezenove: 19, vinte: 20, trinta: 30, quarenta: 40, cinquenta: 50, sessenta: 60,
    setenta: 70, oitenta: 80, noventa: 90, cem: 100, cento: 100, duzentos: 200, trezentos: 300, quatrocentos: 400,
    quinhentos: 500, seiscentos: 600, setecentos: 700, oitocentos: 800, novecentos: 900,
};

const PARADAS = new Set(['de', 'da', 'do', 'das', 'dos', 'com', 'para', 'pra', 'p', 'e', 'o', 'os', 'as', 'um', 'uma', 'em', 'no', 'na', 'nos', 'nas', 'ou', 'a', 'x', 'tem', 'temos', 'quero', 'procura', 'procurar', 'acha', 'achar']);

export function semAcento(texto) {
    return String(texto ?? '').normalize('NFD').replace(SEM_ACENTO, '').toLowerCase();
}

function brutos(texto) {
    return semAcento(texto)
        .replace(/(\d),(\d)/g, '$1.$2')
        .replace(/''|"|”|“|″/g, ' pol ')
        .replace(/(\d)([a-z])/g, '$1 $2')
        .replace(/([a-z])(\d)/g, '$1 $2')
        .split(/[^a-z0-9./]+/)
        .map((parte) => parte.replace(/^[./]+|[./]+$/g, ''))
        .filter(Boolean);
}

function comoNumero(token) {
    if (/^\d+\/\d+$/.test(token)) {
        const [a, b] = token.split('/').map(Number);
        return b ? a / b : null;
    }
    if (/^\d+(\.\d+)?$/.test(token)) return Number(token);
    return null;
}

// Fala: "0 2 6 5" → "0265"; "vinte e cinco" → 25; "dois e meio" / "2 e meio" → 2.5; "meia" → 0.5.
function juntarFala(lista) {
    const saida = [];
    for (let i = 0; i < lista.length; i += 1) {
        // algarismos soltos em sequência (3 ou mais) são um código ditado
        if (/^\d$/.test(lista[i])) {
            let j = i;
            while (j < lista.length && /^\d$/.test(lista[j])) j += 1;
            if (j - i >= 3) {
                saida.push(lista.slice(i, j).join(''));
                i = j - 1;
                continue;
            }
        }
        let valor = null;
        let j = i;
        while (j < lista.length) {
            const palavra = lista[j];
            const parte = Object.prototype.hasOwnProperty.call(NUMEROS, palavra) ? NUMEROS[palavra] : comoNumero(palavra);
            if (parte === null || parte === undefined) {
                if ((palavra === 'meio' || palavra === 'meia') && valor !== null) {
                    valor += 0.5;
                    j += 1;
                }
                break;
            }
            if (valor !== null && !(lista[j - 1] === 'e')) break; // "2 3" são dois números
            valor = valor === null ? parte : valor + parte;
            j += 1;
            if (lista[j] === 'e' && j + 1 < lista.length) {
                const seguinte = lista[j + 1];
                if (seguinte === 'meio' || seguinte === 'meia') {
                    valor += 0.5;
                    j += 2;
                    break;
                }
                if (Object.prototype.hasOwnProperty.call(NUMEROS, seguinte) || comoNumero(seguinte) !== null) {
                    j += 1; // "vinte e cinco": junta
                    continue;
                }
            }
            break;
        }
        if (valor === null && (lista[i] === 'meia' || lista[i] === 'meio')) {
            saida.push('0.5');
            continue;
        }
        if (valor !== null && j > i) {
            // "um"/"uma" sozinho antes de palavra é artigo ("um adaptador"), não número
            if ((lista[i] === 'um' || lista[i] === 'uma') && j === i + 1 && !(lista[j] in UNIDADES)) {
                continue;
            }
            // número sozinho fica como foi dito/escrito (o zero à esquerda do código "0265" não pode sumir)
            saida.push(j === i + 1 && /^\d+(\.\d+)?$/.test(lista[i]) ? lista[i] : String(valor));
            i = j - 1;
            continue;
        }
        saida.push(lista[i]);
    }
    return saida;
}

// { palavras: [..], numeros: [{ v, u }] }
export function termos(texto, { falado = false } = {}) {
    let lista = brutos(texto);
    if (falado) lista = juntarFala(lista);
    const palavras = [];
    const numeros = [];
    let ultimoNumero = null; // a unidade só gruda no número logo antes dela ("20 amperes", "2.5 mm")
    lista.forEach((token) => {
        const numero = comoNumero(token);
        if (numero !== null) {
            ultimoNumero = { v: numero, u: null };
            numeros.push(ultimoNumero);
            return;
        }
        const unidade = UNIDADES[token];
        if (unidade && ultimoNumero && ultimoNumero.u === null) {
            ultimoNumero.u = unidade;
            ultimoNumero = null;
            return;
        }
        ultimoNumero = null;
        if (PARADAS.has(token) || token.length < 2) return;
        palavras.push(token);
    });
    return { palavras, numeros };
}

function distancia(a, b) {
    if (Math.abs(a.length - b.length) > 2) return 3;
    const linha = Array.from({ length: b.length + 1 }, (_, k) => k);
    for (let i = 1; i <= a.length; i += 1) {
        let anterior = linha[0];
        linha[0] = i;
        for (let j = 1; j <= b.length; j += 1) {
            const guardado = linha[j];
            linha[j] = Math.min(linha[j] + 1, linha[j - 1] + 1, anterior + (a[i - 1] === b[j - 1] ? 0 : 1));
            anterior = guardado;
        }
    }
    return linha[b.length];
}

function palavraBate(falada, doItem) {
    if (falada === doItem) return 3;
    const [curta, longa] = doItem.length <= falada.length ? [doItem, falada] : [falada, doItem];
    if (curta.length >= 3 && longa.startsWith(curta)) return 2; // abreviação ("adap") e plural ("buchas")
    if (falada.length >= 4 && distancia(falada, doItem) <= (falada.length >= 7 ? 2 : 1)) return 1; // "wasco" → "wesco"
    return 0;
}

function codigoDoItem(item) {
    return String(item?.codigo_barras ?? item?.codigo ?? item?.id ?? '').trim();
}

function termosDoItem(item) {
    if (!item._termosBusca) {
        Object.defineProperty(item, '_termosBusca', {
            value: termos(`${item?.descricao ?? item?.nome ?? ''} ${item?.marca ?? ''}`),
            enumerable: false,
        });
    }
    return item._termosBusca;
}

function saldoDe(item) {
    const valor = Number(item?.quantidade ?? item?.saldo ?? 0);
    return Number.isFinite(valor) ? valor : 0;
}

export function pontuar(item, consulta, digitos) {
    let nota = 0;
    const codigo = codigoDoItem(item);
    if (digitos) {
        if (codigo === digitos) return 1000;
        if (digitos.length >= 4 && codigo.endsWith(digitos)) nota += 50;
    }
    const doItem = termosDoItem(item);
    // Toda palavra falada precisa estar no item; com 3 ou mais, pode faltar uma ("cabo pp 3 vias": o cadastro não
    // escreve "vias"), e o item desce na lista.
    const faltaPermitida = consulta.palavras.length >= 3 ? 1 : 0;
    let faltaram = 0;
    for (const falada of consulta.palavras) {
        let melhor = 0;
        for (const palavra of doItem.palavras) {
            melhor = Math.max(melhor, palavraBate(falada, palavra));
            if (melhor === 3) break;
        }
        if (!melhor) {
            faltaram += 1;
            if (faltaram > faltaPermitida) return nota >= 50 ? nota : 0;
            nota -= 3;
            continue;
        }
        nota += melhor;
    }
    if (consulta.palavras.length && faltaram === consulta.palavras.length) return nota >= 50 ? nota : 0;
    let numerosQueBatem = 0;
    for (const falado of consulta.numeros) {
        let melhor = 0;
        for (const numero of doItem.numeros) {
            if (falado.u && numero.u && falado.u !== numero.u) continue;
            const mesmaUnidade = Boolean(falado.u && numero.u);
            if (Math.abs(numero.v - falado.v) < 1e-9) {
                melhor = Math.max(melhor, mesmaUnidade ? 5 : (falado.u ? 1 : 4));
            } else if (Number.isInteger(falado.v) && !Number.isInteger(numero.v) && Math.floor(numero.v) === falado.v) {
                melhor = Math.max(melhor, mesmaUnidade || !falado.u ? 2 : 0); // "fio de 2" acha o 2,5
            }
        }
        if (melhor >= 2) numerosQueBatem += 1;
        nota += melhor;
    }
    if (!consulta.palavras.length && consulta.numeros.length && numerosQueBatem < consulta.numeros.length) {
        return nota >= 50 ? nota : 0; // só números (ex.: "20 amperes"): todos precisam estar no item
    }
    return nota;
}

// ---------- Comandos falados (2.6.1) ----------
// Pedido do usuário em 27/11/2026: "eu falo 'Retirada lâmpada bolbo 9w kian 6 unidades' e ele abre a retirada com o
// material que pedi e a quantidade". A 1ª palavra diz a ação; "<número> <unidades/caixas/rolos…>" no fim é a
// quantidade (o "9w" do meio é do material); o resto é o material.
const COMANDOS = [
    { acao: 'retirada', palavras: ['dar saida', 'retirada', 'retirar', 'retira', 'tirar', 'saida'] },
    { acao: 'devolucao', palavras: ['devolucao', 'devolver', 'devolve', 'devolvendo'] },
    { acao: 'alterar', palavras: ['alteracao', 'alterar', 'altera', 'conferencia', 'conferir', 'contagem', 'contar', 'ajustar', 'ajuste'] },
    // 2.6.2: "custódia furadeira", "com quem está a trena", "custódia Gláucia"
    { acao: 'custodia', palavras: ['com quem esta', 'quem esta com', 'custodia', 'custodias', 'onde esta'] },
];
const QTD_BASE = new Set(['unidade', 'unidades', 'un', 'und', 'unid', 'peca', 'pecas', 'pc', 'pcs', 'metro', 'metros', 'litro', 'litros', 'quilo', 'quilos', 'kg']);
const QTD_EMBALAGEM = new Set(['caixa', 'caixas', 'cx', 'pacote', 'pacotes', 'pct', 'rolo', 'rolos', 'lata', 'latas', 'balde', 'baldes', 'saco', 'sacos', 'fardo', 'fardos', 'galao', 'galoes', 'bombona', 'bombonas']);
const QTD_ROTULO = new Set(['quantidade', 'qtd', 'qtde', 'quant']);

// ---------- Quem retira ou devolve e o local, ditos no comando (2.6.2) ----------
// Pedido do usuário em 27/11/2026: "Retirada por/para Gláucia de 5 papel toalhas interfolhas para local das áreas
// comuns e banheiros": o colaborador e o local vão para a tela seguinte, mesmo quando o material sai numa lista.
const PREP_PESSOA = new Set(['por', 'para', 'pra', 'pro']);
const ANTES_DO_LOCAL = new Set(['para', 'pra', 'pro', 'no', 'na', 'em', 'o', 'a', 'ao', 'do', 'da', 'de', 'e']);
const ARTIGO_DO_LOCAL = new Set(['de', 'do', 'da', 'dos', 'das', 'o', 'a', 'os', 'as', 'no', 'na', 'nos', 'nas', 'e']);
const LIGA_NOME = new Set(['de', 'da', 'do', 'das', 'dos', 'e', 'o', 'a']); // "para o Luiz", "da Gláucia"
const DE = new Set(['de', 'do', 'da', 'dos', 'das']);
const temChave = (objeto, chave) => Object.prototype.hasOwnProperty.call(objeto, chave);
const ehQtd = (palavra) => QTD_BASE.has(palavra) || QTD_EMBALAGEM.has(palavra);

// Palavras como foram ditas (o local e o nome ficam com acento) e a forma para comparar.
function palavrasDitas(texto) {
    return String(texto ?? '').split(/\s+/)
        .map((palavra) => palavra.replace(/^[.,;:!?()]+|[.,;:!?()]+$/g, ''))
        .filter(Boolean)
        .map((palavra) => ({ w: palavra, n: semAcento(palavra) }));
}

// Nomes: o reconhecimento escreve "Rafael" para RAPHAEL, "Tais" para THAÍS, "Luis" para LUIZ.
function fonetico(palavra) {
    return semAcento(palavra)
        .replace(/ph/g, 'f').replace(/th/g, 't').replace(/y/g, 'i').replace(/k/g, 'c').replace(/w/g, 'v').replace(/z/g, 's')
        .replace(/(^|[^cln])h/g, '$1')
        .replace(/(.)\1+/g, '$1');
}

function tokensDoNome(nome) {
    return semAcento(nome).split(/[^a-z0-9]+/).filter((t) => t && !LIGA_NOME.has(t)).map(fonetico);
}

// Nota do nome falado numa pessoa (0 = não é ela). Estrito: a 1ª palavra tem de ser igual (fora do começo da frase,
// "cola para cano" não pode virar a pessoa CAIO).
function notaDaPessoa(falados, pessoa, estrito) {
    if (falados.length === 1 && /^\d{3,}$/.test(falados[0])) return String(pessoa?.matricula || '') === falados[0] ? 10 : 0;
    const doNome = tokensDoNome(pessoa?.nome);
    if (!doNome.length || !falados.length) return 0;
    let nota = 0;
    for (let k = 0; k < falados.length; k += 1) {
        const falado = fonetico(falados[k]);
        let melhor = 0;
        for (const token of doNome) melhor = Math.max(melhor, palavraBate(falado, token));
        if (!melhor || (estrito && k === 0 && melhor < 3)) return 0;
        nota += melhor;
    }
    if (fonetico(falados[0]) === doNome[0]) nota += 1; // o 1º nome falado é o 1º nome da pessoa
    return nota;
}

// Pessoas do cadastro (/api/mobile/usuarios) que combinam com o nome falado, da mais para a menos parecida;
// `pessoa` só quando uma está à frente (duas GLÁUCIAs empatam e a tela mostra a lista).
export function acharPessoa(pessoas, texto) {
    const falados = semAcento(texto).split(/[^a-z0-9]+/).filter((t) => t && !LIGA_NOME.has(t));
    if (!falados.length || !Array.isArray(pessoas)) return { pessoa: null, candidatos: [] };
    const achados = pessoas
        .map((p) => ({ p, nota: notaDaPessoa(falados, p, false) }))
        .filter((achado) => achado.nota > 0)
        .sort((a, b) => b.nota - a.nota);
    const pessoa = achados.length && (achados.length === 1 || achados[0].nota > achados[1].nota) ? achados[0].p : null;
    return { pessoa, candidatos: achados.map((achado) => achado.p) };
}

// Quantas palavras do começo de `ws` são o nome de alguém do cadastro (0 = nenhuma).
function tamanhoDoNome(ws, pessoas, estrito) {
    for (let tam = Math.min(5, ws.length); tam >= 1; tam -= 1) {
        const parte = ws.slice(0, tam);
        if (LIGA_NOME.has(parte[tam - 1].n)) continue;
        const falados = parte.map((x) => x.n).filter((t) => !LIGA_NOME.has(t));
        if (falados.length && pessoas.some((p) => notaDaPessoa(falados, p, estrito) > 0)) return tam;
    }
    return 0;
}

const ehNumeroDito = (n) => /^\d/.test(n || '') || (temChave(NUMEROS, n || '') && n !== 'um' && n !== 'uma') || n === 'meia' || n === 'meio';

// A quantidade começa na palavra k ("5", "cinco", "de 5", "uma caixa"): é onde o nome dito antes acaba.
function comecaQuantidade(ws, k) {
    const n = ws[k]?.n;
    const seguinte = ws[k + 1]?.n;
    if (ehNumeroDito(n)) return true;
    if ((n === 'um' || n === 'uma') && ehQtd(seguinte)) return true;
    return DE.has(n) && (ehNumeroDito(seguinte) || ((seguinte === 'um' || seguinte === 'uma') && ehQtd(ws[k + 2]?.n)));
}

// { acao: 'retirada' | 'devolucao' | 'alterar' | 'custodia' | null, material, quantidade: número | null,
//   modo: 'base' | 'embalagem' | null, unidade: a palavra dita ("unidades", "rolos") | null,
//   pessoa: o nome como foi dito | null, local: como foi dito | null }
// `pessoas` (a lista de /api/mobile/usuarios) diz onde o nome acaba; sem ela, o nome logo depois da ação vai até a
// quantidade.
export function interpretarComando(texto, { pessoas = [] } = {}) {
    let ws = palavrasDitas(texto);
    let acao = null;
    for (const comando of COMANDOS) {
        const achada = comando.palavras.find((palavra) => palavra.split(' ').every((parte, k) => ws[k]?.n === parte));
        if (achada) {
            acao = comando.acao;
            ws = ws.slice(achada.split(' ').length);
            break;
        }
    }
    const temPessoas = Array.isArray(pessoas) && pessoas.length > 0;

    // Local: "para (o) local (das) áreas comuns e banheiros" vai até o fim, ou até "por/para <pessoa>" depois dele.
    let local = null;
    const iLocal = ws.findIndex((x) => x.n === 'local');
    if (iLocal >= 0 && iLocal + 1 < ws.length) {
        let inicio = iLocal;
        while (inicio > 0 && ANTES_DO_LOCAL.has(ws[inicio - 1].n)) inicio -= 1;
        let fim = ws.length;
        if (temPessoas) {
            for (let k = iLocal + 2; k < ws.length - 1; k += 1) {
                if (PREP_PESSOA.has(ws[k].n) && tamanhoDoNome(ws.slice(k + 1), pessoas, true)) {
                    fim = k;
                    break;
                }
            }
        }
        let corpo = ws.slice(iLocal + 1, fim);
        while (corpo.length > 1 && ARTIGO_DO_LOCAL.has(corpo[0].n)) corpo = corpo.slice(1);
        local = corpo.map((x) => x.w).join(' ') || null;
        ws = [...ws.slice(0, inicio), ...ws.slice(fim)];
    }

    // Pessoa logo depois da ação: "por/para Gláucia (de) 5 …".
    let pessoa = null;
    if (ws.length >= 3 && PREP_PESSOA.has(ws[0].n) && (ws[1].n === 'o' || ws[1].n === 'a')) ws = [ws[0], ...ws.slice(2)];
    if (ws.length >= 2 && PREP_PESSOA.has(ws[0].n)) {
        let fim = 1;
        while (fim < ws.length && !comecaQuantidade(ws, fim)) fim += 1;
        const ate = ws.slice(1, fim);
        let tam = temPessoas ? tamanhoDoNome(ate, pessoas, false) : 0;
        // nome que o cadastro não tem (ou sem a lista): vai até a quantidade, e a tela mostra a lista de pessoas
        if (!tam && (fim < ws.length || !temPessoas)) tam = Math.min(ate.length, 4);
        if (tam) {
            pessoa = ws.slice(1, 1 + tam).map((x) => x.w).join(' ');
            ws = ws.slice(1 + tam);
        }
    }
    // Pessoa em outro ponto ("… 5 papel toalha para Gláucia"): só quando o nome é de alguém do cadastro.
    if (!pessoa && temPessoas) {
        for (let k = 0; k < ws.length - 1; k += 1) {
            if (!PREP_PESSOA.has(ws[k].n)) continue;
            const tam = tamanhoDoNome(ws.slice(k + 1), pessoas, true);
            if (tam) {
                pessoa = ws.slice(k + 1, k + 1 + tam).map((x) => x.w).join(' ');
                ws = [...ws.slice(0, k), ...ws.slice(k + 1 + tam)];
                break;
            }
        }
    }

    // Quantidade e material: o que sobrou.
    const crus = brutos(ws.map((x) => x.w).join(' '));
    // "uma lata", "um rolo": no comando é quantidade (na busca, "um" antes de palavra é artigo: "um adaptador")
    let lista = juntarFala(crus.map((palavra, k) => ((palavra === 'um' || palavra === 'uma') && ehQtd(crus[k + 1]) ? '1' : palavra)));
    // "uma lata e meia" / "2 caixas e meia": a meia vai para a quantidade
    const n = lista.length;
    if (n >= 4 && lista[n - 2] === 'e' && lista[n - 1] === '0.5' && comoNumero(lista[n - 4]) !== null && ehQtd(lista[n - 3])) {
        lista = [...lista.slice(0, n - 4), String(comoNumero(lista[n - 4]) + 0.5), lista[n - 3]];
    }
    if (DE.has(lista[0]) && comoNumero(lista[1]) !== null) lista = lista.slice(1); // "de 5 papel toalhas"
    let quantidade = null;
    let modo = null;
    let unidade = null;
    const rotulo = lista.findIndex((palavra) => QTD_ROTULO.has(palavra));
    if (rotulo >= 0 && rotulo + 1 < lista.length && comoNumero(lista[rotulo + 1]) !== null) {
        quantidade = comoNumero(lista[rotulo + 1]);
        lista.splice(rotulo, 2);
    } else if (lista.length >= 3 && comoNumero(lista[0]) !== null && ehQtd(lista[1])) {
        quantidade = comoNumero(lista[0]);
        modo = QTD_EMBALAGEM.has(lista[1]) ? 'embalagem' : 'base';
        unidade = lista[1];
        lista = lista.slice(DE.has(lista[2]) ? 3 : 2);
    } else if (lista.length >= 2 && comoNumero(lista[lista.length - 2]) !== null && ehQtd(lista[lista.length - 1])) {
        quantidade = comoNumero(lista[lista.length - 2]);
        unidade = lista[lista.length - 1];
        modo = QTD_EMBALAGEM.has(unidade) ? 'embalagem' : 'base';
        lista = lista.slice(0, -2);
    } else if (lista.length >= 2 && comoNumero(lista[0]) !== null && !/^0\d/.test(lista[0]) && comoNumero(lista[1]) === null
        && !temChave(UNIDADES, lista[1]) && lista[1] !== 'x') {
        // "5 papel toalhas": número no começo, sem unidade, antes do material (o "20 amperes" e o "50 x 25" são do material)
        quantidade = comoNumero(lista[0]);
        lista = lista.slice(1);
    }
    return { acao, material: lista.join(' ').trim(), quantidade, modo, unidade, pessoa, local };
}

// Custódia (2.6.2): linhas de /api/mobile/custodia ({ codigo, descricao, nome, matricula, … }) que combinam com o
// texto dito ou digitado: pela ferramenta ("furadeira", "trena") ou pela pessoa ("Gláucia", "da Gláucia").
export function filtrarCustodia(linhas, texto) {
    const lista = Array.isArray(linhas) ? linhas : [];
    if (!String(texto || '').trim()) return lista;
    const ferramentas = [];
    const vistas = new Set();
    lista.forEach((linha) => {
        if (vistas.has(linha.codigo)) return;
        vistas.add(linha.codigo);
        ferramentas.push({ codigo_barras: linha.codigo, descricao: linha.descricao, quantidade: 1 });
    });
    const codigos = new Set(buscarComNota(ferramentas, texto, { limite: 500 }).map((achado) => achado.item.codigo_barras));
    const pessoas = [];
    const matriculas = new Set();
    lista.forEach((linha) => {
        if (matriculas.has(linha.matricula)) return;
        matriculas.add(linha.matricula);
        pessoas.push({ nome: linha.nome, matricula: linha.matricula });
    });
    const deQuem = new Set(acharPessoa(pessoas, texto).candidatos.map((pessoa) => pessoa.matricula));
    return lista.filter((linha) => codigos.has(linha.codigo) || deQuem.has(linha.matricula));
}

// Itens da base do celular que combinam com o texto, do mais para o menos parecido.
export function buscarMaterial(itens, texto, opcoes = {}) {
    return buscarComNota(itens, texto, opcoes).map((achado) => achado.item);
}

// O 1º achado está claramente à frente (uma palavra inteira a mais que o 2º) ou é o único: o comando falado pode
// abrir direto, sem a pessoa escolher na lista.
export function vencedorClaro(achados) {
    if (!Array.isArray(achados) || !achados.length) return null;
    if (achados.length === 1 || achados[0].nota >= achados[1].nota + 3) return achados[0].item;
    return null;
}

// [{ item, nota }], do mais para o menos parecido.
export function buscarComNota(itens, texto, { limite = 60 } = {}) {
    // A consulta entende números por extenso mesmo digitada ("dois e meio"); o item é lido como está escrito.
    const consulta = termos(texto, { falado: true });
    const soDigitos = semAcento(texto).replace(/[\s.-]/g, '');
    const digitos = /^\d{3,}$/.test(soDigitos) ? soDigitos : ''; // "0265" e "0 2 6 5" (sem os espaços)
    if (!consulta.palavras.length && !consulta.numeros.length && !digitos) return [];
    const achados = [];
    for (const item of Array.isArray(itens) ? itens : []) {
        const nota = pontuar(item, consulta, digitos);
        if (nota > 0) achados.push({ item, nota, temSaldo: saldoDe(item) > 0 });
    }
    achados.sort((a, b) => (b.nota - a.nota)
        || (Number(b.temSaldo) - Number(a.temSaldo))
        || String(a.item?.descricao ?? '').localeCompare(String(b.item?.descricao ?? ''), 'pt-BR'));
    return achados.slice(0, limite).map(({ item, nota }) => ({ item, nota }));
}
