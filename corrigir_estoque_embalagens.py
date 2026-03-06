"""
Script para corrigir inconsistências no estoque de embalagens.

Sincroniza o campo estoque_embalagens com o saldo real (entradas - saídas)
para itens que usam o sistema de embalagens.
"""
from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item
from galint_flask.services.embalagem_service import EmbalagemService

app = create_app()

def corrigir_estoque_embalagens():
    """Corrige estoque_embalagens para todos os itens com sistema de embalagens."""
    
    with app.app_context():
        # Buscar todos os itens que usam sistema de embalagens
        itens = Item.query.filter(
            Item.tipo_embalagem_novo.isnot(None),
            Item.unidades_por_embalagem.isnot(None)
        ).all()
        
        print(f"\n{'='*80}")
        print(f"VERIFICANDO {len(itens)} ITENS COM SISTEMA DE EMBALAGENS")
        print(f"{'='*80}\n")
        
        correcoes = []
        
        for item in itens:
            # Verificar se usa sistema de embalagens
            if not EmbalagemService.tem_embalagem(item):
                continue
            
            # Calcular saldo real baseado em entradas/saídas
            saldo_real = item.get_saldo_atual()
            estoque_emb_atual = item.estoque_embalagens or 0
            
            # Verificar inconsistência
            if abs(estoque_emb_atual - saldo_real) > 0.01:  # Tolerância para float
                correcoes.append({
                    'codigo': item.codigo_item,
                    'descricao': item.descricao,
                    'antes': estoque_emb_atual,
                    'depois': saldo_real,
                    'diferenca': estoque_emb_atual - saldo_real
                })
        
        if not correcoes:
            print("✅ Nenhuma inconsistência encontrada!")
            return
        
        # Mostrar resumo
        print(f"⚠️  ENCONTRADAS {len(correcoes)} INCONSISTÊNCIAS:\n")
        
        for i, corr in enumerate(correcoes, 1):
            print(f"{i}. {corr['codigo']} - {corr['descricao'][:50]}")
            print(f"   Antes: {corr['antes']:.2f} | Depois: {corr['depois']:.2f} | Diferença: {corr['diferenca']:.2f}")
        
        # Confirmar correção
        print(f"\n{'='*80}")
        resposta = input("Deseja aplicar as correções? (S/N): ")
        
        if resposta.upper() != 'S':
            print("\n❌ Correção cancelada pelo usuário")
            return
        
        # Aplicar correções
        print(f"\n{'='*80}")
        print("APLICANDO CORREÇÕES...")
        print(f"{'='*80}\n")
        
        for corr in correcoes:
            item = Item.query.filter_by(codigo_item=corr['codigo']).first()
            if item:
                item.estoque_embalagens = corr['depois']
                item.estoque_unidades_soltas = 0  # Zerar soltas (assumindo que não há)
                print(f"✅ {corr['codigo']}: {corr['antes']:.2f} → {corr['depois']:.2f}")
        
        db.session.commit()
        
        print(f"\n{'='*80}")
        print(f"✅ {len(correcoes)} ITENS CORRIGIDOS COM SUCESSO!")
        print(f"{'='*80}\n")


if __name__ == "__main__":
    try:
        corrigir_estoque_embalagens()
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
