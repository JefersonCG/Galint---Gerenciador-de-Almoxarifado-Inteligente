"""Script final para corrigir as f-strings quebradas"""
import re

file_path = "galint_flask/services/telegram_service.py"

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Encontrar e corrigir todas as f-strings quebradas
fixed_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # Detectar f-string quebrada (termina sem aspas de fechamento)
    if line.strip().startswith('msg') and 'f"' in line and not line.rstrip().endswith('"'):
        # É uma f-string quebrada, juntar com a próxima linha
        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        
        # Remover a quebra e adicionar \\n
        fixed_line = line.rstrip() + "\\n\"\n"
        fixed_lines.append(fixed_line)
        
        # Pular a linha vazia seguinte (a que tinha só ")
        if next_line.strip() == '"':
            i += 2
            continue
    else:
        fixed_lines.append(line)
    
    i += 1

# Escrever  o arquivo corrigido
with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(fixed_lines)

print("✅ F-strings corrigidas com sucesso!")
print(f"Total de linhas processadas: {len(lines)}")
print(f"Total de linhas no arquivo final: {len(fixed_lines)}")
