"""Script para corrigir ortografia no banco de dados: OFFICIAL -> OFICIAL"""
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Usuario

app = create_app()

CORRECTIONS = {
    "OFFICIAL DE MANUTENÇÃO": "OFICIAL DE MANUTENÇÃO",
    "1/2 OFFICIAL DE MANUTENÇÃO": "1/2 OFICIAL DE MANUTENÇÃO",
    "OFFICIAL DE ELÉTRICA": "OFICIAL DE ELÉTRICA",
    "1/2 OFFICIAL": "1/2 OFICIAL",
}

def main():
    with app.app_context():
        print("Buscando setores com 'OFFICIAL'...")
        
        # Buscar todos usuários com OFFICIAL no setor
        usuarios = db.session.query(Usuario).filter(
            Usuario.setor.like("%OFFICIAL%")
        ).all()
        
        print(f"Encontrados {len(usuarios)} usuarios para corrigir")
        
        updated = 0
        for user in usuarios:
            old_setor = user.setor
            new_setor = old_setor
            
            # Aplicar correções
            for wrong, correct in CORRECTIONS.items():
                if wrong in old_setor:
                    new_setor = new_setor.replace(wrong, correct)
            
            if new_setor != old_setor:
                print(f"  {user.matricula} | {user.nome}")
                print(f"     De: '{old_setor}'")
                print(f"     Para: '{new_setor}'")
                user.setor = new_setor
                updated += 1
        
        # Buscar também nos cargos
        usuarios_cargo = db.session.query(Usuario).filter(
            Usuario.cargo.like("%OFFICIAL%")
        ).all()
        
        print(f"\nEncontrados {len(usuarios_cargo)} usuarios com 'OFFICIAL' no cargo")
        
        for user in usuarios_cargo:
            old_cargo = user.cargo
            new_cargo = old_cargo
            
            for wrong, correct in CORRECTIONS.items():
                if wrong in old_cargo:
                    new_cargo = new_cargo.replace(wrong, correct)
            
            if new_cargo != old_cargo:
                print(f"  {user.matricula} | {user.nome}")
                print(f"     Cargo de: '{old_cargo}'")
                print(f"     Para: '{new_cargo}'")
                user.cargo = new_cargo
                updated += 1
        
        if updated > 0:
            print(f"\nSalvando {updated} alteracoes...")
            db.session.commit()
            print("Correcoes aplicadas com sucesso!")
        else:
            print("\nNenhuma correcao necessaria!")
        
        # Verificar resultado
        print("\nVerificando resultado...")
        check = db.session.query(Usuario).filter(
            db.or_(
                Usuario.setor.like("%OFFICIAL%"),
                Usuario.cargo.like("%OFFICIAL%")
            )
        ).count()
        
        if check == 0:
            print("Nao ha mais 'OFFICIAL' no banco de dados!")
        else:
            print(f"Ainda existem {check} ocorrencias de 'OFFICIAL'")

if __name__ == "__main__":
    main()
