// Código lido que não existe no GALINT (2.2.6, 23/11/2026): só oferece cadastro para o que parece
// código de barras. Um QR com endereço ou uma palavra digitada na busca não viram item.
export function isRegistrableCode(code) {
    const text = String(code || '').trim();
    return /^\S{3,64}$/.test(text) && /\d/.test(text) && !text.includes('://');
}
