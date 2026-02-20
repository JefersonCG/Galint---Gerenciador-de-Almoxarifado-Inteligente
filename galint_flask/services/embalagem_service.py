"""Serviço para gerenciar lógica de embalagens (lata, rolo, pacote, caixa, litro, balde)."""
from __future__ import annotations

from typing import Dict, Tuple
from ..models import Item
from ..extensions import db


class EmbalagemService:
    """Gerencia operações de conversão e controle de embalagens."""
    
    TIPOS_VALIDOS = ['lata', 'rolo', 'pacote', 'caixa', 'litro', 'balde']
    
    @staticmethod
    def tem_embalagem(item: Item) -> bool:
        """Verifica se o item usa sistema de embalagens."""
        return (
            item.tipo_embalagem_novo is not None 
            and item.tipo_embalagem_novo in EmbalagemService.TIPOS_VALIDOS
            and item.unidades_por_embalagem is not None
            and item.unidades_por_embalagem > 0
        )

    @staticmethod
    def tem_rolo_legacy(item: Item) -> bool:
        """Verifica se o item usa rolo no sistema antigo (metros por rolo)."""
        return (
            item.tipo_embalagem is not None
            and str(item.tipo_embalagem).strip().lower() == "rolo"
            and item.grandeza_referencia is not None
            and item.grandeza_referencia > 0
        )
    
    @staticmethod
    def processar_entrada(
        item: Item, 
        quantidade: float, 
        em_embalagens: bool
    ) -> Tuple[float, float]:
        """
        Processa entrada de estoque com embalagens.
        
        Args:
            item: Item do estoque
            quantidade: Quantidade a adicionar
            em_embalagens: True se quantidade é em embalagens, False se em unidades
            
        Returns:
            Tupla (novas_embalagens, novas_unidades_soltas)
        """
        if not EmbalagemService.tem_embalagem(item):
            return (0, 0)
        
        embalagens_atuais = item.estoque_embalagens or 0
        soltas_atuais = item.estoque_unidades_soltas or 0
        
        if em_embalagens:
            # Entrada de embalagens fechadas
            embalagens_atuais += quantidade
        else:
            # Entrada de unidades soltas
            soltas_atuais += quantidade
            
            # Se acumular unidades suficientes, "fecha" embalagens
            while soltas_atuais >= item.unidades_por_embalagem:
                soltas_atuais -= item.unidades_por_embalagem
                embalagens_atuais += 1
        
        return (embalagens_atuais, soltas_atuais)
    
    @staticmethod
    def processar_saida(
        item: Item, 
        quantidade: float, 
        em_embalagens: bool
    ) -> Tuple[float, float, bool]:
        """
        Processa saída de estoque com embalagens.
        
        Args:
            item: Item do estoque
            quantidade: Quantidade a retirar
            em_embalagens: True se quantidade é em embalagens, False se em unidades
            
        Returns:
            Tupla (novas_embalagens, novas_unidades_soltas, sucesso)
            sucesso=False se não houver estoque suficiente
        """
        if not EmbalagemService.tem_embalagem(item):
            return (0, 0, False)
        
        embalagens_atuais = item.estoque_embalagens or 0
        soltas_atuais = item.estoque_unidades_soltas or 0
        
        if em_embalagens:
            # Saída de embalagens fechadas
            quantidade_embalagens = quantidade
            
            if embalagens_atuais < quantidade_embalagens:
                return (embalagens_atuais, soltas_atuais, False)
            
            embalagens_atuais -= quantidade_embalagens
        else:
            # Saída de unidades soltas
            quantidade_unidades = quantidade
            
            # Primeiro tenta usar unidades soltas
            if soltas_atuais >= quantidade_unidades:
                soltas_atuais -= quantidade_unidades
            else:
                # Precisa abrir embalagens
                faltam = quantidade_unidades - soltas_atuais
                embalagens_necessarias = int((faltam + item.unidades_por_embalagem - 1) / item.unidades_por_embalagem)
                
                if embalagens_atuais < embalagens_necessarias:
                    # Não tem estoque suficiente
                    return (embalagens_atuais, soltas_atuais, False)
                
                # Abre as embalagens necessárias
                embalagens_atuais -= embalagens_necessarias
                soltas_atuais += (embalagens_necessarias * item.unidades_por_embalagem)
                
                # Agora retira a quantidade
                soltas_atuais -= quantidade_unidades
        
        return (embalagens_atuais, soltas_atuais, True)
    
    @staticmethod
    def processar_devolucao(
        item: Item, 
        quantidade: float, 
        em_embalagens: bool
    ) -> Tuple[float, float]:
        """
        Processa devolução (retorno ao estoque).
        Usa a mesma lógica de entrada.
        
        Args:
            item: Item do estoque
            quantidade: Quantidade a devolver
            em_embalagens: True se quantidade é em embalagens, False se em unidades
            
        Returns:
            Tupla (novas_embalagens, novas_unidades_soltas)
        """
        return EmbalagemService.processar_entrada(item, quantidade, em_embalagens)
    
    @staticmethod
    def calcular_estoque_total(item: Item) -> float:
        """Calcula estoque total em unidades."""
        if not EmbalagemService.tem_embalagem(item):
            return item.get_saldo_atual()
        
        embalagens = item.estoque_embalagens or 0
        soltas = item.estoque_unidades_soltas or 0
        
        return (embalagens * item.unidades_por_embalagem) + soltas
    
    @staticmethod
    def formatar_estoque(item: Item) -> str:
        """
        Formata o estoque para exibição.
        
        Returns:
            String formatada, ex: "19 caixas + 464 unidades" ou "234 litros (65 latas)"
        """
        if EmbalagemService.tem_rolo_legacy(item):
            saldo_atual = item.get_saldo_atual() or 0
            total_metros = saldo_atual * item.grandeza_referencia
            nome_rolo = "rolo" if saldo_atual == 1 else "rolos"
            return f"{total_metros:g} metros ({saldo_atual:g} {nome_rolo})"

        # Para lata/balde com volume em litros definido (Compatível com Legacy e Novo Sistema)
        if (item.litros_por_embalagem and item.litros_por_embalagem > 0 and 
            (item.unidade and item.unidade.lower() in ['lata', 'litro', 'balde'] or
             item.tipo_embalagem_novo and item.tipo_embalagem_novo.lower() in ['lata', 'litro', 'balde'])):
            
            # Determina a quantidade de embalagens baseada no sistema (Novo vs Legacy)
            usa_sistema_novo = EmbalagemService.tem_embalagem(item)
            qtde_embalagens = (item.estoque_embalagens or 0) if usa_sistema_novo else (item.get_saldo_atual() or 0)
            
            # Calcula volume total em litros
            volume_total = qtde_embalagens * item.litros_por_embalagem
            
            # Determina o nome da embalagem
            if usa_sistema_novo:
                nome_emb = item.get_nome_embalagem_plural() if qtde_embalagens != 1 else item.get_nome_embalagem()
            else:
                nome_emb = (item.unidade or "embalagem") + ("s" if qtde_embalagens != 1 and not (item.unidade or "").endswith('s') else "")

            if qtde_embalagens == 0:
                return f"0 litros"
            elif qtde_embalagens == 1:
                return f"{volume_total:.1f} litros (1 {item.get_nome_embalagem() if usa_sistema_novo else (item.unidade or 'embalagem')})"
            else:
                return f"{volume_total:.1f} litros ({qtde_embalagens:.0f} {nome_emb})"
        
        # Para lata/balde com peso em kg definido (grandeza_referencia = kg por embalagem)
        # Compatível com Legacy e Novo Sistema
        if (item.grandeza_referencia and item.grandeza_referencia > 0 and
            (item.unidade and item.unidade.lower() in ['lata', 'balde'] or
             item.tipo_embalagem_novo and item.tipo_embalagem_novo.lower() in ['lata', 'balde'])):
            
            # Determina a quantidade de embalagens baseada no sistema (Novo vs Legacy)
            usa_sistema_novo = EmbalagemService.tem_embalagem(item)
            qtde_embalagens = (item.estoque_embalagens or 0) if usa_sistema_novo else (item.get_saldo_atual() or 0)
            
            # Calcula peso total em kg
            peso_total = qtde_embalagens * item.grandeza_referencia
            
            # Determina o nome da embalagem
            if usa_sistema_novo:
                nome_emb = item.get_nome_embalagem_plural() if qtde_embalagens != 1 else item.get_nome_embalagem()
            else:
                nome_emb = (item.unidade or "embalagem") + ("s" if qtde_embalagens != 1 and not (item.unidade or "").endswith('s') else "")
            
            if qtde_embalagens == 0:
                return f"0 kg"
            elif qtde_embalagens == 1:
                return f"{peso_total:.1f} kg (1 {item.get_nome_embalagem() if usa_sistema_novo else (item.unidade or 'embalagem')})"
            else:
                return f"{peso_total:.1f} kg ({qtde_embalagens:.0f} {nome_emb})"

        if not EmbalagemService.tem_embalagem(item):
            # Verificar se é ROLO/PACOTE/CAIXA usando campo unidade (legacy)
            unidade_lower = (item.unidade or "").strip().lower()
            
            # Se for ROLO/PACOTE/CAIXA no campo unidade e tiver unidades_por_embalagem
            if unidade_lower in ['rolo', 'pacote', 'caixa'] and item.unidades_por_embalagem:
                saldo_embalagens = item.get_saldo_atual() or 0
                unidades_internas = item.unidades_por_embalagem
                total_interno = saldo_embalagens * unidades_internas
                
                nome_singular = {'rolo': 'rolo', 'pacote': 'pacote', 'caixa': 'caixa'}.get(unidade_lower, unidade_lower)
                nome_plural = {'rolo': 'rolos', 'pacote': 'pacotes', 'caixa': 'caixas'}.get(unidade_lower, unidade_lower + 's')
                nome_emb_display = nome_singular if saldo_embalagens == 1 else nome_plural
                
                if unidade_lower == 'rolo':
                    # Para ROLO: mostrar em metros
                    if saldo_embalagens == 0:
                        return "0 metros"
                    return f"{total_interno:g} metros ({saldo_embalagens:g} {nome_emb_display})"
                else:
                    # Para PACOTE e CAIXA: mostrar unidades internas
                    if saldo_embalagens == 0:
                        return "0 unidades"
                    return f"{total_interno:g} unidades ({saldo_embalagens:g} {nome_emb_display})"
            
            return f"{item.get_saldo_atual():.0f} {item.unidade or 'unidades'}"
        
        embalagens = item.estoque_embalagens or 0
        soltas = item.estoque_unidades_soltas or 0
        nome_emb = item.get_nome_embalagem_plural() if embalagens != 1 else item.get_nome_embalagem()
        
        # Para rolos: mostrar saldo total em metros
        if item.tipo_embalagem_novo and item.tipo_embalagem_novo.lower() == 'rolo':
            metros_por_rolo = item.unidades_por_embalagem or 0
            total_metros = (embalagens * metros_por_rolo) + soltas

            if embalagens == 0:
                return f"{total_metros:g} metros"
            if soltas > 0:
                return f"{total_metros:g} metros ({embalagens:.0f} {nome_emb} + {soltas:g} metros)"
            return f"{total_metros:g} metros ({embalagens:.0f} {nome_emb})"
        
        # Para pacotes e caixas: mostrar total de unidades internas
        if item.tipo_embalagem_novo and item.tipo_embalagem_novo.lower() in ['pacote', 'caixa']:
            unidades_por_emb = item.unidades_por_embalagem or 0
            total_unidades = (embalagens * unidades_por_emb) + soltas

            if embalagens == 0:
                return f"{total_unidades:g} unidades"
            if soltas > 0:
                return f"{total_unidades:g} unidades ({embalagens:.0f} {nome_emb} + {soltas:g} unidades)"
            return f"{total_unidades:g} unidades ({embalagens:.0f} {nome_emb})"
        
        # Para outros produtos (sistema normal de embalagens + unidades)
        # Se não tem embalagens fechadas, mostrar só unidades soltas
        if embalagens == 0:
            return f"{soltas:.0f} unidades"
        
        # Se tem embalagens e unidades soltas
        if soltas > 0:
            return f"{embalagens:.0f} {nome_emb} + {soltas:.0f} unidades"
        
        # Se tem só embalagens
        return f"{embalagens:.0f} {nome_emb}"
    
    @staticmethod
    def formatar_quantidade(quantidade: float, item: Item) -> str:
        """
        Formata uma quantidade específica para exibição com embalagens inteligentes.
        
        Args:
            quantidade: Quantidade a ser formatada (em UNIDADES TOTAIS)
            item: Item do estoque (contém info de embalagens)
        
        Returns:
            String formatada, ex: "2 Latas + 16.67 litros" ou "3 caixas + 4 unidades"
        """
        if quantidade <= 0:
            return "0"
        
        # Rolo Legacy
        if EmbalagemService.tem_rolo_legacy(item):
            # No sistema legacy, quantidade representa número de rolos
            total_metros = quantidade * item.grandeza_referencia
            qtde_rolos = quantidade
            nome_rolo = "rolo" if qtde_rolos == 1 else "rolos"
            return f"{total_metros:g} metros ({qtde_rolos:g} {nome_rolo})"

        # Lata/balde com volume em litros
        if (item.litros_por_embalagem and item.litros_por_embalagem > 0 and 
            (item.unidade and item.unidade.lower() in ['lata', 'litro', 'balde'] or
             item.tipo_embalagem_novo and item.tipo_embalagem_novo.lower() in ['lata', 'litro', 'balde'])):
            
            usa_sistema_novo = EmbalagemService.tem_embalagem(item)
            litros_por_emb = item.litros_por_embalagem
            
            if usa_sistema_novo:
                # Quantidade vem em UNIDADES (embalagens), precisa converter para litros
                qtde_embalagens_int = int(quantidade)
                resto_embalagens = quantidade - qtde_embalagens_int
                volume_total = quantidade * litros_por_emb
                resto_litros = resto_embalagens * litros_por_emb
                
                nome_emb = item.get_nome_embalagem_plural() if qtde_embalagens_int != 1 else item.get_nome_embalagem()
                
                if qtde_embalagens_int == 0:
                    return f"{volume_total:.2f} litros"
                elif resto_litros > 0.01:
                    return f"{qtde_embalagens_int} {nome_emb} + {resto_litros:.2f} litros"
                else:
                    return f"{volume_total:.2f} litros ({qtde_embalagens_int} {nome_emb})"
            else:
                # Sistema legacy: quantidade já representa embalagens
                volume_total = quantidade * litros_por_emb
                nome_emb = (item.unidade or "embalagem") + ("s" if quantidade != 1 and not (item.unidade or "").endswith('s') else "")
                return f"{volume_total:.2f} litros ({quantidade:g} {nome_emb})"
        
        # Lata/balde com peso em kg
        if (item.grandeza_referencia and item.grandeza_referencia > 0 and
            (item.unidade and item.unidade.lower() in ['lata', 'balde'] or
             item.tipo_embalagem_novo and item.tipo_embalagem_novo.lower() in ['lata', 'balde'])):
            
            usa_sistema_novo = EmbalagemService.tem_embalagem(item)
            kg_por_emb = item.grandeza_referencia
            
            if usa_sistema_novo:
                # Quantidade vem em UNIDADES (embalagens), precisa converter para kg
                qtde_embalagens_int = int(quantidade)
                resto_embalagens = quantidade - qtde_embalagens_int
                peso_total = quantidade * kg_por_emb
                resto_kg = resto_embalagens * kg_por_emb
                
                nome_emb = item.get_nome_embalagem_plural() if qtde_embalagens_int != 1 else item.get_nome_embalagem()
                
                if qtde_embalagens_int == 0:
                    return f"{peso_total:.2f} kg"
                elif resto_kg > 0.01:
                    return f"{qtde_embalagens_int} {nome_emb} + {resto_kg:.2f} kg"
                else:
                    return f"{peso_total:.2f} kg ({qtde_embalagens_int} {nome_emb})"
            else:
                # Sistema legacy: quantidade já representa embalagens
                peso_total = quantidade * kg_por_emb
                nome_emb = (item.unidade or "embalagem") + ("s" if quantidade != 1 and not (item.unidade or "").endswith('s') else "")
                return f"{peso_total:.2f} kg ({quantidade:g} {nome_emb})"
        
        # Sistema de embalagens unificado (rolos, pacotes, caixas)
        if EmbalagemService.tem_embalagem(item):
            tipo_emb = (item.tipo_embalagem_novo or "").strip().lower()
            unidades_por = item.unidades_por_embalagem or 1
            
            # CORREÇÃO: Quantidade vem em UNIDADES TOTAIS, precisa converter para embalagens + resto
            embalagens_completas = int(quantidade / unidades_por) if unidades_por > 0 else 0
            resto = quantidade - (embalagens_completas * unidades_por)
            
            nome_emb = item.get_nome_embalagem_plural() if embalagens_completas != 1 else item.get_nome_embalagem()
            
            # Para rolos: mostrar em metros
            if tipo_emb == 'rolo':
                total_metros = quantidade
                if embalagens_completas == 0:
                    return f"{total_metros:g} metros"
                if resto > 0.01:
                    return f"{embalagens_completas} {nome_emb} + {resto:g} metros"
                return f"{total_metros:g} metros ({embalagens_completas} {nome_emb})"
            
            # Para pacotes e caixas: mostrar unidades internas
            if tipo_emb in ['pacote', 'caixa']:
                total_unidades = quantidade
                if embalagens_completas == 0:
                    return f"{total_unidades:g} unidades"
                if resto > 0.01:
                    return f"{embalagens_completas} {nome_emb} + {resto:g} unidades"
                return f"{total_unidades:g} unidades ({embalagens_completas} {nome_emb})"
            
            # Outros tipos de embalagem
            if resto > 0.01:
                return f"{embalagens_completas} {nome_emb} + {resto:g} unidades"
            return f"{embalagens_completas} {nome_emb}"
        
        # Legacy: rolo/pacote/caixa no campo unidade
        unidade_lower = (item.unidade or "").strip().lower()
        if unidade_lower in ['rolo', 'pacote', 'caixa'] and item.unidades_por_embalagem:
            # No sistema legacy, quantidade representa número de embalagens
            unidades_por = item.unidades_por_embalagem
            total_interno = quantidade * unidades_por
            
            nome_singular = {'rolo': 'rolo', 'pacote': 'pacote', 'caixa': 'caixa'}.get(unidade_lower, unidade_lower)
            nome_plural = {'rolo': 'rolos', 'pacote': 'pacotes', 'caixa': 'caixas'}.get(unidade_lower, unidade_lower + 's')
            nome_emb_display = nome_singular if quantidade == 1 else nome_plural
            
            if unidade_lower == 'rolo':
                return f"{total_interno:g} metros ({quantidade:g} {nome_emb_display})"
            else:
                return f"{total_interno:g} unidades ({quantidade:g} {nome_emb_display})"
        
        # Quantidade simples (sem embalagem)
        return f"{quantidade:g} {item.unidade or 'unidades'}"
    
    @staticmethod
    def converter_para_embalagens(quantidade_unidades: float, unidades_por_embalagem: float) -> float:
        """Converte quantidade em unidades para embalagens."""
        if unidades_por_embalagem <= 0:
            return 0
        return quantidade_unidades / unidades_por_embalagem
    
    @staticmethod
    def converter_para_unidades(quantidade_embalagens: float, unidades_por_embalagem: float) -> float:
        """Converte quantidade em embalagens para unidades."""
        return quantidade_embalagens * unidades_por_embalagem


# Instância global
embalagem_service = EmbalagemService()
