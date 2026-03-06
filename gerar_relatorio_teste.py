"""Script para forçar a geração de um relatório de teste (útil para desenvolvimento)."""
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
    print("FORÇAR GERAÇÃO DE RELATÓRIO DE TESTE")
    print("=" * 70)
    print()
    
    # Verificar total de entradas
    total = entrada_report_service.get_total_entradas()
    print(f"📊 Total de entradas: {total}")
    print()
    
    if total < 1:
        print("❌ Nenhuma entrada encontrada no sistema!")
        sys.exit(1)
    
    # Perguntar se deseja continuar
    resposta = input("⚠️  Deseja forçar a geração de um relatório de TESTE? (s/n): ").strip().lower()
    
    if resposta != 's':
        print("❌ Operação cancelada.")
        sys.exit(0)
    
    print()
    print("📝 Gerando relatório de teste...")
    print()
    
    try:
        # Para teste, vamos gerar um relatório com as primeiras entradas disponíveis
        # (independente de serem 1000 ou não)
        ciclo_teste = 999  # Número de teste
        
        # Pegar as primeiras entradas (até 1000)
        limite = min(total, entrada_report_service.CONTADOR_CICLO)
        
        pdf_info = entrada_report_service.gerar_pdf_ciclo(
            ciclo=ciclo_teste,
            id_inicio=1,
            id_fim=limite
        )
        
        print("✅ PDF gerado com sucesso!")
        print(f"   📄 Arquivo: {pdf_info['filename']}")
        print(f"   📁 Local: {pdf_info['filepath']}")
        print(f"   📦 Entradas: {pdf_info['total_entradas']}")
        print()
        
        # Perguntar se deseja enviar para o Telegram
        enviar = input("📱 Deseja enviar para o Telegram? (s/n): ").strip().lower()
        
        if enviar == 's':
            print()
            print("📤 Enviando para o Telegram...")
            sucesso = entrada_report_service.enviar_para_telegram(pdf_info['filepath'], ciclo_teste)
            
            if sucesso:
                print("✅ PDF enviado com sucesso para os administradores!")
            else:
                print("⚠️  Não foi possível enviar o PDF. Verifique os logs.")
        else:
            print("⏭️  Envio para Telegram cancelado.")
        
        print()
        print("=" * 70)
        
    except Exception as e:
        print(f"❌ Erro ao gerar relatório: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
