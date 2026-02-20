from galint_flask import create_app

import traceback

app = create_app()

with app.app_context():
    client = app.test_client()
    try:
        resp = client.get('/itens/')
        print('STATUS_CODE:', resp.status_code)
        if resp.status_code == 200:
            print('Page rendered OK (200).')
        else:
            data = resp.get_data(as_text=True)
            print('Response body (truncated):\n', data[:2000])
    except Exception:
        print('Exception while requesting /itens:')
        traceback.print_exc()
