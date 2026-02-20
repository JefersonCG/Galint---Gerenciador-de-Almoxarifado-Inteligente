from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Entrada, InventarioEvento
from galint_flask.services.telegram_service import TelegramService

app = create_app()
N = 5
results = []
with app.app_context():
    # buscar últimas N entradas e N ajustes, depois ordenar por data desc e pegar N
    entradas = db.session.query(Entrada).order_by(Entrada.data_entrada.desc()).limit(N).all()
    ajustes = db.session.query(InventarioEvento).order_by(InventarioEvento.data_evento.desc()).limit(N).all()

    combined = []
    for e in entradas:
        combined.append((e.data_entrada or None, 'entrada', e))
    for a in ajustes:
        combined.append((a.data_evento or None, 'ajuste', a))

    # remover sem datas e ordenar
    combined = [c for c in combined if c[0] is not None]
    combined.sort(key=lambda x: x[0], reverse=True)
    combined = combined[:N]

    summary = {'attempted': 0, 'sent': [], 'failed': []}
    for dt, kind, obj in combined:
        summary['attempted'] += 1
        if kind == 'entrada':
            eid = getattr(obj, 'id_entrada', None)
            if not eid:
                summary['failed'].append(f'entrada_missing_id_{obj}'); continue
            res = TelegramService.notify_new_entry(eid)
            if res.get('success'):
                summary['sent'].append(('entrada', eid, res.get('sent', [])))
            else:
                summary['failed'].append(('entrada', eid, res.get('error')))
        else:
            aid = getattr(obj, 'id_evento', None)
            if not aid:
                summary['failed'].append(f'ajuste_missing_id_{obj}'); continue
            res = TelegramService.notify_inventory_event(aid)
            if res.get('success'):
                summary['sent'].append(('ajuste', aid, res.get('sent', [])))
            else:
                summary['failed'].append(('ajuste', aid, res.get('error')))

    print('Resend summary:')
    print('Attempted:', summary['attempted'])
    print('Sent:', summary['sent'])
    print('Failed:', summary['failed'])
