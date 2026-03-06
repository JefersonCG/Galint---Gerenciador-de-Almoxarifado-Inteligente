from galint_flask.utils.backup import save_json_backup
import time

# Create 3 test backups and show results
for i in range(3):
    data = {"i": i, "time": int(time.time())}
    path = save_json_backup(data, prefix="test_prune", keep=2)
    print("Created:", path)

print('\nAfter creation, files in instance/backups:')
import os
bkdir = os.path.join(os.getcwd(), 'instance', 'backups')
for name in sorted(os.listdir(bkdir)):
    if name.startswith('test_prune_') and name.endswith('.json'):
        print('-', name)
