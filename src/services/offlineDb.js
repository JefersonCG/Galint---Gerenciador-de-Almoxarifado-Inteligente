let SQLiteModule = null;
let db = null;
let initialized = false;
let available = true;

function isDuplicateColumnError(error) {
    const message = String(error?.message || error || '').toLowerCase();
    return message.includes('duplicate column name');
}

async function ensureItemColumn(columnName, columnType) {
    try {
        await runSql(`ALTER TABLE items ADD COLUMN ${columnName} ${columnType}`);
    } catch (error) {
        if (!isDuplicateColumnError(error)) {
            throw error;
        }
    }
}

function toDbNumber(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? Number(numeric.toFixed(6)) : null;
}

function toDbText(value) {
    if (value === undefined || value === null) return null;
    const normalized = String(value).trim();
    return normalized || null;
}

function toDbJson(value) {
    if (value === undefined || value === null) return null;
    try {
        return JSON.stringify(value);
    } catch (error) {
        return null;
    }
}

function parseMaybeJson(value) {
    if (!value || typeof value !== 'string') return null;
    try {
        return JSON.parse(value);
    } catch (error) {
        return null;
    }
}

function hydrateItemRow(row) {
    if (!row) return null;
    return {
        ...row,
        quantidade: toDbNumber(row.quantidade),
        estoque_minimo: toDbNumber(row.estoque_minimo),
        unidades_por_embalagem: toDbNumber(row.unidades_por_embalagem),
        estoque_embalagens: toDbNumber(row.estoque_embalagens),
        estoque_unidades_soltas: toDbNumber(row.estoque_unidades_soltas),
        pre_cadastro_pendente: row.pre_cadastro_pendente === 1 || row.pre_cadastro_pendente === true,
        estoque_formatado: parseMaybeJson(row.estoque_formatado),
    };
}

function runSql(sql, params = []) {
    if (!available || !db) {
        return Promise.resolve({ rows: { _array: [] } });
    }
    return new Promise((resolve, reject) => {
        db.transaction(
            (tx) => {
                tx.executeSql(
                    sql,
                    params,
                    (_, result) => resolve(result),
                    (_, error) => {
                        reject(error);
                        return false;
                    }
                );
            },
            (error) => reject(error)
        );
    });
}

export async function initOfflineDb() {
    if (initialized) return;
    try {
        SQLiteModule = require('expo-sqlite');
        db = SQLiteModule.openDatabase('galint_offline.db');
    } catch (error) {
        available = false;
        initialized = true;
        return;
    }
    await runSql(
        `CREATE TABLE IF NOT EXISTS items (
            id INTEGER,
            codigo_barras TEXT,
            descricao TEXT,
            categoria TEXT,
            localizacao TEXT,
            marca TEXT,
            quantidade REAL,
            unidade TEXT,
            saldo_display TEXT,
            estoque_minimo REAL,
            tipo_embalagem_novo TEXT,
            unidades_por_embalagem REAL,
            estoque_embalagens REAL,
            estoque_unidades_soltas REAL,
            estoque_formatado TEXT,
            pre_cadastro_pendente INTEGER,
            foto_path TEXT,
            foto_url TEXT,
            barcode_image_path TEXT,
            updated_at INTEGER,
            codigo_key TEXT PRIMARY KEY
        )`
    );

    await ensureItemColumn('saldo_display', 'TEXT');
    await ensureItemColumn('estoque_minimo', 'REAL');
    await ensureItemColumn('tipo_embalagem_novo', 'TEXT');
    await ensureItemColumn('unidades_por_embalagem', 'REAL');
    await ensureItemColumn('estoque_embalagens', 'REAL');
    await ensureItemColumn('estoque_unidades_soltas', 'REAL');
    await ensureItemColumn('estoque_formatado', 'TEXT');
    await ensureItemColumn('pre_cadastro_pendente', 'INTEGER');
    await ensureItemColumn('foto_path', 'TEXT');
    await ensureItemColumn('foto_url', 'TEXT');
    await ensureItemColumn('barcode_image_path', 'TEXT');

    await runSql(
        `CREATE TABLE IF NOT EXISTS pending_ops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            status TEXT NOT NULL,
            retries INTEGER NOT NULL
        )`
    );

    initialized = true;
}

function resolveCodigoKey(item) {
    const codigo = (item?.codigo_barras || item?.codigo || item?.id || '').toString().trim();
    return codigo || null;
}

