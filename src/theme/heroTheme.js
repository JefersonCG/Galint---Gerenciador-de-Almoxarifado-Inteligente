// Cores do app. Desde a 2.2.0 elas podem vir da tela Aparência do site (Configurações →
// Aparência, no molde da skin do Pipocas): o App.js aplica a paleta guardada ANTES de carregar as
// telas, porque cada tela monta seus estilos (StyleSheet.create) uma vez, ao ser carregada. Uma
// mudança feita no site vale na próxima vez que o app abrir.
import AsyncStorage from '@react-native-async-storage/async-storage';

const DEFAULT_PALETTE = {
    bg: '#06101b',
    bgAlt: '#0b1728',
    hero: '#0d1b31',
    heroAlt: '#123055',
    panel: '#0f1b31',
    panelAlt: '#14253f',
    panelSoft: '#172c4b',
    border: 'rgba(148, 163, 184, 0.18)',
    borderStrong: 'rgba(103, 232, 249, 0.28)',
    text: '#f8fbff',
    textMuted: '#9db0ca',
    textSoft: '#d8e4f4',
    primary: '#67e8f9',
    primaryStrong: '#22d3ee',
    accent: '#34d399',
    warning: '#fbbf24',
    danger: '#fb7185',
    success: '#22c55e',
};

// Só estas partes mudam com a Aparência; textos e cores de estado (alerta, erro) ficam fixos.
const THEMEABLE = ['bg', 'bgAlt', 'hero', 'heroAlt', 'panel', 'panelAlt', 'panelSoft', 'primary', 'primaryStrong', 'borderStrong'];
const STORAGE_KEY = 'galint_tema_app';
const COLOR = /^(#[0-9a-f]{6}|rgba?\([\d\s.,]+\))$/i;

export const heroPalette = { ...DEFAULT_PALETTE };

function applyPalette(app) {
    Object.assign(heroPalette, DEFAULT_PALETTE);
    if (!app || typeof app !== 'object') return;
    THEMEABLE.forEach((key) => {
        const value = String(app[key] || '').trim();
        if (COLOR.test(value)) heroPalette[key] = value;
    });
}

// Tema guardado da última vez (vale já nesta abertura).
export async function loadSavedTheme() {
    try {
        const saved = JSON.parse((await AsyncStorage.getItem(STORAGE_KEY)) || 'null');
        applyPalette(saved?.personalizada ? saved.app : null);
        return saved;
    } catch (error) {
        applyPalette(null);
        return null;
    }
}

// Tema recebido do servidor (/api/mobile/tema). applyNow = true só enquanto as telas ainda não
// foram carregadas; depois disso ele fica guardado para a próxima abertura.
export async function saveServerTheme(tema, { applyNow = false } = {}) {
    if (!tema || typeof tema !== 'object') return;
    try {
        await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify({ personalizada: Boolean(tema.personalizada), app: tema.app || null }));
    } catch (error) {
        // sem espaço ou sem acesso: fica o tema atual
    }
    if (applyNow) applyPalette(tema.personalizada ? tema.app : null);
}

export const heroShadow = {
    shadowColor: '#020617',
    shadowOffset: { width: 0, height: 14 },
    shadowOpacity: 0.28,
    shadowRadius: 24,
    elevation: 10,
};

export const heroSoftShadow = {
    shadowColor: '#020617',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.18,
    shadowRadius: 18,
    elevation: 6,
};
