"""Script para descobrir o chat_id de grupos do Telegram."""

import requests
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    print("❌ ERRO: TELEGRAM_BOT_TOKEN não encontrado no arquivo .env")
    exit(1)

print("\n" + "=" * 80)
print("DESCOBRINDO CHAT_ID DE GRUPOS TELEGRAM")
print("=" * 80)
print("\n📋 INSTRUÇÕES:")
print("   1. Adicione o bot ao grupo (se ainda não adicionou)")
print("   2. Torne o bot ADMINISTRADOR do grupo")
print("   3. Envie uma mensagem no grupo mencionando o bot")
print("      Exemplo: @nome_do_bot olá")
print("   4. Execute este script")
print("\n" + "=" * 80)

try:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    response = requests.get(url)
    data = response.json()
    
    if not data.get("ok"):
        print(f"\n❌ ERRO: {data.get('description', 'Erro desconhecido')}")
        exit(1)
    
    updates = data.get("result", [])
    
    if not updates:
        print("\n⚠️  NENHUMA ATUALIZAÇÃO ENCONTRADA")
        print("    Certifique-se de:")
        print("    1. O bot foi adicionado ao grupo")
        print("    2. O bot é administrador do grupo")
        print("    3. Alguém enviou uma mensagem recente no grupo")
        exit(0)
    
    print(f"\n✅ Encontradas {len(updates)} atualizações\n")
    
    groups_found = {}
    
    for update in updates:
        # Verifica mensagens em grupos
        if "message" in update:
            message = update["message"]
            chat = message.get("chat", {})
            
            if chat.get("type") in ["group", "supergroup"]:
                chat_id = chat.get("id")
                chat_title = chat.get("title", "Sem título")
                
                if chat_id not in groups_found:
                    groups_found[chat_id] = {
                        "title": chat_title,
                        "type": chat["type"],
                        "last_message": message.get("text", "")
                    }
    
    if not groups_found:
        print("❌ NENHUM GRUPO ENCONTRADO NAS ATUALIZAÇÕES")
        print("   Envie uma mensagem em algum grupo onde o bot está presente")
        exit(0)
    
    print("📱 GRUPOS ENCONTRADOS:")
    print("=" * 80)
    
    for chat_id, info in groups_found.items():
        print(f"\n🔹 Grupo: {info['title']}")
        print(f"   Chat ID: {chat_id}")
        print(f"   Tipo: {info['type']}")
        if info['last_message']:
            print(f"   Última mensagem: {info['last_message'][:50]}...")
        
        print(f"\n   💾 Use este Chat ID para cadastrar no sistema:")
        print(f"   {chat_id}")
        print("   " + "-" * 76)
    
    print("\n" + "=" * 80)
    print("✅ PRÓXIMO PASSO:")
    print("   Acesse: Sistema Web → Configurações → Telegram → Grupos")
    print("   Cadastre o grupo usando o Chat ID acima")
    print("=" * 80 + "\n")

except requests.exceptions.RequestException as e:
    print(f"\n❌ ERRO DE CONEXÃO: {e}")
    print("   Verifique sua conexão com a internet")
except Exception as e:
    print(f"\n❌ ERRO INESPERADO: {e}")
