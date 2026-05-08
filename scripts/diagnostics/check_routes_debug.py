from galint_flask import create_app

try:
    app = create_app()
    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    print(f"Total endpoints: {len(endpoints)}")
    if 'inventory.generate_all_barcodes' in endpoints:
        print("FOUND: inventory.generate_all_barcodes")
    else:
        print("NOT FOUND: inventory.generate_all_barcodes")
        print("Listing inventory.* endpoints:")
        for e in endpoints:
            if e.startswith('inventory.'):
                print(f" - {e}")
except Exception as e:
    print(f"Error creating app: {e}")
