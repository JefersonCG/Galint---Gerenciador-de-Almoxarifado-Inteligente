"""Script para aplicar os novos modelos de notificação Telegram (Modelo 3)"""

# Novo código para format_devolucao_message
NEW_DEVOLUCAO_CODE = '''    @staticmethod
    def format_devolucao_message(evento, item) -> str:
        """Formata mensagem personalizada para devolução de material - Modelo 3: Tabela Descritiva."""
        from ..models import Saida
        
        codigo = evento.codigo_item or "N/A"
        descricao = item.descricao if item else "N/D"
        marca = getattr(item, "marca", None)
        categoria = getattr(item, "categoria", None) or "Material"
        quantidade = abs(float(getattr(evento, "quantidade", 0) or 0))
        data_devolucao = getattr(evento, "data_evento", None)
        data_devolucao_fmt = TimeService.format_local(data_devolucao)
        
        # Extrair informações do usuário da descrição
        descricao_evento = getattr(evento, "descricao", "") or ""
        devolvido_por = ""
        if "por" in descricao_evento:
            try:
                devolvido_por = descricao_evento.split("por")[-1].split(":")[0].strip()
            except:
                pass
        
        # Buscar a última saída deste item para obter quem retirou e quando
        retirado_por = None
        retirado_matricula = None
        data_retirada = None
        local_uso = None
        tempo_posse_str = ""
        
        if item:
            try:
                ultima_saida = (
                    Saida.query
                    .filter(Saida.codigo_item == codigo)
                    .order_by(Saida.data_saida.desc())
                    .first()
                )
                if ultima_saida:
                    data_retirada = ultima_saida.data_saida
                    local_uso = ultima_saida.local_servico
                    if ultima_saida.usuario:
                        retirado_por = ultima_saida.usuario.nome
                        retirado_matricula = ultima_saida.usuario.matricula
                    
                    # Calcular tempo de posse
                    if data_retirada and data_devolucao:
                        from datetime import timedelta
                        delta = data_devolucao - data_retirada
                        dias = delta.days
                        horas = delta.seconds // 3600
                        minutos = (delta.seconds % 3600) // 60
                        
                        partes = []
                        if dias > 0:
                            partes.append(f"{dias} dia{'s' if dias != 1 else ''}")
                        if horas > 0:
                            partes.append(f"{horas} hora{'s' if horas != 1 else ''}")
                        if minutos > 0 or not partes:
                            partes.append(f"{minutos} minuto{'s' if minutos != 1 else ''}")
                        tempo_posse_str = ", ".join(partes)
            except Exception:
                pass
        
        # Título dinâmico baseado na categoria
        categoria_titulo = categoria.upper() if isinstance(categoria, str) else "MATERIAL"
        if "FERRAMENTA" in categoria_titulo:
            categoria_titulo = "FERRAMENTA"
        
        # Emoji baseado na categoria
        emoji_map = {
            "ferramentas": "🔧",
            "material elétrico": "⚡",
            "material eletrico": "⚡",
            "material hidráulico": "🚰",
            "material hidraulico": "🚰",
            "material piscina": "🏊",
            "material de limpeza": "🧹",
            "equipamentos de epi": "🦺",
            "liquido": "💧",
            "líquido": "💧",
        }
        categoria_lower = categoria.lower() if isinstance(categoria, str) else ""
        emoji = emoji_map.get(categoria_lower, "📦")

        # ========== MODELO 3: TABELA DESCRITIVA ==========
        msg = f"🔄 <b>DEVOLUÇÃO DE {categoria_titulo}</b>\\n\\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\\n"
        msg += f"{emoji} <b>{descricao}</b>\\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\\n\\n"
        
        # DADOS DA FERRAMENTA/MATERIAL
        msg += f"📋 <b>DADOS DO ITEM</b>\\n"
        msg += f"   • Código: <code>{codigo}</code>\\n"
        msg += f"   • Categoria: {categoria}\\n"
        if marca:
            msg += f"   • Marca: {marca}\\n"
        
        # Buscar lote se existir
        lote = getattr(item, "lote", None) if item else None
        if lote:
            msg += f"   • Lote: {lote}\\n"
        
        # RETIRADA ORIGINAL
        if retirado_por:
            msg += f"\\n📤 <b>RETIRADA ORIGINAL</b>\\n"
            msg += f"   • Por: {retirado_por}"
            if retirado_matricula:
                msg += f" (Mat. {retirado_matricula})"
            msg += "\\n"
            if data_retirada:
                data_ret_fmt = TimeService.format_local(data_retirada)
                msg += f"   • Quando: {data_ret_fmt}\\n"
            if local_uso:
                msg += f"   • Local: {local_uso}\\n"
        
        # DEVOLUÇÃO REGISTRADA
        msg += f"\\n📥 <b>DEVOLUÇÃO REGISTRADA</b>\\n"
        if devolvido_por:
            msg += f"   • Por: {devolvido_por}\\n"
        msg += f"   • Quando: {data_devolucao_fmt}\\n"
        msg += f"   • Qtd: {quantidade:g} unidade{'s' if quantidade != 1 else ''}\\n"
        
        # TEMPO DE POSSE
        if tempo_posse_str:
            msg += f"\\n⏱️ <b>TEMPO DE POSSE</b>\\n"
            msg += f"   └─ {tempo_posse_str}\\n"
        
        # STATUS E EST OQUE
        msg += f"\\n✅ <b>Status:</b> Devolvida e disponível\\n"
        
        # Saldo após devolução
        if item:
            try:
                from galint_flask.services.embalagem_service import EmbalagemService
                if EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item):
                    estoque_str = EmbalagemService.formatar_estoque(item)
                    msg += f"📊 <b>Estoque atualizado:</b> {estoque_str}\\n"
                else:
                    saldo_atual = int(item.get_saldo_atual() or 0)
                    unidade = item.unidade or 'unidades'
                    msg += f"📊 <b>Estoque atualizado:</b> {saldo_atual} {unidade}\\n"
            except Exception:
                try:
                    saldo_atual = int(item.get_saldo_atual() or 0)
                    unidade = item.unidade or 'unidades'
                    msg += f"📊 <b>Estoque atualizado:</b> {saldo_atual} {unidade}\\n"
                except Exception:
                    pass

            totals = TelegramService._format_balance_totals(item, prefix="")
            if totals:
                msg += totals + "\\n"
        
        return msg
'''

