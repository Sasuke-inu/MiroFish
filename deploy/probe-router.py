"""A small live check that never prints credentials."""
import json
import sqlite3
import urllib.request

with sqlite3.connect(
    'file:C:/Users/PC/Desktop/9-router/data/db/data.sqlite?mode=ro', uri=True
) as connection:
    key = connection.execute(
        'select key from apiKeys where isActive=1 order by createdAt limit 1'
    ).fetchone()[0]

body = json.dumps({
    'model': 'cx/gpt-5.6-luna',
    'messages': [{'role': 'user', 'content': 'Return a JSON object with ok=true and message=MiroFish model connection works.'}],
    'response_format': {'type': 'json_object'},
    'max_completion_tokens': 512,
    'stream': False,
}).encode()
request = urllib.request.Request(
    'http://127.0.0.1:20128/v1/chat/completions', data=body,
    headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'User-Agent': 'MiroFish/0.1.0'},
)
response = json.load(urllib.request.urlopen(request, timeout=120))
content = response['choices'][0]['message']['content']
assert content, 'Model returned empty content'
assert json.loads(content)['ok'] is True
print(json.dumps({'model': response.get('model'), 'content': content, 'usage': response.get('usage')}, ensure_ascii=False))
