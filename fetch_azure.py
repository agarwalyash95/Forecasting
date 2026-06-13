import requests

res = requests.post(
    'https://djangolearning-akf3bmh6eqauf2aq.centralindia-01.azurewebsites.net/api/chat/',
    json={'message': 'hello', 'session_id': None}
)

print(f"Status: {res.status_code}")
with open('response.html', 'w', encoding='utf-8') as f:
    f.write(res.text)
