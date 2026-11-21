// Base local do app (desde a 2.2.0): o estoque inteiro guardado no celular, para a busca e a
// leitura de código não esperarem o servidor. É só leitura: toda gravação (retirada, devolução,
// contagem) vai direto ao servidor, e a sincronização (dbSync.js) traz a mudança de volta.
//
// Até a 2.1.1 a base ficava em offlineDb.js e chamava openDatabase(), que o expo-sqlite 15 já
// não tinha. O erro era engolido, a base nunca abria, toda gravação local era descartada e a
// "fila offline" perdia retiradas que o app dizia ter registrado. Aqui se usa a API assíncrona
// (openDatabaseAsync), e um erro ao abrir a base aparece no log em vez de sumir.
import * as SQLite from 'expo-sqlite';

const DB_NAME = 'galint_base.db';
let dbPromise = null;

function normalizeText(value) {
    return String(value ?? '')
        .normalize('NFD')
        .replace(/[̀-ͯ]/g, '')
        .toLowerCase()
        .trim();
}

function itemCode(item) {
    return String(item?.codigo_barras ?? item?.codigo ?? item?.id ?? '').trim();
}

function searchKey(item) {
    return normalizeText([
        item?.descricao,
        item?.nome,
        itemCode(item),
        item?.categoria,
        item?.marca,
        item?.localizacao,
    ].filter(Boolean).join(' '));
}

async function openDb() {
    if (!dbPromise) {
        dbPromise = (async () => {
            const db = await SQLite.openDatabaseAsync(DB_NAME);
            await db.execAsync(`
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS items (
                    codigo TEXT PRIMARY KEY NOT NULL,
                    descricao TEXT,
                    busca TEXT,
                    dados TEXT NOT NULL,
                    atualizado_em INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_items_descricao ON items(descricao);
                CREATE TABLE IF NOT EXISTS meta (
                    chave TEXT PRIMARY KEY NOT NULL,
                    valor TEXT
                );
            `);
            return db;
        })().catch((error) => {
            dbPromise = null;
            throw error;
        });
    }
    return dbPromise;
}

function hydrate(row) {
    if (!row?.dados) return null;
    try {
        return JSON.parse(row.dados);
    } catch (error) {
        return null;
    }
}

async function writeItems(db, items) {
    const statement = await db.prepareAsync(
        'INSERT OR REPLACE INTO items (codigo, descricao, busca, dados, atualizado_em) VALUES (?, ?, ?, ?, ?)'
    );
    const now = Date.now();
    let written = 0;
    try {
        for (const item of items) {
            const codigo = itemCode(item);
            if (!codigo) continue;
            await statement.executeAsync([codigo, item?.descricao ?? item?.nome ?? null, searchKey(item), JSON.stringify(item), now]);
            written += 1;
        }
    } finally {
        await statement.finalizeAsync();
    }
    return written;
}

export async function initLocalDb() {
    await openDb();
}

// Mudanças que vieram do servidor: grava (ou substitui) só esses itens.
export async function upsertItems(items = []) {
    if (!Array.isArray(items) || items.length === 0) return 0;
    const db = await openDb();
    let written = 0;
    await db.withExclusiveTransactionAsync(async (txn) => {
        written = await writeItems(txn, items);
    });
    return written;
}

export async function upsertItem(item) {
    return upsertItems(item ? [item] : []);
}

// Lista completa do servidor: troca a base inteira de uma vez (itens apagados no site somem).
export async function replaceAllItems(items = []) {
    const db = await openDb();
    let written = 0;
    await db.withExclusiveTransactionAsync(async (txn) => {
        await txn.execAsync('DELETE FROM items');
        written = await writeItems(txn, Array.isArray(items) ? items : []);
    });
    return written;
}

// Mesma limpeza do servidor (_barcode_lookup_candidates): prefixo do leitor (]E0), espaços,
// só dígitos e a troca entre UPC-A (12) e EAN-13 com zero à esquerda.
export function barcodeCandidates(value) {
    const raw = String(value ?? '').trim();
    if (!raw) return [];
    const out = [];
    const add = (candidate) => {
        const normalized = String(candidate ?? '').trim();
        if (normalized && !out.includes(normalized)) out.push(normalized);
    };
    const compact = raw.replace(/\s+/g, '');
    add(raw);
    add(compact);
    if (compact.startsWith(']') && compact.length > 3) add(compact.slice(3));
    const digits = compact.replace(/\D+/g, '');
    add(digits);
    if (digits.length === 13 && digits.startsWith('0')) add(digits.slice(1));
    if (digits.length === 12) add(`0${digits}`);
    return out;
}

export async function getItemByCodigo(codigo) {
    const candidates = barcodeCandidates(codigo);
    if (candidates.length === 0) return null;
    const db = await openDb();
    for (const candidate of candidates) {
        const row = await db.getFirstAsync('SELECT dados FROM items WHERE codigo = ?', [candidate]);
        if (row) return hydrate(row);
    }
    for (const candidate of candidates) {
        const row = await db.getFirstAsync('SELECT dados FROM items WHERE codigo = ? COLLATE NOCASE', [candidate]);
        if (row) return hydrate(row);
    }
    return null;
}

// Busca por nome, código, categoria, marca ou local, sem acento e sem diferença de maiúsculas.
// Várias palavras: o item precisa ter todas ("luva latex" acha "LUVA LÁTEX G").
export async function searchItems(query = '', limit = 0) {
    const db = await openDb();
    const terms = normalizeText(query).split(/\s+/).filter(Boolean);
    const where = terms.map(() => 'busca LIKE ?').join(' AND ');
    const sql = `SELECT dados FROM items${where ? ` WHERE ${where}` : ''} ORDER BY descricao ASC${limit > 0 ? ` LIMIT ${Math.floor(limit)}` : ''}`;
    const rows = await db.getAllAsync(sql, terms.map((term) => `%${term}%`));
    return rows.map(hydrate).filter(Boolean);
}

export async function countItems() {
    const db = await openDb();
    const row = await db.getFirstAsync('SELECT COUNT(*) AS total FROM items');
    return Number(row?.total || 0);
}

export async function getMeta(chave) {
    const db = await openDb();
    const row = await db.getFirstAsync('SELECT valor FROM meta WHERE chave = ?', [chave]);
    return row ? row.valor : null;
}

export async function setMeta(chave, valor) {
    const db = await openDb();
    await db.runAsync('INSERT OR REPLACE INTO meta (chave, valor) VALUES (?, ?)', [chave, valor == null ? null : String(valor)]);
}

// Trocou de servidor: a base do outro servidor não vale aqui.
export async function clearLocalDb() {
    const db = await openDb();
    await db.execAsync('DELETE FROM items; DELETE FROM meta;');
}
