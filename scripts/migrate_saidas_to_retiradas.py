import os
import sys
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.getcwd())

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Saida, RetiradaFerramenta, Item

app = create_app()


def parse_args():
    p = argparse.ArgumentParser(description='Migrar saídas de ferramentas para retiradas_ferramentas')
    p.add_argument('--since', help='Data inicial (YYYY-MM-DD) para buscar saídas', default=None)
    p.add_argument('--saida-id', help='ID específico de saída para migrar', type=int)
    p.add_argument('--dry-run', action='store_true', help='Mostrar ações sem gravar no banco')
    return p.parse_args()


with app.app_context():
    args = parse_args()

    query = Saida.query

    if args.saida_id:
        query = query.filter(Saida.id_saida == args.saida_id)
    elif args.since:
        try:
            dt = datetime.strptime(args.since, '%Y-%m-%d')
            query = query.filter(Saida.data_saida >= dt)
        except Exception as e:
            print('Data inválida:', e)
            sys.exit(2)
    else:
        # padrão: últimas 7 dias
        dt = datetime.utcnow() - timedelta(days=7)
        query = query.filter(Saida.data_saida >= dt)

    saidas = query.order_by(Saida.data_saida.desc()).limit(500).all()

    print(f'Found {len(saidas)} saida(s) to inspect')

    created = 0
    for s in saidas:
        item = Item.query.filter_by(codigo_item=s.codigo_item).first()
        if not item:
            print(f'Saida {s.id_saida}: item {s.codigo_item} não encontrado, pulando')
            continue
        cat = (item.categoria or '').lower()
        if 'ferrament' not in cat:
            print(f'Saida {s.id_saida}: categoria "{item.categoria}" não é de ferramenta, pulando')
            continue
        # Verificar duplicata: existe retirada com mesmo codigo, matricula e data_retirada dentro de 1 dia?
        window_start = s.data_saida - timedelta(days=1)
        window_end = s.data_saida + timedelta(days=1)
        dup = (
            RetiradaFerramenta.query
            .filter(RetiradaFerramenta.codigo_item == s.codigo_item)
            .filter(RetiradaFerramenta.matricula == s.matricula)
            .filter(RetiradaFerramenta.data_retirada >= window_start)
            .filter(RetiradaFerramenta.data_retirada <= window_end)
            .first()
        )
        if dup:
            print(f'Saida {s.id_saida}: já existe retirada correspondente (id={dup.id}), pulando')
            continue

        print(f'Saida {s.id_saida}: migrando -> RetiradaFerramenta(codigo={s.codigo_item}, matricula={s.matricula}, qtd={s.quantidade}, data={s.data_saida})')
        if not args.dry_run:
            r = RetiradaFerramenta(
                codigo_item=s.codigo_item,
                matricula=s.matricula,
                quantidade=int(max(1, round(float(s.quantidade or 1)))),
                local_servico=s.local_servico,
                observacao=s.observacao,
                status='em_uso',
            )
            db.session.add(r)
            created += 1

    if not args.dry_run and created > 0:
        db.session.commit()
        print(f'Criadas {created} retiradas.')
    else:
        print('Nenhuma alteração gravada (dry-run ou 0 criadas).')
