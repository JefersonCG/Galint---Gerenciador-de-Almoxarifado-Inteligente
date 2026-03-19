# 3 Modelos de Formatação para Notificações Telegram

## Problema Atual
As notificações apresentam:
- ❌ Notação científica (0.03994e+08, 1.0598e+06)
- ❌ Números sem separadores de milhar (102000, 839800)
- ❌ Decimais desnecessários (.00)
- ❌ Informações confusas e repetitivas

---

## MODELO 1: Formatação Simples e Direta

### Exemplo PAPEL HIGIÊNICO
```
📦 Materiais de Limpeza
🧻 PAPEL HIGIÊNICO
Qtd: 1 unidades

📊 SALDO ATUAL
   📦 Caixas: 83.999 (cada caixa contém 6.000 un)
   📦 Saldo total (em unidades): 503.994.000 un
```

### Exemplo PAPEL TOALHA
```
📦 Materiais de Limpeza
🧻 PAPEL TOALHA INTERFOLHAS
Qtd: 5 unidades

📊 SALDO ATUAL
   📦 Pacotes: 102 (cada pacote contém 1.000 un)
   + Unidades soltas: 0 un
   📦 Saldo total (em unidades): 102.000 un
```

### Exemplo SACO LIXO 300 LITROS
```
📦 Materiais de Limpeza
🗑️ SACO LIXO 300 LITROS
Qtd: 1 unidades

📊 SALDO ATUAL
   📦 Pacotes: 10.598 (cada pacote contém 100 un)
   📦 Saldo total (em unidades): 1.059.800 un
```

### Exemplo SACO LIXO 200 LITROS
```
📦 Materiais de Limpeza
🗑️ SACO LIXO 200 LITROS
Qtd: 1 unidades

📊 SALDO ATUAL
   📦 Pacotes: 8.398 (cada pacote contém 100 un)
   📦 Saldo total (em unidades): 839.800 un
```

---

## MODELO 2: Formato Compacto com Ênfase em Números

### Exemplo PAPEL HIGIÊNICO
```
📦 Materiais de Limpeza
🧻 PAPEL HIGIÊNICO
Qtd: 1 unidades

📊 SALDO ATUAL
   📦 83.999 caixas × 6.000 un = 503.994.000 un total
```

### Exemplo PAPEL TOALHA
```
📦 Materiais de Limpeza
🧻 PAPEL TOALHA INTERFOLHAS
Qtd: 5 unidades

📊 SALDO ATUAL
   📦 102 pacotes × 1.000 un = 102.000 un total
```

### Exemplo SACO LIXO 300 LITROS
```
📦 Materiais de Limpeza
🗑️ SACO LIXO 300 LITROS
Qtd: 1 unidades

📊 SALDO ATUAL
   📦 10.598 pacotes × 100 un = 1.059.800 un total
```

### Exemplo SACO LIXO 200 LITROS
```
📦 Materiais de Limpeza
🗑️ SACO LIXO 200 LITROS
Qtd: 1 unidades

📊 SALDO ATUAL
   📦 8.398 pacotes × 100 un = 839.800 un total
```

---

## MODELO 3: Formato Hierárquico Detalhado (RECOMENDADO) ⭐

### Exemplo PAPEL HIGIÊNICO
```
📦 Materiais de Limpeza
🧻 PAPEL HIGIÊNICO
Qtd: 1 unidades

📊 SALDO ATUAL
   📦 Total de caixas: 83.999
      └─ Unidades por caixa: 6.000
   📊 Total geral: 503.994.000 unidades
```

### Exemplo PAPEL TOALHA
```
📦 Materiais de Limpeza
🧻 PAPEL TOALHA INTERFOLHAS
Qtd: 5 unidades

📊 SALDO ATUAL
   📦 Total de pacotes: 102
      └─ Unidades por pacote: 1.000
   📊 Total geral: 102.000 unidades
```

### Exemplo SACO LIXO 300 LITROS
```
📦 Materiais de Limpeza
🗑️ SACO LIXO 300 LITROS
Qtd: 1 unidades

📊 SALDO ATUAL
   📦 Total de pacotes: 10.598
      └─ Unidades por pacote: 100
   📊 Total geral: 1.059.800 unidades
```

### Exemplo SACO LIXO 200 LITROS
```
📦 Materiais de Limpeza
🗑️ SACO LIXO 200 LITROS
Qtd: 1 unidades

📊 SALDO ATUAL
   📦 Total de pacotes: 8.398
      └─ Unidades por pacote: 100
   📊 Total geral: 839.800 unidades
```

---

## Mudanças Técnicas Necessárias

### Nova Função de Formatação Numérica:
```python
def _fmt_number(value: float, decimals: int = 0) -> str:
    """
    Formata número com separador de milhar (ponto) e remove decimais desnecessários.
    
    Exemplos:
        1000 → "1.000"
        1000.5 → "1.000,5" (se decimals > 0)
        503994000 → "503.994.000"
    """
    try:
        value_f = float(value)
    except Exception:
        return "0"
    
    # Se é número inteiro ou decimals=0, retornar como inteiro formatado
    if decimals == 0 or abs(value_f - round(value_f)) < 1e-9:
        return f"{int(round(value_f)):,}".replace(",", ".")
    
    # Caso contrário, formatar com decimais
    formatted = f"{value_f:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return formatted.rstrip("0").rstrip(",")
```

### Substituir nos trechos do código:
1. Linha ~2320: `lines.append(f"{prefix}📦 {nome}: {embalagens:g} (internas: {total_internas:g} un)")`
2. Linha ~2435: `lines.append(f"{prefix}📦 Saldo interno total ({nome_tipo}): {total_interno_unidades:.2f} unidades")`
3. Adicionar a função `_fmt_number` ao início da classe TelegramService

---

## Qual modelo você prefere?
- **Modelo 1**: Mais descritivo, explica o conteúdo de cada embalagem
- **Modelo 2**: Compacto, usa operador × para mostrar cálculo direto
- **Modelo 3**: ⭐ Hierárquico visual, fácil de ler, profissional (RECOMENDADO)
