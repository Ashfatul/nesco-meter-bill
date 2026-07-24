import requests
from bs4 import BeautifulSoup

url = "https://customer.nesco.gov.bd/pre/panel"

try:
    response = requests.get(url, verify=False)
    print("Status:", response.status_code)
    soup = BeautifulSoup(response.text, 'html.parser')
    forms = soup.find_all('form')
    for idx, form in enumerate(forms):
        print(f"\n--- Form {idx} ---")
        print("Action:", form.get('action'))
        print("Method:", form.get('method'))
        inputs = form.find_all('input')
        for inp in inputs:
            print(f"Input: name='{inp.get('name')}', type='{inp.get('type')}', value='{inp.get('value')}'")
        buttons = form.find_all('button')
        for btn in buttons:
            print(f"Button: type='{btn.get('type')}', text='{btn.text.strip()}'")
            
except Exception as e:
    print("Error:", e)
