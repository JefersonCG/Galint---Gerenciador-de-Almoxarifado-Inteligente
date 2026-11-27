// Lista de pessoas (/api/mobile/usuarios) guardada na memória para os comandos de voz (2.6.2). Em "retirada por
// Gláucia de 5 papel toalhas" o nome sai certo mesmo sem ela; em "… para Gláucia" no fim da frase, ela diz que
// "Gláucia" é uma pessoa e não parte do material. Sem rede (ou demorando mais de 4 s), volta vazia e o comando segue.
import ApiService from './api';

let guardada = null;

export async function pessoasParaVoz() {
    if (guardada?.length) return guardada;
    const lista = await Promise.race([
        ApiService.getUsuarios().catch(() => []),
        new Promise((resolve) => setTimeout(() => resolve([]), 4000)),
    ]);
    if (Array.isArray(lista) && lista.length) guardada = lista;
    return Array.isArray(lista) ? lista : [];
}
