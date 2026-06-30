"""
split_price_history.py
Splits the monolithic price_history.json into per-symbol files
stored in app/data/prices/{SYMBOL}.json for lazy loading in the modal.
"""
import json
import os

SRC  = os.path.join(os.path.dirname(__file__), '..', 'app', 'data', 'price_history.json')
DEST = os.path.join(os.path.dirname(__file__), '..', 'app', 'data', 'prices')

os.makedirs(DEST, exist_ok=True)

with open(SRC) as f:
    data = json.load(f)

count = 0
for category in ('stocks', 'etfs'):
    for symbol, info in data.get(category, {}).items():
        # stocks are dicts with 'prices' key; etfs are stored directly as lists
        if isinstance(info, list):
            prices = info
            name   = symbol
        else:
            prices = info.get('prices', [])
            name   = info.get('name', symbol)
        out = {
            'symbol':   symbol,
            'name':     name,
            'category': category,
            'prices':   prices,
        }
        path = os.path.join(DEST, f'{symbol}.json')
        with open(path, 'w') as f:
            json.dump(out, f, separators=(',', ':'))
        count += 1
        print(f'  {symbol}: {len(out["prices"])} days → {os.path.getsize(path)/1024:.1f} KB')

print(f'\nDone: {count} files written to {DEST}')
