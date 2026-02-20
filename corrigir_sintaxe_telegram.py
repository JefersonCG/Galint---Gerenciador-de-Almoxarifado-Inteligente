"""Script para corrigir os modelos de notificação aplicando código válido"""
import re

file_path = "galint_flask/services/telegram_service.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# ===== CORREÇÃO 1: format_withdrawal_message_user =====
# Localizar a função quebrada e substituir
pattern1 = r'(@staticmethod\s+def format_withdrawal_message_user\(saida: Saida, usuario: Usuario, item: Item\) -> str:.*?)(return msg)'

new_func1 = r'''\1
        """Formata mensagem de retirada para o funcionário - Modelo 3: Ficha Técnica."""
        categoria = (item.categoria or "Geral").strip() or "Geral"
        local = (saida.local_servico or "NÃO INFORMADO").strip() or "NÃO INFORMADO"
        data_fmt = TimeService.format_local(saida.data_saida)
        quantidade_fmt = TelegramService._format_saida_quantidade(saida, item)
        
        # Emoji baseado na categoria
        emoji_map = {
            "ferramentas": "🔧",
            "material elétrico": "⚡",
            "material eletrico": "⚡",
            "material hidráulico": "🚰",
            "material hidraulico": "🚰",
            "material piscina": "🏊",
            "equipamento": "⚙️",
            "liquido": "💧",
            "líquido": "💧",
        }
        emoji = emoji_map.get(categoria.lower(), "📦")
        
        # Determinar título baseado na categoria
        categoria_titulo = categoria.upper()
        if "FERRAMENTA" in categ oria_titulo:
            categoria_titulo = "FERRAMENTA"
        
        # ========== MODELO 3: FICHA TÉCNICA ==========
        msg = f"📤 <b>NOVA RETIRADA REGISTRADA</b>\\n\\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\\n"
        msg += f"{emoji} <b>{item.descricao}</b>\\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\\n\\n"
        
        # RESPONSÁVEL PELA RETIRADA
        msg += f"👤 <b>VOCÊ RETIROU</b>\\n"
        msg += f"   • Data/Hora: {data_fmt}\\n\\n"
        
        # INFORMAÇÕES DO MATERIAL
        msg += f"📋 <b>INFORMAÇÕES DO MATERIAL</b>\\n"
        msg += f"   • Categoria: {categoria}\\n"
        msg += f"   • Quantidade retirada: {quantidade_fmt}\\n"
        
        # Lote se houver
        if hasattr(item, 'lote') and item.lote:
            msg += f"   • Lote: {item.lote}\\n"
        
        # Destino
        msg += f"   • Destino: {local}\\n"
        
        # IMPACTO NO ESTOQUE
        msg += f"\\n📊 <b>IMPACTO NO ESTOQUE</b>\\n"
        
        try:
            from ..services.embalagem_service import EmbalagemService, embalagem_service
            saldo_atual = int(item.get_saldo_atual() or 0)
            saldo_anterior = saldo_atual + int(saida.quantidade)
            unidade = item.unidade or 'unidades'
            
            msg += f"   • Saldo anterior: {saldo_anterior} {unidade}\\n"
            msg += f"   • Nova disponibilidade: <b>{saldo_atual} {unidade}</b>\\n"
            
            # Alerta de estoque zerado
            if saldo_atual == 0:
                msg += f"   • ⚠️ <b>STATUS: ESTOQUE ZERADO</b>\\n"
            elif saldo_atual < 3:
                msg += f"   • ⚠️ STATUS: Estoque baixo\\n"
        except Exception:
            pass

        # Lembrete para ferramentas
        if "ferrament" in categoria.lower():
            msg += f"\\n━━━━━━━━━━━━━━━━━━━━━━━━\\n"
            msg += f"⚠️ <i>Lembre-se de devolver ao final do expediente!</i>\\n"
        else:
            msg += f"\\n━━━━━━━━━━━━━━━━━━━━━━━━\\n"
        
        msg += f"⏰ Registro em {data_fmt}\\n"
        
        \2'''

# Aplicar com mais cuidado - buscar por linha específica
# Vou fazer uma abordagem mais simples: buscar ponto de início da função e reescrever só ela

print("Corrigindo funções quebradas...")
print("Script simplificado - necessário correção manual no arquivo.")
print("Por favor, execute o script Python alternativo.")
