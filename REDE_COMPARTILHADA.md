# Rede Compartilhada

A **Rede Galint** é um painel público minimalista que expõe os principais indicadores do almoxarifado sem exigir autenticação. Ideal para TVs, totens ou dashboards que precisam acompanhar o estoque.

## Como funciona

1. **Token seguro**: defina a variável de ambiente `GALINT_DASHBOARD_TOKEN` com um valor forte (por exemplo, `GALINT_DASHBOARD_TOKEN=galint#rede2025`). Esse token é usado como parte da URL pública e impede acessos não autorizados.
2. **Reinicie o servidor** após alterar o token, pois o valor é lido na inicialização e integrado à rota pública.
3. **Gere o link de compartilhamento**: abra a aba **Configurações** (`/configuracoes`) logado como administrador, copie o link exibido no card “Rede Galint” (`/rede-galint/<token>`) e leve-o para o dispositivo desejado.
4. **Visualização apenas do dashboard**: a rota `/rede-galint/<token>` renderiza apenas o conteúdo central do dashboard (sem menu lateral), o que facilita a exibição em monitores dedicados.
5. **Distribuição controlada**: quem tiver o link poderá acessar a tela pública, portanto mantenha o token restrito e gere um novo sempre que houver suspeita de vazamento.

## Dicas operacionais

- Combine o compartilhamento com automações que abrem a URL em televisores ou totens.
- Qualquer navegador moderno pode exibir o painel; nenhuma autenticação é solicitada.
- Sempre que trocar o token, reinicie o serviço Flask e distribua o novo endereço.

## Roteiro rápido

| Ação                        | Comando / rota                        |
|-----------------------------|----------------------------------------|
| Definir token (PowerShell)  | `$env:GALINT_DASHBOARD_TOKEN = "nova-chave"` |
| Reiniciar o servidor Flask  | `python app.py` ou `run_app.ps1`     |
| Monitorar uso do link       | verifique os logs de acesso do Flask   |
| Copiar o link público       | `/rede-galint/<token>` (obtido em `/configuracoes`) |

Assim que o token estiver ativo, a mesma URL pode ser usada em telas digitais sem expor as demais áreas do GALINT Flask.