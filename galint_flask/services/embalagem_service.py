"""Serviço para gerenciar lógica de embalagens (lata, rolo, pacote, caixa, fardo, litro, balde, bombona, saco)."""
from __future__ import annotations

from typing import Dict, Tuple
from ..models import Item


class EmbalagemService:
    """Gerencia operações de conversão e controle de embalagens."""
    
    TIPOS_VALIDOS = ['lata', 'rolo', 'pacote', 'caixa', 'fardo', 'litro', 'balde', 'bombona', 'saco']
    
    @staticmethod
    def tem_embalagem(item: Item) -> bool:
        """Verifica se o item usa sistema de embalagens."""
        from .legacy_stock_normalizer import ignore_packaging_metadata_for_stock, resolve_canonical_unit, resolve_packaging_factor

        tipo_embalagem = str(item.tipo_embalagem_novo or "").strip().lower()
        fator_embalagem = float(resolve_packaging_factor(item) or 0.0)
        unidade_canonica = str(resolve_canonical_unit(item) or "").strip().lower()

        if unidade_canonica in {"un", "par"} and 0 < fator_embalagem <= 1.0:
            return False

        return (
            bool(tipo_embalagem)
            and tipo_embalagem in EmbalagemService.TIPOS_VALIDOS
            and fator_embalagem > 0
            and not ignore_packaging_metadata_for_stock(item)
        )

    @staticmethod
    def tem_rolo_legacy(item: Item) -> bool:
        """Verifica se o item usa rolo no sistema antigo (metros por rolo)."""
        tipo_embalagem_novo = str(getattr(item, "tipo_embalagem_novo", None) or "").strip().lower()
        unidades_por_embalagem = float(getattr(item, "unidades_por_embalagem", 0) or 0)

        # Quando o item ja foi migrado para o sistema novo de embalagens,
        # o metadado legado nao pode voltar a dirigir a exibicao.
        if tipo_embalagem_novo == "rolo" and unidades_por_embalagem > 0:
            return False

        legacy_type = str(getattr(item, "tipo_embalagem", None) or "").strip().lower()
        legacy_reference = getattr(item, "grandeza_referencia", None)
        try:
            legacy_reference_value = float(legacy_reference)
        except (TypeError, ValueError):
            return False

        return (
            bool(legacy_type == "rolo")
            and legacy_reference is not None
            and legacy_reference_value > 0
        )

    @staticmethod
    def _resolve_measure(item: Item) -> tuple[float, str | None]:
        from .legacy_stock_normalizer import infer_packaging_measure

        inferred = infer_packaging_measure(item)
        if inferred is None:
            return 0.0, None
        return float(inferred[0] or 0.0), inferred[1]

    @staticmethod
    def _resolve_packaging_display_factor(item: Item, measure_value: float, measure_unit: str | None) -> float:
        from .legacy_stock_normalizer import resolve_packaging_factor

        factor = float(resolve_packaging_factor(item) or 0.0)
        if factor > 0:
            return factor
        if measure_value > 0 and measure_unit:
            return float(measure_value)
        return float(getattr(item, "unidades_por_embalagem", 0) or 0.0)
    
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

        from .legacy_stock_normalizer import resolve_packaging_factor
        
        embalagens_atuais = float(item.estoque_embalagens or 0)
        soltas_atuais = float(item.estoque_unidades_soltas or 0)
        fator_embalagem = float(resolve_packaging_factor(item) or 0)
        if fator_embalagem <= 0:
            return (embalagens_atuais, soltas_atuais)
        
        if em_embalagens:
            # Entrada de embalagens fechadas
            embalagens_atuais += float(quantidade)
        else:
            # Entrada de unidades soltas
            soltas_atuais += float(quantidade)
            
            # Se acumular unidades suficientes, "fecha" embalagens
            while soltas_atuais >= fator_embalagem:
                soltas_atuais -= fator_embalagem
                embalagens_atuais += 1.0
        
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

        from .legacy_stock_normalizer import resolve_packaging_factor
        
        embalagens_atuais = float(item.estoque_embalagens or 0)
        soltas_atuais = float(item.estoque_unidades_soltas or 0)
        fator_embalagem = float(resolve_packaging_factor(item) or 0)
        if fator_embalagem <= 0:
            return (embalagens_atuais, soltas_atuais, False)
        
        if em_embalagens:
            # Saída de embalagens fechadas
            quantidade_embalagens = float(quantidade)
            
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
                import math
                faltam = quantidade_unidades - soltas_atuais
                embalagens_necessarias = math.ceil(faltam / fator_embalagem)
                
                if embalagens_atuais < embalagens_necessarias:
                    # Não tem estoque suficiente
                    return (embalagens_atuais, soltas_atuais, False)
                
                # Abre as embalagens necessárias
                embalagens_atuais -= embalagens_necessarias
                soltas_atuais += (embalagens_necessarias * fator_embalagem)
                
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

        from .legacy_stock_normalizer import resolve_packaging_factor
        
        embalagens = float(item.estoque_embalagens or 0)
        soltas = float(item.estoque_unidades_soltas or 0)
        fator_embalagem = float(resolve_packaging_factor(item) or 0)
        
        return (embalagens * fator_embalagem) + soltas

    @staticmethod
    def tentar_sincronizar_estoque_de_legacy(item: Item) -> bool:
        """Tenta sincronizar o estoque novo (embalagens/unidades soltas) a partir do saldo legado.

        Contexto:
        - O sistema legado calcula saldo via somatório de entradas/saídas/ajustes.
        - O sistema novo de embalagens usa os campos `Item.estoque_embalagens` e
          `Item.estoque_unidades_soltas`.

        Problema comum:
        - Itens antigos podem ter saldo legado positivo (ex.: 1 caixa), mas o estoque novo
          permanece em 0 embalagens, causando "Saldo insuficiente" ao retirar unidades.

        Heurística (conservadora):
        - Só sincroniza quando o item tem embalagem e o estoque novo ainda não tem embalagens.
        - Usa o saldo legado apenas quando ele parece inteiro (caso típico de caixas/pacotes).
        - Nunca diminui o estoque novo; só aumenta quando o legado implicar mais unidades.

        Retorna True quando realizou sincronização (sem commit).
        """
        if not EmbalagemService.tem_embalagem(item):
            return False

        from .balance_provider import balance_provider
        from .legacy_stock_normalizer import is_packaging_unit_code, resolve_packaging_factor

        factor = float(resolve_packaging_factor(item) or 0)
        if factor <= 0:
            return False

        try:
            estoque_emb_atual = float(item.estoque_embalagens or 0)
            estoque_soltas_atual = float(item.estoque_unidades_soltas or 0)
        except Exception:
            estoque_emb_atual = 0.0
            estoque_soltas_atual = 0.0

        try:
            snapshot = balance_provider.get_balance(item.codigo_item, item=item)
            saldo_legacy = float(snapshot.quantity_base or 0)
            unit_base = str(snapshot.unit_base or item.unidade or "").strip().lower()
        except Exception:
            return False

        if saldo_legacy <= 0:
            return False

        # Proteção contra valores absurdos (evita explosões em casos de unidade errada).
        if saldo_legacy > 100000:
            return False

        current_total = (estoque_emb_atual * factor) + estoque_soltas_atual

        if unit_base and is_packaging_unit_code(unit_base):
            saldo_legacy_int = int(round(saldo_legacy))
            if abs(saldo_legacy - saldo_legacy_int) > 1e-6:
                return False
            target_embalagens = float(saldo_legacy_int)
            target_soltas = float(estoque_soltas_atual % factor) if estoque_soltas_atual >= factor else float(estoque_soltas_atual)
            target_total = (target_embalagens * factor) + target_soltas
        else:
            import math

            target_total = float(saldo_legacy)
            target_embalagens = float(math.floor((target_total + 1e-9) / factor))
            target_soltas = float(target_total - (target_embalagens * factor))
            if abs(target_soltas) <= 1e-6:
                target_soltas = 0.0

        if target_total <= current_total + 1e-6:
            return True

        item.estoque_embalagens = float(target_embalagens)
        item.estoque_unidades_soltas = float(target_soltas)
        return True
    
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

        measure_value, measure_unit = EmbalagemService._resolve_measure(item)

        # Para lata/balde/bombona com volume em litros definido (Compatível com Legacy APENAS)
        # IMPORTANTE: Este bloco NÃO deve ser usado quando há estoque_unidades_soltas
        if (item.litros_por_embalagem and item.litros_por_embalagem > 0 and 
            (item.unidade and item.unidade.lower() in ['lata', 'litro', 'balde', 'bombona'] or
             item.tipo_embalagem_novo and item.tipo_embalagem_novo.lower() in ['lata', 'litro', 'balde', 'bombona'])):
            
            # Determina a quantidade de embalagens baseada no sistema (Novo vs Legacy)
            usa_sistema_novo = EmbalagemService.tem_embalagem(item)
            
            # Se usa sistema novo E tem unidades soltas, pula este bloco (será tratado depois)
            if usa_sistema_novo and (item.estoque_unidades_soltas or 0) > 0:
                pass  # Será tratado no bloco específico de lata/balde/litro com soltas
            else:
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
        
        # Para lata/balde/bombona com peso em kg definido (grandeza_referencia = kg por embalagem)
        # Compatível com Legacy e Novo Sistema
        if (measure_unit == 'kg' and measure_value > 0 and
            (item.unidade and item.unidade.lower() in ['lata', 'balde', 'bombona', 'pacote', 'saco'] or
             item.tipo_embalagem_novo and item.tipo_embalagem_novo.lower() in ['lata', 'balde', 'bombona', 'pacote', 'saco'])):
            
            # Determina a quantidade de embalagens baseada no sistema (Novo vs Legacy)
            usa_sistema_novo = EmbalagemService.tem_embalagem(item)
            if usa_sistema_novo and (item.estoque_unidades_soltas or 0) > 0:
                pass
            else:
                qtde_embalagens = (item.estoque_embalagens or 0) if usa_sistema_novo else (item.get_saldo_atual() or 0)
                
                # Calcula peso total em kg
                peso_total = qtde_embalagens * measure_value
                
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
            # Verificar se é ROLO/PACOTE/CAIXA/FARDO usando campo unidade (legacy)
            unidade_lower = (item.unidade or "").strip().lower()
            
            # Se for ROLO/PACOTE/CAIXA/FARDO no campo unidade e tiver unidades_por_embalagem
            if unidade_lower in ['rolo', 'pacote', 'caixa', 'fardo'] and item.unidades_por_embalagem:
                saldo_embalagens = item.get_saldo_atual() or 0
                unidades_internas = item.unidades_por_embalagem
                total_interno = saldo_embalagens * unidades_internas
                
                nome_singular = {'rolo': 'rolo', 'pacote': 'pacote', 'caixa': 'caixa', 'fardo': 'fardo'}.get(unidade_lower, unidade_lower)
                nome_plural = {'rolo': 'rolos', 'pacote': 'pacotes', 'caixa': 'caixas', 'fardo': 'fardos'}.get(unidade_lower, unidade_lower + 's')
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
            metros_por_rolo = EmbalagemService._resolve_packaging_display_factor(item, measure_value, measure_unit)
            total_metros = (embalagens * metros_por_rolo) + soltas

            if embalagens == 0:
                # Se tem menos de 1 metro, mostrar em centímetros
                if total_metros < 1:
                    return f"{total_metros * 100:g} centímetros"
                return f"{total_metros:g} metros"
            if soltas > 0:
                # Se soltas < 1, mostrar em centímetros
                if soltas < 1:
                    return f"{embalagens:.0f} {nome_emb} + {soltas * 100:g} centímetros"
                return f"{embalagens:.0f} {nome_emb} + {soltas:g} metros"
            return f"{total_metros:g} metros ({embalagens:.0f} {nome_emb})"
        
        # Para pacote/caixa/fardo/saco: mostrar total de unidades internas ou kg conforme configurado.
        if item.tipo_embalagem_novo and item.tipo_embalagem_novo.lower() in ['pacote', 'caixa', 'fardo', 'saco']:
            tipo_emb = item.tipo_embalagem_novo.lower()
            if measure_unit == 'kg' and measure_value > 0:
                kg_por_emb = measure_value
                total_kg = (embalagens * kg_por_emb) + soltas

                if embalagens == 0:
                    if total_kg < 1:
                        return f"{total_kg * 1000:g} gramas"
                    return f"{total_kg:g} Kg"
                if soltas > 0:
                    if soltas < 1:
                        return f"{embalagens:.0f} {nome_emb} + {soltas * 1000:g} gramas"
                    return f"{embalagens:.0f} {nome_emb} + {soltas:g} Kg"
                return f"{total_kg:g} Kg ({embalagens:.0f} {nome_emb})"

            unidades_por_emb = measure_value if measure_unit == 'un' and measure_value > 0 else (item.unidades_por_embalagem or 0)
            total_unidades = (embalagens * unidades_por_emb) + soltas

            if embalagens == 0:
                return f"{total_unidades:g} unidades"
            if soltas > 0:
                return f"{embalagens:.0f} {nome_emb} + {soltas:g} unidades"
            return f"{total_unidades:g} unidades ({embalagens:.0f} {nome_emb})"
        
        # Para lata/balde/bombona/litro: mostrar litros ou kg com unidades menores quando aplicável
        if item.tipo_embalagem_novo and item.tipo_embalagem_novo.lower() in ['lata', 'balde', 'bombona', 'litro']:
            if measure_unit == 'l' and measure_value > 0:
                litros_por_emb = measure_value
                litros_soltos = soltas
                
                if embalagens == 0:
                    # Se tem menos de 1 litro, mostrar em mililitros
                    if litros_soltos < 1:
                        return f"{litros_soltos * 1000:g} ml"
                    return f"{litros_soltos:g} Litros"
                if soltas > 0:
                    # Se soltas < 1, mostrar em ml
                    if litros_soltos < 1:
                        return f"{embalagens:.0f} {nome_emb} + {litros_soltos * 1000:g} ml"
                    return f"{embalagens:.0f} {nome_emb} + {litros_soltos:g} Litros"
                # Apenas embalagens
                volume_total = embalagens * litros_por_emb
                return f"{volume_total:g} Litros ({embalagens:.0f} {nome_emb})"
            
            elif measure_unit == 'kg' and measure_value > 0:
                kg_por_emb = measure_value
                kg_soltos = soltas
                
                if embalagens == 0:
                    # Se tem menos de 1 kg, mostrar em gramas
                    if kg_soltos < 1:
                        return f"{kg_soltos * 1000:g} gramas"
                    return f"{kg_soltos:g} Kg"
                if soltas > 0:
                    # Se soltas < 1, mostrar em gramas
                    if kg_soltos < 1:
                        return f"{embalagens:.0f} {nome_emb} + {kg_soltos * 1000:g} gramas"
                    return f"{embalagens:.0f} {nome_emb} + {kg_soltos:g} Kg"
                # Apenas embalagens
                peso_total = embalagens * kg_por_emb
                return f"{peso_total:g} Kg ({embalagens:.0f} {nome_emb})"
        
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

        measure_value, measure_unit = EmbalagemService._resolve_measure(item)
        
        # Rolo Legacy
        if EmbalagemService.tem_rolo_legacy(item):
            # No sistema legacy, quantidade representa número de rolos
            total_metros = quantidade * item.grandeza_referencia
            qtde_rolos = quantidade
            nome_rolo = "rolo" if qtde_rolos == 1 else "rolos"
            return f"{total_metros:g} metros ({qtde_rolos:g} {nome_rolo})"

        # Lata/balde/bombona com volume em litros
        if (item.litros_por_embalagem and item.litros_por_embalagem > 0 and 
            (item.unidade and item.unidade.lower() in ['lata', 'litro', 'balde', 'bombona'] or
             item.tipo_embalagem_novo and item.tipo_embalagem_novo.lower() in ['lata', 'litro', 'balde', 'bombona'])):
            
            usa_sistema_novo = EmbalagemService.tem_embalagem(item)
            litros_por_emb = item.litros_por_embalagem
            
            if usa_sistema_novo:
                # Quantidade vem em UNIDADES (embalagens), precisa converter para litros
                qtde_embalagens = float(quantidade)
                qtde_embalagens_int = int(qtde_embalagens)
                resto_embalagens = qtde_embalagens - qtde_embalagens_int
                volume_total = qtde_embalagens * litros_por_emb
                resto_litros = resto_embalagens * litros_por_emb
                
                nome_emb = item.get_nome_embalagem_plural() if qtde_embalagens_int != 1 else item.get_nome_embalagem()
                
                if qtde_embalagens_int == 0:
                    if volume_total < 1:
                        return f"{volume_total * 1000:.0f} ml"
                    return f"{volume_total:.2f} litros"
                elif resto_litros > 0.01:
                    if resto_litros < 1:
                        return f"{qtde_embalagens_int} {nome_emb} + {resto_litros * 1000:.0f} ml"
                    return f"{qtde_embalagens_int} {nome_emb} + {resto_litros:.2f} litros"
                else:
                    return f"{volume_total:.2f} litros ({qtde_embalagens_int} {nome_emb})"
            else:
                # Sistema legacy: quantidade já representa embalagens
                volume_total = quantidade * litros_por_emb
                nome_emb = (item.unidade or "embalagem") + ("s" if quantidade != 1 and not (item.unidade or "").endswith('s') else "")
                return f"{volume_total:.2f} litros ({quantidade:g} {nome_emb})"
        
        # Lata/balde/bombona com peso em kg
        if (measure_unit == 'kg' and measure_value > 0 and
            (item.unidade and item.unidade.lower() in ['lata', 'balde', 'bombona', 'pacote', 'saco'] or
             item.tipo_embalagem_novo and item.tipo_embalagem_novo.lower() in ['lata', 'balde', 'bombona', 'pacote', 'saco'])):
            
            usa_sistema_novo = EmbalagemService.tem_embalagem(item)
            kg_por_emb = measure_value
            
            if usa_sistema_novo:
                # Quantidade vem em UNIDADES (embalagens), precisa converter para kg
                qtde_embalagens = float(quantidade)
                qtde_embalagens_int = int(qtde_embalagens)
                resto_embalagens = qtde_embalagens - qtde_embalagens_int
                peso_total = qtde_embalagens * kg_por_emb
                resto_kg = resto_embalagens * kg_por_emb
                
                nome_emb = item.get_nome_embalagem_plural() if qtde_embalagens_int != 1 else item.get_nome_embalagem()
                
                if qtde_embalagens_int == 0:
                    if peso_total < 1:
                        return f"{peso_total * 1000:.0f} gramas"
                    return f"{peso_total:.2f} kg"
                elif resto_kg > 0.01:
                    if resto_kg < 1:
                        return f"{qtde_embalagens_int} {nome_emb} + {resto_kg * 1000:.0f} gramas"
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
            unidades_por = EmbalagemService._resolve_packaging_display_factor(item, measure_value, measure_unit)
            
            # CORREÇÃO: Quantidade vem em UNIDADES TOTAIS, precisa converter para embalagens + resto
            quantidade_float = float(quantidade)
            embalagens_completas = int(quantidade_float // unidades_por) if unidades_por > 0 else 0
            resto = quantidade_float - (embalagens_completas * unidades_por)
            
            nome_emb = item.get_nome_embalagem_plural() if embalagens_completas != 1 else item.get_nome_embalagem()
            
            # Para rolos: mostrar em metros
            if tipo_emb == 'rolo':
                total_metros = quantidade_float
                if embalagens_completas == 0:
                    if total_metros < 1:
                        return f"{total_metros * 100:.0f} centímetros"
                    return f"{total_metros:g} metros"
                if resto > 0.01:
                    if resto < 1:
                        return f"{embalagens_completas} {nome_emb} + {resto * 100:.0f} centímetros"
                    return f"{embalagens_completas} {nome_emb} + {resto:g} metros"
                return f"{total_metros:g} metros ({embalagens_completas} {nome_emb})"
            
            # Para pacote/caixa/fardo/saco: mostrar unidades internas ou kg conforme configurado.
            if tipo_emb in ['pacote', 'caixa', 'fardo', 'saco']:
                if measure_unit == 'kg' and measure_value > 0:
                    total_kg = quantidade_float
                    if embalagens_completas == 0:
                        if total_kg < 1:
                            return f"{total_kg * 1000:.0f} gramas"
                        return f"{total_kg:.2f} kg"
                    if resto > 0.01:
                        if resto < 1:
                            return f"{embalagens_completas} {nome_emb} + {resto * 1000:.0f} gramas"
                        return f"{embalagens_completas} {nome_emb} + {resto:.2f} kg"
                    return f"{total_kg:.2f} kg ({embalagens_completas} {nome_emb})"

                total_unidades = quantidade_float
                if embalagens_completas == 0:
                    return f"{total_unidades:g} unidades"
                if resto > 0.01:
                    return f"{embalagens_completas} {nome_emb} + {resto:g} unidades"
                return f"{total_unidades:g} unidades ({embalagens_completas} {nome_emb})"
            
            # Outros tipos de embalagem
            if resto > 0.01:
                return f"{embalagens_completas} {nome_emb} + {resto:g} unidades"
            return f"{embalagens_completas} {nome_emb}"
        
        # Legacy: rolo/pacote/caixa/fardo no campo unidade
        unidade_lower = (item.unidade or "").strip().lower()
        if unidade_lower in ['rolo', 'pacote', 'caixa', 'fardo'] and item.unidades_por_embalagem:
            # No sistema legacy, quantidade representa número de embalagens
            unidades_por = item.unidades_por_embalagem
            total_interno = quantidade * unidades_por
            
            nome_singular = {'rolo': 'rolo', 'pacote': 'pacote', 'caixa': 'caixa', 'fardo': 'fardo'}.get(unidade_lower, unidade_lower)
            nome_plural = {'rolo': 'rolos', 'pacote': 'pacotes', 'caixa': 'caixas', 'fardo': 'fardos'}.get(unidade_lower, unidade_lower + 's')
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
    
    @staticmethod
    def gerar_explicacao_saldo(item: Item) -> str | None:
        """
        Gera explicação detalhada do saldo seguindo o formato:
        "ou seja, cada Lata contém 18 Litros + 9 Litros soltos de lata aberta anteriormente."
        
        Returns:
            String com explicação ou None se o item não usa embalagens
        """
        if not EmbalagemService.tem_embalagem(item):
            return None

        embalagens = float(item.estoque_embalagens or 0)
        soltas = float(item.estoque_unidades_soltas or 0)
        
        # Sem explicação se não tem embalagens nem soltas
        if embalagens == 0 and soltas == 0:
            return None
        
        nome_emb_singular = item.get_nome_embalagem()
        tipo_emb = (item.tipo_embalagem_novo or "").strip().lower()
        measure_value, measure_unit = EmbalagemService._resolve_measure(item)
        
        # Para lata/balde/bombona com litros
        if tipo_emb in ['lata', 'balde', 'bombona'] and measure_unit == 'l' and measure_value > 0:
            litros_por_emb = measure_value
            if embalagens > 0 and soltas > 0:
                return f"ou seja, cada {nome_emb_singular} contém {litros_por_emb:g} litros + {soltas:g} litros soltos de {nome_emb_singular} aberta anteriormente."
            elif embalagens > 0:
                return f"ou seja, cada {nome_emb_singular} contém {litros_por_emb:g} litros."
            else:
                return f"ou seja, {soltas:g} litros soltos de {nome_emb_singular} aberta anteriormente."
        
        # Para lata/balde/bombona com kg
        if tipo_emb in ['lata', 'balde', 'bombona', 'pacote', 'saco'] and measure_unit == 'kg' and measure_value > 0:
            kg_por_emb = measure_value
            if embalagens > 0 and soltas > 0:
                return f"ou seja, cada {nome_emb_singular} contém {kg_por_emb:g}kg + {soltas:g}kg soltos de {nome_emb_singular} aberto anteriormente."
            elif embalagens > 0:
                return f"ou seja, cada {nome_emb_singular} contém {kg_por_emb:g}kg."
            else:
                return f"ou seja, {soltas:g}kg soltos de {nome_emb_singular} aberto anteriormente."
        
        # Para rolo
        if tipo_emb == 'rolo':
            metros_por = EmbalagemService._resolve_packaging_display_factor(item, measure_value, measure_unit)
            if embalagens > 0 and soltas > 0:
                return f"ou seja, cada {nome_emb_singular} contém {metros_por:g}m + {soltas:g}m soltos de {nome_emb_singular} aberto anteriormente."
            elif embalagens > 0:
                return f"ou seja, cada {nome_emb_singular} contém {metros_por:g}m."
            else:
                return f"ou seja, {soltas:g}m soltos de {nome_emb_singular} aberto anteriormente."
        
        # Para caixa/pacote/fardo
        if tipo_emb in ['caixa', 'pacote', 'fardo', 'saco']:
            unidades_por = float((measure_value if measure_unit == 'un' and measure_value > 0 else item.unidades_por_embalagem) or 0)
            if embalagens > 0 and soltas > 0:
                return f"ou seja, cada {nome_emb_singular} contém {unidades_por:g} unidades + {soltas:g} unidades soltas de {nome_emb_singular} aberta anteriormente."
            elif embalagens > 0:
                return f"ou seja, cada {nome_emb_singular} contém {unidades_por:g} unidades."
            else:
                return f"ou seja, {soltas:g} unidades soltas de {nome_emb_singular} aberta anteriormente."
        
        # Caso genérico (outras embalagens)
        unidades_por = float(item.unidades_por_embalagem or 0)
        if embalagens > 0 and soltas > 0:
            return f"ou seja, cada {nome_emb_singular} contém {unidades_por:g} unidades + {soltas:g} unidades soltas de {nome_emb_singular} aberta anteriormente."
        elif embalagens > 0:
            return f"ou seja, cada {nome_emb_singular} contém {unidades_por:g} unidades."
        else:
            return f"ou seja, {soltas:g} unidades soltas de {nome_emb_singular} aberta anteriormente."


# Instância global
embalagem_service = EmbalagemService()
