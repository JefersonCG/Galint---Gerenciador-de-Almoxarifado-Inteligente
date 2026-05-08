from galint_flask.utils.barcode_photo_processor import BarcodePhotoProcessor

print("\n" + "="*60)
print("  SCANNER DE CODIGO DE BARRAS - VALIDACAO FINAL")
print("="*60)

if BarcodePhotoProcessor.is_available():
    print("\n[SUCESSO] Scanner DISPONIVEL e pronto para uso!")
    print("\nBibliotecas instaladas:")
    print("  - pyzbar: OK")
    print("  - opencv-python-headless: OK")
    print("  - Pillow: OK")
    print("\n" + "="*60)
    print("\nProximos passos:")
    print("  1. Acesse: Configuracoes -> Telegram")
    print("  2. Ative o switch 'Retiradas' para usuarios")
    print("  3. Usuario envia /scanear no Telegram")
    print("  4. Usuario envia foto do codigo de barras")
    print("\nDocumentacao: TELEGRAM_SCANNER_BARCODE.md")
    print("\n" + "="*60)
    exit(0)
else:
    missing = BarcodePhotoProcessor.get_missing_libraries()
    print(f"\n[ERRO] Scanner NAO disponivel")
    print(f"Bibliotecas faltando: {missing}")
    print("\nExecute: pip install pyzbar opencv-python-headless")
    exit(1)
