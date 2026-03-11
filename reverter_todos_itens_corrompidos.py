#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Reverte TODOS os 36 itens que foram incorretamente "corrigidos" pelo agente.
O agente aplicou lógica de sync ERRADA que corrupta itens usando novo sistema de embalagens.
"""

import sys
from app import app
from galint_flask.extensions import db
from galint_flask.models import Item

# IDs dos itens corrompidos (do log de corrigir_sincronizacao_embalagens.py)
CORRUPTED_ITEMS = [
    '7891323113965',  # TINTA BRANCA EMBORRACHADA METALEX 18Litros (JA REVERTIDO)
    '7891323113200',  # DILUENTE AGUARAZ MINERAL METALEX 18Litros
    '7891323113255',  # TINTA ALUMÍNIO INCOLOR METALEX 18Litros
    '7891323113262',  # TINTA ALUMÍNIO METÁLICA METALEX 18Litros
    '7891323112999',  # DILUENTE LAC.A.BRILHO METALEX 18Litros
    '7891323113033',  # TINTA PRETO EMBORRACHADA METALEX 18Litros
    '7891323113040',  # TINTA VERDE EMBORRACHADA METALEX 18Litros
    '7891323113019',  # TINTA ALUMÍNIO GRAFITE METALEX 18Litros
    '7910000054501',  # GAXETA CHAPA PLANA 1,5MM
    '7891323113057',  # TINTA AZUL EMBORRACHADA METALEX 18Litros
    '7891323113088',  # TINTA CINZA EMBORRACHADA METALEX 18Litros
    '7891323113026',  # TINTA PRETO GRAFITE METALEX 18Litros
    '7891323113248',  # TINTA ALUMÍNIO BRILHO METALEX 18Litros
    '7891323113118',  # TINTA PRETO FOSCO METALEX 18Litros
    '7898408690272',  # REBITE CEGO 5/32 X 3/16 COMP. 7,00 ARCO IRIS
    '7891323113187',  # TINTA PRETO OPACO METALEX 18Litros
    '7891323113064',  # TINTA VERMELHA EMBORRACHADA METALEX 18Litros
    '7891323113095',  # TINTA CROMADO PRATA METALEX 18Litros
    '7891323113071',  # TINTA AMARELA EMBORRACHADA METALEX 18Litros
    '7910000054402',  # GAXETA ENROLADA C/ EM GRAFITE P/ FLANGE 1"1/2
    '7891323113101',  # TINTA CROMADO PRETO METALEX 18Litros
    '7891323113149',  # TINTA ALUMÍNIO OURO METALEX 18Litros
    '7891323113002',  # TINTA ALUMÍNIO FOSCO METALEX 18Litros
    '7910000052002',  # CHAPA DE BRONZE SAE-111 ENCDR.0,8M X 0,7M- ESP.0,40MM
    '7910000054105',  # GAXETA FITA TEFLON 3MM 25M
    '7910000050701',  # PANO MANTA CRU 1,50L- 5KG INDUSTRIAL
    '7891323113217',  # MASSA EPOXI UNIVERSAL METALEX 18Kg
    '7910000054303',  # GAXETA ENROLADA C/ EM GRAFITE P/ FLANGE 4"
    '7891323113156',  # TINTA CROMADO AZUL METALEX 18Litros
    '7910000054304',  # GAXETA ENROLADA C/ EM GRAFITE P/ FLANGE 6"
    '7910000054401',  # GAXETA ENROLADA C/ EM GRAFITE P/ FLANGE 1"
    '7910000054502',  # GAXETA CHAPA PLANA 2,5MM
    '7891323113173',  # TINTA CROMADO VERMELHO METALEX 18Litros
    '7891323113194',  # TINTA CROMADO VERDE METALEX 18Litros
    '7891323113163',  # TINTA CROMADO DOURADO METALEX 18Litros
    '7891323113125',  # TINTA VERDE GRAFITE METALEX 18Litros
]


def reverter_item(codigo: str) -> bool:
    """
    Reverte um item para seu estado anterior calculando do get_saldo_atual().
    
    LÓGICA CORRETA DE REVERSÃO:
    - Se o item tem estoque_embalagens > 20 e estoque_unidades_soltas == 0:
      --> Foi "corrigido" incorretamente
      --> get_saldo_atual() retorna valor em LITROS (ou unidade base)
      --> Precisa dividir por unidades_por_embalagem para obter número de embalagens
    """
    item = Item.query.filter_by(codigo_item=codigo).first()
    if not item:
        print(f"AVISO: Item {codigo} nao encontrado!")
        return False
    
    # Verificar se usa sistema de embalagens
    if not item.unidades_por_embalagem or item.unidades_por_embalagem <= 0:
        print(f"SKIP: Item {codigo} nao usa sistema de embalagens")
        return False
    
    # Capturar estado atual
    saldo_antes = item.get_saldo_atual()
    emb_antes = item.estoque_embalagens
    soltas_antes = item.estoque_unidades_soltas
    
    # Detectar se foi corrompido (estoque_embalagens muito alto, unidades_soltas = 0)
    if emb_antes > 0 and soltas_antes == 0 and emb_antes > 20:
        # PROVAVEL CORRUPCAO!
        # O get_saldo_atual() retorna valor correto em litros
        # Precisamos recalcular embalagens e soltas
        
        total_unidades = saldo_antes
        unid_por_emb = item.unidades_por_embalagem
        
        # Calcular embalagens fechadas e unidades soltas
        embalagens_fechadas = int(total_unidades // unid_por_emb)
        unidades_soltas = total_unidades % unid_por_emb
        
        item.estoque_embalagens = float(embalagens_fechadas)
        item.estoque_unidades_soltas = unidades_soltas
        
        db.session.commit()
        
        print(f"\nREVERTIDO: {codigo}")
        print(f"  Nome: {item.nome}")
        print(f"  Antes: {emb_antes} emb + {soltas_antes} soltas")
        print(f"  Depois: {item.estoque_embalagens} emb + {item.estoque_unidades_soltas} soltas")
        print(f"  Saldo (litros): {item.get_saldo_atual()}")
        
        return True
    else:
        print(f"OK: {codigo} - Valores parecem corretos (emb={emb_antes}, soltas={soltas_antes})")
        return False


if __name__ == '__main__':
    with app.app_context():
        print("="*80)
        print("REVERTENDO TODOS OS ITENS CORROMPIDOS")
        print("="*80)
        print(f"\nTotal de itens a processar: {len(CORRUPTED_ITEMS)}")
        print()
        
        revertidos = 0
        ok = 0
        erros = 0
        
        for codigo in CORRUPTED_ITEMS:
            try:
                if reverter_item(codigo):
                    revertidos += 1
                else:
                    ok += 1
            except Exception as e:
                print(f"ERRO ao reverter {codigo}: {e}")
                erros += 1
        
        print("\n" + "="*80)
        print("RESUMO")
        print("="*80)
        print(f"  Revertidos: {revertidos}")
        print(f"  Ja corretos: {ok}")
        print(f"  Erros: {erros}")
        print(f"  Total: {len(CORRUPTED_ITEMS)}")
        print("="*80)
