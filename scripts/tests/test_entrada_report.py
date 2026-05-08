"""Script para testar o serviço de relatórios automáticos de entradas."""
import os
import sys

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Desabilitar serviços em background
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

from galint_flask import create_app
from galint_flask.services.entrada_report_service import entrada_report_service

app = create_app()

with app.app_context():
    print("=" * 70)
    print("TESTE DO SERVIÇO DE RELATÓRIOS AUTOMÁTICOS DE ENTRADAS")
    print("=" * 70)
    print()
    
    # Verificar total de entradas
    total = entrada_report_service.get_total_entradas()
    print(f"📊 Total de entradas registradas: {total}")
    print()
    
    # Verificar último ciclo gerado
    ultimo_ciclo = entrada_report_service.get_ultimo_ciclo_gerado()
    print(f"🔢 Último ciclo gerado: {ultimo_ciclo}")
    print()
    
    # Calcular próximo ciclo
    proximo_ciclo = ultimo_ciclo + 1
    entradas_necessarias = proximo_ciclo * entrada_report_service.CONTADOR_CICLO
    faltam = max(0, entradas_necessarias - total)
    
    print(f"📈 Próximo ciclo: {proximo_ciclo}")
    print(f"📦 Entradas necessárias: {entradas_necessarias}")
    print(f"⏳ Faltam: {faltam} entradas")
    print()
    
    # Verificar se deve gerar relatório
    resultado = entrada_report_service.check_e_gerar_relatorio()
    
    print("-" * 70)
    print("RESULTADO DA VERIFICAÇÃO:")
    print("-" * 70)
    
    if resultado.get("gerado"):
        print("✅ RELATÓRIO GERADO!")
        print(f"   Ciclo: {resultado['ciclo']}")
        print(f"   Range: {resultado['range']}")
        print(f"   PDF: {resultado['pdf']}")
    else:
        print("⏸️  Relatório não gerado ainda.")
        if resultado.get("erro"):
            print(f"   ❌ Erro: {resultado['erro']}")
        else:
            print(f"   Faltam {resultado.get('faltam', 0)} entradas para o próximo relatório")
    
    print()
    print("=" * 70)
