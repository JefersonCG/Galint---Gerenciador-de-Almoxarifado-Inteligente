"""
Migration: Adiciona tabelas de configuração de empresa e relatórios.

Este script cria as tabelas:
- empresa_config: Dados da empresa, logo, endereço, etc.
- relatorio_config: Templates e configurações de relatórios.
"""
import sys
from pathlib import Path

# Adiciona diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import EmpresaConfig, RelatorioConfig


def migrate():
    """Cria as tabelas de configuração."""
    app = create_app()
    
    with app.app_context():
        print("\n" + "="*80)
        print("MIGRATION: Tabelas de Configuração Multi-Empresa")
        print("="*80 + "\n")
        
        try:
            # Verificar se as tabelas já existem
            inspector = db.inspect(db.engine)
            tabelas_existentes = inspector.get_table_names()
            
            if 'empresa_config' in tabelas_existentes:
                print("⚠️  Tabela 'empresa_config' já existe")
            else:
                print("📋 Criando tabela 'empresa_config'...")
                EmpresaConfig.__table__.create(db.engine)
                print("✅ Tabela 'empresa_config' criada com sucesso!")
            
            if 'relatorio_config' in tabelas_existentes:
                print("⚠️  Tabela 'relatorio_config' já existe")
            else:
                print("📋 Criando tabela 'relatorio_config'...")
                RelatorioConfig.__table__.create(db.engine)
                print("✅ Tabela 'relatorio_config' criada com sucesso!")
            
            print("\n" + "="*80)
            print("✅ MIGRATION CONCLUÍDA COM SUCESSO!")
            print("="*80 + "\n")
            
            print("📝 Próximos passos:")
            print("   1. Acesse /configuracoes/empresa para configurar a empresa")
            print("   2. Acesse /configuracoes/relatorios para personalizar relatórios")
            print("   3. Na primeira execução, será exibido um Setup Wizard\n")
            
        except Exception as e:
            print(f"\n❌ ERRO na migration: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    migrate()
