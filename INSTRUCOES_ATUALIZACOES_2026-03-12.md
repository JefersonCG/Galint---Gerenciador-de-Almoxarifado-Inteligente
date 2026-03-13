# Instrucoes - Atualizacoes de 12/03/2026

Este arquivo resume o que foi feito hoje e como usar cada parte.

## 1) Foto por URL (assistente de imagem)

### O que foi implementado
- Upload de foto por URL com compressao automatica.
- Endpoint estavel para evitar erro 404, inclusive com fallback no app.
- Modal para colar link direto da imagem.

### Como usar
1. Abra um item e clique na lupa ao lado de "Produto".
2. Cole o link direto da imagem (termina em .jpg, .png, .webp).
3. Clique em "Aplicar foto".

### Observacoes
- O sistema baixa, redimensiona e comprime a imagem automaticamente.
- Devolucao de 404 agora esta corrigida com rota fixa.

## 2) Dashboard Percentual Movimentos

### O que mudou
- Layout single-page, sem scroll global (100vh).
- KPIs no topo, sidebar 25% e painel principal 75%.
- Tabelas com estilo de monitoramento.
- Clique em KPI abre grafico placeholder no painel principal.

## 3) Sobre (pagina)

### O que mudou
- Texto simplificado e amigavel.
- Visual mais chamativo com cards, icones e destaques.
- Ajuda do Percentual Movimentos foi movida para um bloco especial no Sobre.

## 4) Menu Ferramentas

### O que mudou
- Criado menu expansivel "Ferramentas".
- Itens dentro: "Auditar Ferramentas" e "Em reparo...".

## 5) Painel Mobile (desativado)

### O que mudou
- Link removido do menu quando a feature esta desligada.
- Rotas retornam 404 quando a feature esta desativada.

### Como reativar
Defina a variavel de ambiente:

GALINT_FEATURE_MOBILE_PANEL=true

## 6) Assistente Virtual (toast)

### O que foi implementado
- Toggle no sidebar para ativar/desativar.
- Toast aparece apos 2 erros em 2 minutos.
- Preferencia salva no navegador por usuario.

---

## Rotas importantes criadas/ajustadas
- POST /api/itens/foto/url
- POST /itens/foto/url (fallback no app)

## Observacoes finais
Se precisar reativar qualquer parte (painel mobile, assistente ou ajuda), basta ajustar o config e/ou o menu.
