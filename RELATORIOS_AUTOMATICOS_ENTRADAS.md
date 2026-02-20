# 📊 Sistema de Relatórios Automáticos de Entradas

## Visão Geral

O sistema GALINT agora possui um recurso de geração automática de relatórios de entradas. **A cada 1000 registros de entrada**, o sistema automaticamente:

1. ✅ Gera um PDF consolidado com todas as entradas do ciclo
2. 📱 Envia o PDF automaticamente para todos os administradores via Telegram
3. 🔄 Reinicia o contador para o próximo ciclo
4. 🔒 Funciona de forma totalmente automática e silenciosa (sem intervenção manual)

## Como Funciona

### Trigger Automático

O sistema é acionado **automaticamente** sempre que uma nova entrada é registrada no sistema através da função `registrar_entrada()` em `inventory_service.py`.

### Ciclos de 1000 Entradas

- **Ciclo 1**: Entradas 1 a 1000
- **Ciclo 2**: Entradas 1001 a 2000
- **Ciclo 3**: Entradas 2001 a 3000
- E assim por diante...

### Nome do Arquivo PDF

Os PDFs são gerados com o formato:
```
Registros_de_Entradas_DDMMAAAA_cicloX.pdf
```

Exemplo: `Registros_de_Entradas_04022026_ciclo1.pdf`

## Estrutura do PDF

O PDF gerado contém:

### Cabeçalho
- Título: "REGISTROS DE ENTRADAS - CICLO X"
- Informações do ciclo (range de IDs, total de registros, data de geração)

### Tabela de Dados
Cada entrada inclui:
- **ID**: Número único da entrada
- **Data/Hora**: Timestamp do registro
- **Código**: Código do item (EAN/interno)
- **Descrição**: Nome do produto
- **Qtd**: Quantidade registrada
- **Un.**: Unidade de medida
- **NF**: Nota fiscal
- **Usuário**: Nome do responsável pelo registro
- **Categoria**: Categoria do item

### Rodapé
- Indicação de relatório automático
- Número do ciclo

## Localização dos Arquivos

Os PDFs são salvos em:
```
instance/reports/entradas_automaticas/
```

### Arquivo de Controle
Um arquivo `.ultimo_ciclo.txt` armazena o número do último ciclo gerado, evitando duplicações.

## Envio via Telegram

### Destinatários
O PDF é enviado automaticamente para **todos os administradores** que possuem:
- Telegram vinculado ao sistema
- Notificações habilitadas

### Formato da Mensagem
```
📊 Relatório Automático de Entradas

🔢 Ciclo: 1
📦 Entradas: 1 a 1000
📅 Gerado em: 04/02/2026 às 14:30

Este é um relatório automático gerado a cada 1000 entradas.
```

## Monitoramento no Dashboard

O dashboard exibe informações em tempo real sobre o progresso:

### Card "Registros de Entradas"
- Total histórico de entradas
- Progresso visual (barra) para o próximo relatório
- Número do próximo ciclo
- Quantidade de entradas faltantes
- Percentual de conclusão

Exemplo:
```
Registros de Entradas
103
Total histórico de entradas registradas

Próximo relatório automático (PDF): Ciclo 1
[=============>        ] 10% completo
Faltam 897 entradas
```

## Scripts de Teste

### 1. Verificar Status
```bash
python test_entrada_report.py
```

Mostra:
- Total de entradas no sistema
- Último ciclo gerado
- Próximo ciclo
- Quantas entradas faltam
- Se um relatório deve ser gerado

### 2. Forçar Geração de Teste
```bash
python gerar_relatorio_teste.py
```

Permite:
- Gerar um PDF de teste com as entradas atuais
- Enviar para o Telegram para validação
- Útil para desenvolvimento e testes

## Arquitetura Técnica

### Serviço Principal
**Arquivo**: `galint_flask/services/entrada_report_service.py`

**Classe**: `EntradaReportService`

**Métodos principais**:
- `get_total_entradas()`: Retorna total de entradas
- `get_ultimo_ciclo_gerado()`: Verifica último ciclo
- `check_e_gerar_relatorio()`: Verifica e gera se necessário
- `gerar_pdf_ciclo()`: Cria o PDF
- `enviar_para_telegram()`: Envia aos administradores

### Integração
O serviço é chamado automaticamente em:
```python
# galint_flask/services/inventory.py
def _registrar_movimento(self, payload, *, is_entrada: bool):
    # ... código de registro ...
    
    # Verificar e gerar relatório automático a cada 1000 entradas
    if is_entrada:
        try:
            from ..services.entrada_report_service import entrada_report_service
            entrada_report_service.check_e_gerar_relatorio()
        except Exception as e:
            logger.warning(f"Erro ao verificar relatório automático: {e}")
```

### Bibliotecas Utilizadas
- **ReportLab**: Geração de PDFs
- **SQLAlchemy**: Consultas ao banco de dados
- **TelegramService**: Envio de documentos

## Características Importantes

### ✅ Não Bloqueante
- A geração do PDF e envio não bloqueiam o registro de entradas
- Se houver erro, a operação continua normalmente
- Logs são registrados para debug

### ✅ Silencioso
- Funciona em background
- Não exibe popups ou alertas
- Não requer confirmação do usuário

### ✅ Resiliente
- Tratamento de erros em todas as etapas
- Estado persistido em arquivo
- Recuperação automática

### ✅ Performance
- Consultas otimizadas ao banco
- Processamento assíncrono via Telegram
- Mínimo impacto no sistema

## Logs

O sistema registra logs detalhados:

```python
logger.info(f"Check relatório: total={total}, último_ciclo={ultimo_ciclo}")
logger.info(f"Gerando relatório do ciclo {ciclo}")
logger.info(f"PDF gerado com sucesso: {filepath}")
logger.info(f"PDF enviado para {enviados} administradores")
```

## Troubleshooting

### PDF não está sendo gerado
1. Verificar se há 1000 entradas acumuladas
2. Executar `python test_entrada_report.py`
3. Verificar logs do sistema
4. Checar permissões da pasta `instance/reports/`

### PDF não é enviado no Telegram
1. Verificar se Telegram está habilitado
2. Confirmar que há administradores com Telegram vinculado
3. Verificar configurações de notificações
4. Testar com `python gerar_relatorio_teste.py`

### Resetar o contador
Para reiniciar do zero:
```bash
rm instance/reports/entradas_automaticas/.ultimo_ciclo.txt
```

## Personalização

### Alterar o Limite de Entradas
Edite em `entrada_report_service.py`:
```python
CONTADOR_CICLO = 1000  # Altere para o valor desejado
```

### Alterar Formato do Nome
Modifique em `gerar_pdf_ciclo()`:
```python
filename = f"Registros_de_Entradas_{data_geracao}_ciclo{ciclo}.pdf"
```

## Próximas Melhorias

- [ ] Adicionar opção de enviar para grupos específicos
- [ ] Permitir configurar o limite via interface web
- [ ] Adicionar gráficos estatísticos no PDF
- [ ] Exportar também em formato XLSX
- [ ] Histórico de relatórios na interface
- [ ] Notificação quando faltarem 100 entradas

## Suporte

Para dúvidas ou problemas, verifique:
1. Este documento
2. Scripts de teste
3. Logs do sistema
4. Código fonte em `galint_flask/services/entrada_report_service.py`
