# 📝 ESTRATÉGIA DE VERSIONAMENTO GIT - GALINT

**Data:** 20/02/2026  
**Autor:** Ronaldo  
**Objetivo:** Garantir rastreabilidade completa de TODAS as alterações

---

## 🎯 REGRA DE OURO

**"CADA VÍRGULA NO GIT"**

✅ **SEMPRE fazer commit** antes de:
- Testar código
- Fazer build
- Iniciar servidor
- Modificar outra funcionalidade
- Pausar trabalho
- Finalizar o dia

❌ **NUNCA** trabalhar sem Git:
- Sem commit, sem histórico
- Sem histórico, sem recuperação
- Sem recuperação, perda de tempo e dinheiro

---

## 📋 CONVENÇÕES DE COMMIT

### **Formato:**
```
<tipo>: <descrição curta>

<descrição detalhada opcional>
<lista de alterações>
```

### **Tipos de Commit:**

| Tipo | Uso | Exemplo |
|------|-----|---------|
| `feat:` | Nova funcionalidade | `feat: adicionar devolucao multipla materiais` |
| `fix:` | Correção de bug | `fix: corrigir calculo saldo offline` |
| `refactor:` | Refatoração de código | `refactor: simplificar api.js` |
| `chore:` | Tarefas manutenção | `chore: auto-commit em 2026-02-20 15:30` |
| `docs:` | Documentação | `docs: atualizar README com API mobile` |
| `style:` | Formatação | `style: corrigir indentacao EstoqueScreen` |
| `test:` | Testes | `test: adicionar testes offline mode` |
| `perf:` | Performance | `perf: otimizar query estoque` |

---

## 🔄 FLUXO DE TRABALHO DIÁRIO

### **1. INÍCIO DO DIA**
```powershell
# Verificar status
git status

# Se houver alterações de ontem, commitar
.\auto_commit.ps1 "chore: commit inicial do dia"
```

### **2. DURANTE DESENVOLVIMENTO**

**A cada 15-30 minutos OU após cada funcionalidade:**
```powershell
.\auto_commit.ps1 "feat: implementar X"
```

**Commits específicos:**
```powershell
git add src/services/api.js
git commit -m "feat: adicionar device tracking no login"
```

### **3. FIM DO DIA**
```powershell
# Commitar tudo antes de desligar
.\auto_commit.ps1 "chore: fim do dia - WIP"

# Ver log do dia
git log --since="today" --oneline
```

---

## 🗂️ ESTRUTURA DOS REPOSITÓRIOS

```
GALINT_FLASK_COPIA_FULL_20251231_085800/  ← Repositório Principal
├── .git/                                  ← Git do Flask
├── galint-mobile/                         ← Subprojeto Mobile
│   ├── .git/                              ← Git separado do Mobile
│   └── auto_commit.ps1
├── auto_commit.ps1                        ← Script auto-commit Flask
├── .gitignore
└── ...código Flask...
```

**IMPORTANTE:**
- **Mobile** tem Git **separado** do Flask
- Commits mobile **independentes** de commits Flask
- Sempre commitar **ambos** quando alterar ambos

---

## 🚀 SCRIPTS DE AUTO-COMMIT

### **Flask (raiz do projeto):**
```powershell
.\auto_commit.ps1 "mensagem"
```

### **Mobile:**
```powershell
cd galint-mobile
.\auto_commit.ps1 "mensagem"
```

### **Ambos de uma vez:**
```powershell
# Flask
.\auto_commit.ps1 "feat: atualizar API X"

# Mobile
cd galint-mobile
.\auto_commit.ps1 "feat: integrar com API X"
cd ..
```

---

## 📊 VERIFICAR HISTÓRICO

### **Ver últimos 10 commits:**
```powershell
git log --oneline -10
```

### **Ver commits de hoje:**
```powershell
git log --since="today" --pretty=format:"%h - %s (%ci)"
```

### **Ver arquivos alterados:**
```powershell
git log --stat -1
```

### **Ver diferenças:**
```powershell
git diff HEAD~1
```

### **Ver commit específico:**
```powershell
git show <hash>
```

---

## ⚡ ATALHOS RÁPIDOS

### **Commit rápido (tudo):**
```powershell
git add -A; git commit -m "chore: salvamento rápido"
```

### **Ver status curto:**
```powershell
git status -s
```

### **Desfazer último commit (mantém alterações):**
```powershell
git reset --soft HEAD~1
```

### **Revertir arquivo específico:**
```powershell
git checkout -- arquivo.js
```

---

## 🔥 SITUAÇÕES DE EMERGÊNCIA

### **Código quebrou após última alteração:**
```powershell
# Ver o que mudou
git diff

# Voltar arquivo específico
git checkout HEAD -- arquivo.js

# Ou voltar TUDO para último commit
git reset --hard HEAD
```

### **Commit errado:**
```powershell
# Editar mensagem do último commit
git commit --amend -m "nova mensagem"

# Adicionar arquivo esquecido ao último commit
git add arquivo_esquecido.js
git commit --amend --no-edit
```

### **"Não sei o que mudou ontem!"**
```powershell
# Ver TUDO que mudou em 19/02/2026
git log --since="2026-02-19 00:00" --until="2026-02-19 23:59" --name-status
```

---

## 📌 BOAS PRÁTICAS

✅ **SEMPRE:**
- Commitar ANTES de testar build
- Commitar versões funcionais
- Mensagens descritivas
- Commitar mobile separado do Flask
- Usar `git status` frequentemente

❌ **NUNCA:**
- Commitar código que não roda
- Commitar senhas/tokens (usar .env)
- Trabalhar horas sem commit
- Confiar na memória
- Ignorar avisos do Git

---

## 🎓 APRENDIZADO

### **Problema passado:**
> "Ontem não foi registrado nada??"

### **Causa:**
- Não havia Git configurado no projeto principal
- Mobile tinha commits, mas Flask não
- Alterações sem rastreabilidade

### **Solução implementada:**
- ✅ Git inicializado em Flask
- ✅ .gitignore configurado
- ✅ Scripts auto_commit criados
- ✅ Documentação de fluxo (este arquivo)
- ✅ Convenções de commit definidas

### **Resultado esperado:**
**ZERO perguntas tipo "o que foi feito ontem?"**

---

## 🔗 COMANDOS ÚTEIS RESUMO

```powershell
# Status
git status
git status -s

# Commit rápido
.\auto_commit.ps1 "mensagem"

# Histórico
git log --oneline -10
git log --since="today"

# Ver diferenças
git diff
git diff HEAD~1

# Reverter
git checkout -- arquivo.js
git reset --hard HEAD
```

---

**Última atualização:** 20/02/2026 - Ronaldo  
**Revisão:** A cada nova necessidade identificada
