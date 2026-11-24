// Texto sempre em MAIÚSCULAS (2.2.7). Pedido do usuário em 24/11/2026: "sempre que escrever, o sistema
// lança as letras em maiúsculo", no app e no site. Todas as telas importam este campo no lugar do
// TextInput do React Native (import TextInput from '../components/UpperTextInput'), então o que se
// digita ou cola já chega à tela e ao servidor em maiúsculas, e o teclado abre em CAPS.
//
// Ficam como digitados só os campos em que a caixa importa: senha (secureTextEntry), link (teclado de
// URL, ex.: foto do item), e-mail e os marcados com keepCase (usuário e senha do login, que continuam
// iguais mesmo com "mostrar senha" ligado).
import React, { forwardRef, useCallback } from 'react';
import { TextInput as NativeTextInput } from 'react-native';

const KEEP_CASE_KEYBOARDS = new Set(['url', 'email-address', 'visible-password']);

export function keepsCase({ keepCase, secureTextEntry, keyboardType } = {}) {
    return Boolean(keepCase || secureTextEntry || KEEP_CASE_KEYBOARDS.has(keyboardType));
}

const UpperTextInput = forwardRef(function UpperTextInput({ keepCase, onChangeText, autoCapitalize, ...props }, ref) {
    const keep = keepsCase({ keepCase, secureTextEntry: props.secureTextEntry, keyboardType: props.keyboardType });
    const handleChangeText = useCallback(
        (text) => onChangeText(keep ? text : String(text ?? '').toUpperCase()),
        [keep, onChangeText],
    );
    return (
        <NativeTextInput
            ref={ref}
            {...props}
            autoCapitalize={keep ? autoCapitalize : 'characters'}
            onChangeText={onChangeText ? handleChangeText : undefined}
        />
    );
});

export default UpperTextInput;
