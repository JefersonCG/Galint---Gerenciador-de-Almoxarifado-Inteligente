// Janela de voz do Google (módulo nativo GalintVoz.ouvir), usada pelo 🎤 das telas e da câmera.
// 2.7.2: a escuta própria da 2.7.1 (janela "Ouvindo…" do app) foi desfeita. Pedido do usuário em 27/11/2026: "esse
// modal do microfone está horrível, muito grande, exagerado, não está ouvindo com facilidade, tem atraso no ouvir,
// está um modal muito baixo; deixe o que era pelo Google".
import { Alert, NativeModules } from 'react-native';

// A frase mais provável, ou '' (cancelou, não entendeu ou o celular não tem o reconhecimento de voz).
export async function ouvirVoz() {
    const voz = NativeModules?.GalintVoz;
    if (!voz?.ouvir) {
        Alert.alert('Voz', 'Atualize o app para falar o material.');
        return '';
    }
    try {
        const frases = await voz.ouvir('Fale o material ou o código');
        return Array.isArray(frases) ? String(frases[0] || '').trim() : '';
    } catch (erro) {
        if (erro?.code === 'sem_voz') Alert.alert('Voz', erro.message || 'Este celular não tem o reconhecimento de voz.');
        return '';
    }
}
