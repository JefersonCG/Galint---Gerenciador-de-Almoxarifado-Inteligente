#!/usr/bin/env python
"""
Script para corrigir ortografia das categorias no banco de dados.
Execute: python fix_categorias_ortografia.py
"""
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from galint_flask import create_app
from galint_flask.extensions import db

def fix_categorias():
    """Corrige ortografia das categorias no banco de dados."""
    app = create_app()
    
    with app.app_context():
        # Mapeamento: errado → correto
        correcoes = {
            'Material Eletrico': 'Material Elétrico',
            'Material Hidraulico': 'Material Hidráulico',
            'Material Descartavel': 'Materiais de Limpeza',
            'Material Descartável': 'Materiais de Limpeza',
            'Material Construcao': 'Material Construção',
        }
        
        total_corrigidos = 0
        
        for errado, correto in correcoes.items():
            result = db.session.execute(
                db.text("UPDATE itens SET categoria = :correto WHERE categoria = :errado"),
                {"correto": correto, "errado": errado}
            )
            count = result.rowcount
            if count > 0:
                print(f"✅ Corrigido '{errado}' → '{correto}': {count} registro(s)")
                total_corrigidos += count
        
        db.session.commit()
        
        # Mostra categorias únicas após correção
        print("\n📋 Categorias após correção:")
        result = db.session.execute(db.text("SELECT DISTINCT categoria FROM itens ORDER BY categoria"))
        for row in result:
            print(f"  • {row[0]}")
        
        print(f"\n✨ Total corrigido: {total_corrigidos} registro(s)")

if __name__ == "__main__":
    print("🔧 Corrigindo ortografia das categorias no banco de dados...\n")
    try:
        fix_categorias()
        print("\n✅ Correção concluída com sucesso!")
    except Exception as e:
        print(f"\n❌ Erro ao corrigir: {e}")
        sys.exit(1)
