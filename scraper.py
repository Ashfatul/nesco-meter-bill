import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

class NescoScraper:
    def __init__(self):
        self.url = "https://customer.nesco.gov.bd/pre/panel"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
    def get_csrf_token(self):
        try:
            response = self.session.get(self.url, verify=False)
            soup = BeautifulSoup(response.text, 'html.parser')
            token_input = soup.find('input', {'name': '_token'})
            if token_input:
                return token_input.get('value')
        except Exception as e:
            print(f"Error fetching CSRF token: {e}")
        return None

    def fetch_monthly_usage(self, meter_number):
        token = self.get_csrf_token()
        if not token:
            return None
            
        data = {
            '_token': token,
            'cust_no': meter_number,
            'submit': 'মাসিক ব্যবহার'
        }
        
        try:
            response = self.session.post(self.url, data=data, verify=False)
            if response.status_code != 200:
                return None
                
            soup = BeautifulSoup(response.text, 'html.parser')
            result = {
                'meter_number': meter_number,
                'current_balance': 0.0,
                'customer_name': 'Unknown',
                'address': 'Unknown',
                'date': datetime.now().date()
            }
            
            with open("debug_monthly.html", "w", encoding="utf-8") as f:
                f.write(response.text)
                
            # Parse Customer Name, Address, and Balance from input fields
            inputs = soup.find_all('input', {'disabled': 'disabled'})
            for inp in inputs:
                val = inp.get('value', '').strip()
                # Find balance by looking at the preceding label
                parent = inp.parent
                if parent:
                    prev_label = parent.find_previous_sibling('label')
                    if prev_label:
                        label_text = prev_label.get_text(strip=True)
                        if 'অবশিষ্ট ব্যালেন্স' in label_text:
                            try:
                                result['current_balance'] = float(val)
                            except ValueError:
                                pass
                        elif 'গ্রাহকের নাম' in label_text:
                            result['customer_name'] = val
                        elif 'ঠিকানা' in label_text:
                            result['address'] = val
                        elif 'মোবাইল' in label_text:
                            result['phone'] = val
                        elif 'ফিডারের নাম' in label_text:
                            result['feeder'] = val
                        elif 'অনুমোদিত ট্যারিফ' in label_text:
                            result['tariff'] = val
                        elif 'অনুমোদিত লোড' in label_text:
                            result['load'] = val

            # Parse Monthly Usage history table
            usages = []
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                if not rows: continue
                headers = [th.get_text(strip=True) for th in rows[0].find_all(['th', 'td'])]
                if 'বছর' in headers and 'মাস' in headers:
                    for row in rows[1:]:
                        cols = row.find_all('td')
                        if len(cols) >= 13:
                            try:
                                usage = {
                                    'year': int(cols[0].get_text(strip=True)),
                                    'month': cols[1].get_text(strip=True),
                                    'total_recharge': float(cols[2].get_text(strip=True).replace(',', '')) if cols[2].get_text(strip=True) else 0.0,
                                    'used_electricity_tk': float(cols[4].get_text(strip=True).replace(',', '')) if cols[4].get_text(strip=True) else 0.0,
                                    'meter_rent': float(cols[5].get_text(strip=True).replace(',', '')) if cols[5].get_text(strip=True) else 0.0,
                                    'demand_charge': float(cols[6].get_text(strip=True).replace(',', '')) if cols[6].get_text(strip=True) else 0.0,
                                    'vat': float(cols[9].get_text(strip=True).replace(',', '')) if cols[9].get_text(strip=True) else 0.0,
                                    'total_usage_tk': float(cols[10].get_text(strip=True).replace(',', '')) if cols[10].get_text(strip=True) else 0.0,
                                    'end_month_balance': float(cols[11].get_text(strip=True).replace(',', '')) if cols[11].get_text(strip=True) else 0.0,
                                    'used_energy_kwh': float(cols[12].get_text(strip=True).replace(',', '')) if cols[12].get_text(strip=True) else 0.0,
                                }
                                usages.append(usage)
                            except Exception as e:
                                print(f"Error parsing monthly usage row: {e}")
                                continue
            result['monthly_usages'] = usages

            return result
        except Exception as e:
            print(f"Error: {e}")
            return None

    def fetch_recharge_history(self, meter_number):
        token = self.get_csrf_token()
        if not token:
            return []
            
        data = {
            '_token': token,
            'cust_no': meter_number,
            'submit': 'রিচার্জ হিস্ট্রি'
        }
        
        try:
            response = self.session.post(self.url, data=data, verify=False)
            if response.status_code != 200:
                return []
                
            soup = BeautifulSoup(response.text, 'html.parser')
            recharges = []
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                for row in rows[1:]: # skip header
                    cols = row.find_all('td')
                    if len(cols) >= 14:
                        # Extract date from col 13 and amount from col 10
                        date_str = cols[13].get_text(strip=True)
                        amount_str = cols[10].get_text(strip=True)
                        # Extract token if available
                        token_val = "Unknown"
                        a_tag = cols[2].find('a')
                        if a_tag and a_tag.has_attr('data-token'):
                            token_val = a_tag['data-token']
                            
                        try:
                            # NESCO date format: 08-JUL-2026 6:18 PM
                            parsed_date = datetime.strptime(date_str, '%d-%b-%Y %I:%M %p')
                            amount = float(amount_str.replace(',', ''))
                            energy_cost = float(cols[9].get_text(strip=True).replace(',', '')) if cols[9].get_text(strip=True) else 0.0
                            method = cols[12].get_text(strip=True)
                            status = cols[14].get_text(strip=True)
                            
                            recharges.append({
                                'date': parsed_date.strftime('%Y-%m-%d %H:%M:%S'), 
                                'amount': amount,
                                'token': token_val,
                                'energy_cost': energy_cost,
                                'method': method,
                                'status': status
                            })
                        except Exception as e:
                            print(f"Error parsing row: {e}")
                            continue
                            
            return recharges
        except Exception as e:
            print(f"Error: {e}")
            return []
