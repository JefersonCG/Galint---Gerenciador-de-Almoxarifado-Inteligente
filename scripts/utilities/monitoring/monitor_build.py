"""
Monitor de Build EAS - Python Version
Verifica o progresso do build e extrai links automaticamente
"""
import time
import re
from datetime import datetime, timedelta

def print_header():
    print("\n" + "=" * 70)
    print(" 🔨 MONITOR DE BUILD APK - GALINT v1.3.1")
    print("=" * 70)
    print(f"\n⏱️  Iniciado: {datetime.now().strftime('%H:%M:%S')}")
    print("📱 Plataforma: Android (APK)")
    print("🔧 Profile: preview")
    print("\n🔍 Monitorando build EAS...\n")

def format_elapsed(elapsed):
    hours = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)
    seconds = int(elapsed % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def check_build_status():
    """
    Verifica status do build.
    Em produção, leria o output do terminal ou API do EAS.
    """
    # Placeholder: retorna status simulado
    return {
        'completed': False,
        'status': 'Em fila / Processando',
        'url': None,
        'download_url': None
    }

def monitor_build(check_interval=120, max_hours=2):
    print_header()
    
    start_time = time.time()
    max_seconds = max_hours * 3600
    check_count = 0
    
    print("⏳ Aguardando conclusão do build...")
    print(f"   (Verificações a cada {check_interval}s, timeout: {max_hours}h)\n")
    
    while True:
        elapsed = time.time() - start_time
        
        if elapsed > max_seconds:
            print("\n\n" + "=" * 70)
            print("⚠️  TIMEOUT ATINGIDO")
            print("=" * 70)
            print(f"\nBuild ainda em andamento após {max_hours}h")
            print("\n💡 Verifique manualmente em: https://expo.dev")
            break
        
        check_count += 1
        elapsed_str = format_elapsed(elapsed)
        
        # Animação de progresso
        dots = "." * ((check_count % 3) + 1)
        spaces = " " * (3 - ((check_count % 3) + 1))
        
        print(f"\r⏱️  [{elapsed_str}] Check #{check_count} {dots}{spaces}", end="", flush=True)
        
        # Verificar status
        status = check_build_status()
        
        if status['completed']:
            print("\n\n" + "=" * 70)
            print("✅ BUILD CONCLUÍDO!")
            print("=" * 70)
            
            if status['url']:
                print(f"\n📱 LINK DO BUILD:")
                print(f"   {status['url']}")
            
            if status['download_url']:
                print(f"\n⬇️  DOWNLOAD DIRETO:")
                print(f"   {status['download_url']}")
            
            print("\n" + "=" * 70)
            print("🎯 PRÓXIMOS PASSOS:")
            print("   1. Baixe o APK pelo link acima")
            print("   2. Instale no celular (USB ou WhatsApp)")
            print("   3. IMPORTANTE: Limpe dados do app:")
            print("      Configurações → Apps → GALINT → Limpar dados")
            print("   4. Teste login com RONALDO + cadastro de item")
            print("=" * 70 + "\n")
            
            # Salvar informações
            with open('BUILD_INFO_v1.3.1.txt', 'w', encoding='utf-8') as f:
                f.write(f"BUILD APK GALINT v1.3.1\n")
                f.write(f"=" * 50 + "\n")
                f.write(f"Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
                f.write(f"Tempo total: {elapsed_str}\n\n")
                f.write(f"Link Build: {status['url']}\n")
                f.write(f"Download: {status['download_url']}\n\n")
                f.write(f"Correções:\n")
                f.write(f"- Bug permissão cadastro (setor=GERENTE)\n")
                f.write(f"- CadastroScreen.js + CadastroMultiploScreen.js\n")
            
            print("📄 Informações salvas em: BUILD_INFO_v1.3.1.txt\n")
            break
        
        # Aguardar próximo check
        time.sleep(check_interval)

if __name__ == "__main__":
    try:
        monitor_build(check_interval=120, max_hours=2)
    except KeyboardInterrupt:
        print("\n\n⚠️  Monitoramento interrompido pelo usuário")
        print("💡 Build continua em andamento. Verifique: https://expo.dev\n")
