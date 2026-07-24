import requests
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings()

url = "https://customer.nesco.gov.bd/pre/panel"
s = requests.Session()
r1 = s.get(url, verify=False)
soup = BeautifulSoup(r1.text, 'html.parser')
token = soup.find('input', {'name': '_token'}).get('value')

data = {
    '_token': token,
    'cust_no': '12345678901',
    'submit': 'মাসিক ব্যবহার'
}
r2 = s.post(url, data=data, verify=False)
print("Monthly Usage Response:")
print(r2.text)

data['submit'] = 'রিচার্জ হিস্ট্রি'
r3 = s.post(url, data=data, verify=False)
print("\nRecharge History Response:")
print(r3.text)
