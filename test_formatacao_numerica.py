"""Script de teste para validar a nova formatação numérica nas notificações Telegram."""

import sys
import os

# Adicionar o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from galint_flask.services.telegram_service import TelegramService


def test_fmt_number():
    """Testa a função _fmt_number com vários valores."""
    
    test_cases = [
        # (valor, decimals, esperado)
        (1000, 0, "1.000"),
        (83999, 0, "83.999"),
        (503994000, 0, "503.994.000"),
        (102000, 0, "102.000"),
        (1059800, 0, "1.059.800"),
        (839800, 0, "839.800"),
        (100.0, 0, "100"),
        (1000.5, 2, "1.000,5"),
        (223.2, 2, "223,2"),
        (162.0, 2, "162"),
        (150.0, 2, "150"),
        (0.03994e+08, 0, "39.940.000"),  # Notação científica
        (5.03994e+08, 0, "503.994.000"),
        (1.0598e+06, 0, "1.059.800"),
    ]
    
    print("🔍 TESTANDO FORMATAÇÃO NUMÉRICA\n")
    print("=" * 60)
    
    all_passed = True
    for valor, decimals, esperado in test_cases:
        resultado = TelegramService._fmt_number(valor, decimals)
        passou = resultado == esperado
        
        if not passou:
            all_passed = False
            
        status = "✅" if passou else "❌"
        print(f"{status} {valor:>15} (dec={decimals}) → {resultado:>15} {'✓' if passou else f'(esperado: {esperado})'}")
    
    print("=" * 60)
    print(f"\n{'✅ TODOS OS TESTES PASSARAM!' if all_passed else '❌ ALGUNS TESTES FALHARAM!'}\n")
    
    return all_passed


def test_format_examples():
    """Mostra exemplos de formatação de notificações."""
    
    print("\n📋 EXEMPLOS DE FORMATAÇÃO DE NOTIFICAÇÕES\n")
    print("=" * 60)
    
    # Exemplo 1: PAPEL HIGIÊNICO (83.999 caixas × 6.000 un)
    print("\n📦 PAPEL HIGIÊNICO")
    print("   📦 Total de caixas: 83.999")
    print("      └─ Unidades por caixa: 6.000")
    print("   📊 Total geral: 503.994.000 unidades")
    
    # Exemplo 2: PAPEL TOALHA (102 pacotes × 1.000 un)
    print("\n📦 PAPEL TOALHA INTERFOLHAS")
    print("   📦 Total de pacotes: 102")
    print("      └─ Unidades por pacote: 1.000")
    print("   📊 Total geral: 102.000 unidades")
    
    # Exemplo 3: SACO LIXO 300 LITROS (10.598 pacotes × 100 un)
    print("\n📦 SACO LIXO 300 LITROS")
    print("   📦 Total de pacotes: 10.598")
    print("      └─ Unidades por pacote: 100")
    print("   📊 Total geral: 1.059.800 unidades")
    
    # Exemplo 4: SACO LIXO 200 LITROS (8.398 pacotes × 100 un)
    print("\n📦 SACO LIXO 200 LITROS")
    print("   📦 Total de pacotes: 8.398")
    print("      └─ Unidades por pacote: 100")
    print("   📊 Total geral: 839.800 unidades")
    
    print("\n" + "=" * 60)
    
    # Testar formatação programática
    print("\n🔬 FORMATAÇÃO PROGRAMÁTICA:")
    print(f"   83.999 caixas: {TelegramService._fmt_number(83999)}")
    print(f"   6.000 un/caixa: {TelegramService._fmt_number(6000)}")
    print(f"   Total: {TelegramService._fmt_number(83999 * 6000)} unidades")
    
    print(f"\n   10.598 pacotes: {TelegramService._fmt_number(10598)}")
    print(f"   100 un/pacote: {TelegramService._fmt_number(100)}")
    print(f"   Total: {TelegramService._fmt_number(10598 * 100)} unidades")
    
    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    # Executar testes
    passed = test_fmt_number()
    test_format_examples()
    
    sys.exit(0 if passed else 1)
