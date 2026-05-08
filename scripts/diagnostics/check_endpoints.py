from galint_flask import create_app

app = create_app()

print("=== Endpoints de Ferramentas ===")
for rule in app.url_map.iter_rules():
    if 'ferramenta' in rule.endpoint or 'ferramenta' in rule.rule:
        print(f"{rule.endpoint:40s} -> {rule.rule}")
