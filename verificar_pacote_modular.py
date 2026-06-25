from pathlib import Path
import re, sys
root = Path(__file__).resolve().parent
blocked_ext = {'.apk','.aab','.jks','.keystore','.db','.sqlite','.sqlite3'}
bad = []
for p in root.rglob('*'):
    if any(part in {'.venv_windows_brechorisee','play_store_upload','tools','build','.gradle','dist_brechorisee'} for part in p.parts):
        continue
    if p.is_file() and p.suffix.lower() in blocked_ext:
        bad.append(str(p.relative_to(root)))
    if p.is_file() and p.name in {'.env','keystore.properties','local.properties'}:
        bad.append(str(p.relative_to(root)))
if bad:
    print('VERIFICACAO REPROVADA')
    for item in bad:
        print('-', item)
    sys.exit(1)
print('VERIFICACAO APROVADA')