# Novo código para format_withdrawal_message_user
NEW_WITHDRAWAL_USER_CODE = '''    @staticmethod
    def format_withdrawal_message_user(saida: Saida, usuario: Usuario, item: Item) -> str:
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
        if "FERRAMENTA" in categoria_titulo:
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
        
        return msg
'''

# Novo código para format_withdrawal_message_supervisor
NEW_WITHDRAWAL_SUPERVISOR_CODE = '''    @staticmethod
    def format_withdrawal_message_supervisor(saida: Saida, usuario: Usuario, item: Item) -> str:
        """Formata mensagem de retirada para supervisão - Modelo 3: Ficha Técnica."""
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
        if "FERRAMENTA" in categoria_titulo:
            categoria_titulo = "FERRAMENTA"
        
        # ========== MODELO 3: FICHA TÉCNICA (SUPERVISOR) ==========
        msg = f"📤 <b>NOVA RETIRADA REGISTRADA</b>\\n\\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\\n"
        msg += f"{emoji} <b>{item.descricao}</b>\\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━\\n\\n"
        
        # RESPONSÁVEL PELA RETIRADA
        msg += f"👤 <b>RESPONSÁVEL PELA RETIRADA</b>\\n"
        msg += f"   • Nome: {usuario.nome}\\n"
        msg += f"   • Matrícula: {usuario.matricula}\\n"
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
            
            # Alerta de estoque zerado ou baixo
            if saldo_atual == 0:
                msg += f"   • ⚠️ <b>STATUS: ESTOQUE ZERADO</b>\\n"
            elif saldo_atual < 3:
                msg += f"   • ⚠️ STATUS: Estoque baixo\\n"
        except Exception:
            pass
        
        msg += f"\\n━━━━━━━━━━━━━━━━━━━━━━━━\\n"
        msg += f"⏰ Registro em {data_fmt}\\n"
        
        return msg
'''

if __name__ == "__main__":
    import re
    
    file_path = "galint_flask/services/telegram_service.py"
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Substituir format_devolucao_message
    pattern_devolucao = r'    @staticmethod\s+def format_devolucao_message\(evento, item\) -> str:.*?return msg'
    content = re.sub(pattern_devolucao, NEW_DEVOLUCAO_CODE.strip(), content, flags=re.DOTALL)
    
    # Substituir format_withdrawal_message_user
    pattern_withdrawal_user = r'    @staticmethod\s+def format_withdrawal_message_user\(saida: Saida, usuario: Usuario, item: Item\) -> str:.*?return msg'
    content = re.sub(pattern_withdrawal_user, NEW_WITHDRAWAL_USER_CODE.strip(), content, flags=re.DOTALL)
    
    # Substituir format_withdrawal_message_supervisor
    pattern_withdrawal_super = r'    @staticmethod\s+def format_withdrawal_message_supervisor\(saida: Saida, usuario: Usuario, item: Item\) -> str:.*?(?=\n    @staticmethod|\n    def [a-z_]+\(|\nclass )'
    content = re.sub(pattern_withdrawal_super, NEW_WITHDRAWAL_SUPERVISOR_CODE.strip(), content, flags=re.DOTALL)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print("✅ Novos modelos aplicados com sucesso!")
    print("   - format_devolucao_message (Modelo 3 - Tabela Descritiva)")
    print("   - format_withdrawal_message_user (Modelo 3 - Ficha Técnica)")
    print("   - format_withdrawal_message_supervisor (Modelo 3 - Ficha Técnica)")