export async function upsertItem(item) {
    if (!item) return;
    const codigoKey = resolveCodigoKey(item);
    if (!codigoKey) return;
    await runSql(
        `INSERT OR REPLACE INTO items
            (
                id,
                codigo_barras,
                descricao,
                categoria,
                localizacao,
                marca,
                quantidade,
                unidade,
                saldo_display,
                estoque_minimo,
                tipo_embalagem_novo,
                unidades_por_embalagem,
                estoque_embalagens,
                estoque_unidades_soltas,
                estoque_formatado,
                pre_cadastro_pendente,
                foto_path,
                foto_url,
                barcode_image_path,
                updated_at,
                codigo_key
            )
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
        , [
            item.id ?? null,
            item.codigo_barras ?? item.codigo ?? null,
            item.descricao ?? item.nome ?? null,
            item.categoria ?? null,
            item.localizacao ?? null,
            item.marca ?? null,
            toDbNumber(item.quantidade),
            item.unidade ?? null,
            toDbText(item.saldo_display),
            toDbNumber(item.estoque_minimo),
            toDbText(item.tipo_embalagem_novo),
            toDbNumber(item.unidades_por_embalagem),
            toDbNumber(item.estoque_embalagens),
            toDbNumber(item.estoque_unidades_soltas),
            toDbJson(item.estoque_formatado),
            item.pre_cadastro_pendente ? 1 : 0,
            toDbText(item.foto_path),
            toDbText(item.foto_url),
            toDbText(item.barcode_image_path),
            Date.now(),
            codigoKey,
        ]
    );
}

export async function upsertItems(items = []) {
    if (!Array.isArray(items)) return;
    for (const item of items) {
        await upsertItem(item);
    }
}

export async function getItemByCodigo(codigo) {
    const codigoKey = String(codigo || '').trim();
    if (!codigoKey) return null;
    const result = await runSql(
        `SELECT * FROM items WHERE codigo_key = ? OR codigo_barras = ? OR id = ? LIMIT 1`,
        [codigoKey, codigoKey, codigoKey]
    );
    const rows = result?.rows?._array || [];
    return rows.length > 0 ? hydrateItemRow(rows[0]) : null;
}

export async function searchItems(query = '') {
    const like = `%${String(query || '').trim()}%`;
    const result = await runSql(
        `SELECT * FROM items
         WHERE descricao LIKE ? OR categoria LIKE ? OR codigo_barras LIKE ? OR marca LIKE ? OR localizacao LIKE ?
         ORDER BY descricao ASC`,
        [like, like, like, like, like]
    );
    return (result?.rows?._array || []).map((row) => hydrateItemRow(row));
}

export async function adjustLocalSaldo(codigo, delta) {
    const item = await getItemByCodigo(codigo);
    if (!item) return;
    const current = Number.isFinite(Number(item.quantidade)) ? Number(item.quantidade) : 0;
    const deltaNum = Number.isFinite(Number(delta)) ? Number(delta) : 0;
    const novo = Number((current + deltaNum).toFixed(6));
    await runSql(
        `UPDATE items SET quantidade = ?, updated_at = ? WHERE codigo_key = ? OR codigo_barras = ? OR id = ?`,
        [novo, Date.now(), String(codigo), String(codigo), String(codigo)]
    );
}

export async function addPendingOp(type, payload) {
    await runSql(
        `INSERT INTO pending_ops (type, payload, created_at, status, retries)
         VALUES (?, ?, ?, ?, ?)`
        , [
            type,
            JSON.stringify(payload || {}),
            Date.now(),
            'pending',
            0,
        ]
    );
}

export async function listPendingOps(limit = 50) {
    const result = await runSql(
        `SELECT * FROM pending_ops WHERE status IN ('pending', 'failed') ORDER BY created_at ASC LIMIT ?`,
        [limit]
    );
    return result?.rows?._array || [];
}

export async function markPendingOpSynced(id) {
    await runSql(`UPDATE pending_ops SET status = 'synced' WHERE id = ?`, [id]);
}

export async function markPendingOpFailed(id) {
    await runSql(`UPDATE pending_ops SET status = 'failed' WHERE id = ?`, [id]);
}

export async function incrementPendingRetry(id) {
    await runSql(`UPDATE pending_ops SET retries = retries + 1 WHERE id = ?`, [id]);
}

// ============ ONLINE SNAPSHOT (CACHE) ============

export async function ensureSnapshotTable() {
    await runSql(
        `CREATE TABLE IF NOT EXISTS online_snapshot (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            total_itens INTEGER NOT NULL,
            total_quantidade INTEGER NOT NULL,
            total_categorias INTEGER NOT NULL,
            timestamp INTEGER NOT NULL
        )`
    );
}

export async function saveOnlineSnapshot(totalItens, totalQuantidade, totalCategorias) {
    await ensureSnapshotTable();
    await runSql(
        `INSERT OR REPLACE INTO online_snapshot (id, total_itens, total_quantidade, total_categorias, timestamp)
         VALUES (1, ?, ?, ?, ?)`,
        [totalItens, totalQuantidade, totalCategorias, Date.now()]
    );
}

export async function getOnlineSnapshot() {
    await ensureSnapshotTable();
    const result = await runSql(`SELECT * FROM online_snapshot WHERE id = 1`);
    const rows = result?.rows?._array || [];
    return rows.length > 0 ? rows[0] : null;
}

export async function getOfflineDelta() {
    const ops = await listPendingOps(999);
    let entradas = 0;
    let retiradas = 0;
    
    for (const op of ops) {
        try {
            const payload = JSON.parse(op.payload || '{}');
            const quantidade = Math.abs(Number(payload.quantidade) || 0);
            
            if (op.type === 'entrada' || op.type === 'entrada_lote') {
                entradas += quantidade;
            } else if (op.type === 'retirada' || op.type === 'retirada_ferramenta' || op.type === 'retirada_multipla') {
                retiradas += quantidade;
            }
        } catch (e) {
            // ignora erros de parse
        }
    }
    
    return { entradas, retiradas };
}

export async function clearOfflineDelta() {
    // Marca todas pendentes como synced
    await runSql(`DELETE FROM pending_ops WHERE status IN ('pending', 'synced')`);
}
