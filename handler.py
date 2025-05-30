import threading
import time
from selenium import webdriver
import json
from queue import Queue
import urllib.parse
from bs4 import BeautifulSoup as bs
import requests
import passwords as psw
import os
from selenium.webdriver.chrome.service import Service
import re
import pyodbc

class HandlerRoles():
    __routes = {
        'SOBI': {
            "main_url": "https://sobi.cert.roskazna.ru/",
            "id_url": "https://sobi.cert.roskazna.ru/poib/am/api/accounts/?page=1&limit=10&name={}&org=Управление федерального казначейства по Московской области&orderByAsc=name",
            "roles_url": "https://sobi.cert.roskazna.ru/poib/am/api/accounts/{}/roles/?enrichGroups=true"
        },
        'EIS': {
            "main_url": "https://lk.zakupki.gov.ru/sso/secure",
            "users_url": "https://lk.zakupki.gov.ru/44fz/ppa/users.html",
            "users_search_url": "https://lk.zakupki.gov.ru/44fz/ppa/users.html?execution=e1s1",
            "cookies": {
                "name": "activeRole",
                "value": "CIA",
            }
        },
        'AXIOK': {
            'OpenBrowser': False,
            'default_filter': {
                'page': 1,
                'start': 0,
                'limit': 1000,
                'records': '[]'
            }
        },
        'SEDS': {
            'OpenBrowser': False,
            "sed_fio_pattern": r'FIO.*?([А-Яа-я\s]+)',
            "sed_roles_pattern": r"Roles.{5}([A-Za-z\r]+)",
        }
    }

    __chrome_versions = {
        '131.0.6778.69': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'drivers/chromedriver_131.exe'),
        '109.0.5414.173': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'drivers/chromedriver_109.exe'),
    }

    def __init__(self):
        self.__driver = None
        self.__options = webdriver.ChromeOptions()
        self.__options.set_capability(
                        "goog:loggingPrefs", {"performance": "ALL"}
                    )
        self.__options.add_argument('--auto-select-certificate')
        self.__options.add_experimental_option("excludeSwitches", ["enable-logging"])
        # self.__options.binary_location = '/usr/bin/chromium-gost'

        self.__routes['functions'] = {'SOBI': self.open_sobi, 'EIS': self.open_eis, 'AXIOK': self.open_axiok, 'SEDS': self.open_seds}

    def clean_string(self, name):
        return re.sub(r'\s+', ' ', name).strip()
    
    def __await_load(self):
        while self.__driver.execute_script("return document.readyState") != "complete":
            time.sleep(1)

    def get_supported_chrome(self) -> list:
        return list(self.__chrome_versions.keys())

    def start(self, names: list, system: str, chromium_path: str, chromium_v: str, debug=False):
        if system not in self.__routes:
            yield {'code': 403, 'args': []}
            return 
        
        self.__result_queue = Queue()
        self.__log_queue = Queue()
        self.__names = names

        if self.__routes[system].get('OpenBrowser', True):
            try:
                driver = Service(self.__chrome_versions[chromium_v])
                self.__options.binary_location = chromium_path
                self.__driver = webdriver.Chrome(service = driver, options=self.__options)
                self.__driver.set_window_size(800, 800)
            except Exception as e:
                yield {'code': 500, 'discription': str(e)}
                return 
            
        t1 = threading.Thread(target=self.__routes['functions'][system], kwargs=self.__routes[system])
        t1.start()
        
        while True:
            if not self.__log_queue.empty():
                yield self.__log_queue.get()
            elif not t1.is_alive():
                yield self.__result_queue.get()
                break
            else:
                time.sleep(0.1)

    def __get_response(self, url:str, *args) -> dict:
        script = f"""
            arguments[0](fetch('{url.format(*args)}').then(response => response.json()));
        """

        response = self.__driver.execute_async_script(script)
        response_json = json.dumps(response, ensure_ascii=False)
        response = json.loads(response_json)

        return response
    
    def open_seds(self, sed_fio_pattern: str, sed_roles_pattern:str, **kwards):
        roles = {}
        for server, db in psw.SED_DB.items():
            connection_string = f"DRIVER={{SQL Server}};SERVER={server};DATABASE={db};UID={psw.SED_CONNECT['user']};PWD={psw.SED_CONNECT['password']}"
            roles[db] = {'parent': None, 'roles': {}}
            try:
                with pyodbc.connect(connection_string) as conn:
                    cursor = conn.cursor()
                    cursor.execute(psw.SCRIPTS[db])
                    if cursor.description:
                        rows = cursor.fetchall()
                        
                        for row in rows:
                            sysname_user, data_byte, sign = row
                            data = data_byte.decode('cp1251', errors='ignore')
                            cleaned_data = re.sub(r'[^a-zA-Zа-яА-ЯёЁ\n\s]', '', data)

                            match_user = re.search(sed_fio_pattern, cleaned_data)
                            user = match_user.group(1) if match_user else None
                            user = re.sub('\s{0,}', '', str(user))
                            user = re.sub(r'(?<!^)(?=[A-ZА-Я])', ' ', user)

                            if re.search('Blocked', data):
                                continue
                            if not user:
                                self.__log_queue.put({'code': 405, 'args': [sysname_user]})
                                continue

                            user = user[2:] if user[0] in ['p', 'р', 'a', 'а'] else user
                            if user not in self.__names:
                                continue

                            match_roles = re.search(sed_roles_pattern, data)
                            role_list = match_roles.group(1).split('\r')[:-1] if match_roles else [] 
                            role_list.append(sign)
                            
                            if sysname_user:
                                if sysname_user not in roles:
                                    roles[sysname_user] = {'parent': db, 'roles': {}}
                                
                                for role in role_list:
                                    roles[sysname_user]['roles'].setdefault(role, [])
                                    roles[sysname_user]['roles'][role].append(user)
                            
            except Exception as e:
                self.__log_queue.put({'code': 401, 'discription': f'{db}: {e}'})
                continue
        
        self.__log_queue.put({'code': 100})
        self.__result_queue.put(roles)

    def open_axiok(self, default_filter, **kwards) -> None:
        default_filter = {
                'page': 1,
                'start': 0,
                'limit': 1000,
                'records': '[]'
            }
        s = requests.Session()
        server = psw.AXIOK['server']

        try:
            s.post(f"{server}/login", data=psw.AXIOK['auth'])
        except Exception as e:
            self.__log_queue.put({'code': 403, 'discription': str(e)})
            return

        roles = {'Аксиок Планирование': {'parent': None, 'roles': {}}}
        link_roles = roles['Аксиок Планирование']['roles']
        
        for name in self.__names:
            current_datetime = int(time.time() * 1000)
            user_filter = {
                'dataFilter': {
                    "Group": 2,
                    "Filters": [
                        {
                            "DataIndex": "Name",
                            "Value": name,
                            "Operand": 6
                        }
                    ]
                },
                **default_filter
            }

            try:
                data = s.post(f"{server}/action/Operator/ListByOrganization", params={'_dc': current_datetime}, json=user_filter).json()['data']
                
                if len(data):
                    roles_filter = {'objectId': data[0]['Id'], **default_filter}
                    data = s.post(f"{server}/action/Operator/GetOperatorRoles", params={'_dc': current_datetime}, json=roles_filter).json()['data']

                    for role in data:
                        link_roles.setdefault(role['Name'], [])  
                        link_roles[role['Name']].append(name)
                else:
                    self.__log_queue.put({'code': 404, 'args': [name]})
            except Exception as e:
                self.__log_queue.put({'code': 401, 'discription': str(e)})
                continue

        self.__log_queue.put({'code': 100})
        self.__result_queue.put(roles)
    
    def open_eis(self, main_url: str, users_url: str, users_search_url: str, cookies: str, **kwards) -> None:
        try:
            self.__driver.get(main_url)
            self.__await_load()
            self.__driver.add_cookie(cookies)
            self.__driver.refresh()
            self.__await_load()
            self.__driver.get(users_url)
            self.__await_load()
        except Exception as e:
            self.__log_queue.put({'code': 403, 'discription': str(e)})
            self.__driver.quit()
            self.__result_queue.put(None)
            return

        latest_url = users_search_url
        roles = {"ЕИС": {'parent': None, 'roles': {}}}
        
        for name in self.__names:
            try:
                # поиск в еис производиться только по фамиилии
                # "_" - в соби соответствует 1 любому символу
                correct_name = re.sub(r'[её]', '_', name.split(' ')[0])
                login = urllib.parse.quote(correct_name)
                script = f"""
                    arguments[0](fetch('{latest_url}', 
                    {{"body": "userLogin={login}&_userAuthorities=on&_userAuthorities=on&_userAuthorities=on&_userAuthorities=on&_userAuthorities=on&fromDate=&toDate=&_eventId_findOrganizationUsers=%D0%9D%D0%B0%D0%B9%D1%82%D0%B8&pageNumber=1&sortField=name.lastName&sortAsc=true&filterChanged=true&userId=",
                        "headers": {{
                            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                            "cache-control": "max-age=0",
                            "content-type": "application/x-www-form-urlencoded",
                            "sec-ch-ua-mobile": "?0",
                            "sec-fetch-dest": "document",
                            "sec-fetch-mode": "navigate",
                            "sec-fetch-site": "same-origin",
                            "sec-fetch-user": "?1",
                            "upgrade-insecure-requests": "1"
                        }},
                        "method": "POST",
                        "mode": "cors",
                        "credentials": "include",
                        "referrer": "{latest_url}"
                    }}).then(response => response));
                """

                latest_url = self.__driver.execute_async_script(script)['url']

                self.__driver.get(latest_url)
                self.__await_load()

                soup = bs(self.__driver.page_source, 'html.parser')
                table = soup.find('table', {'id': 'organizationUser'})
                table_tr = table.find_all('tr')
            except Exception as e:
                self.__log_queue.put({'code': 401, 'discription': str(e)})
                continue
            
            empty_user = True

            for tr in table_tr[1:]:
                table_td = tr.find_all('td')

                if table_td[0].get('id', '') == 'emptyRow':
                    break

                name_user = self.clean_string(f"{table_td[2].text}{table_td[3].text}{table_td[4].text}").lower()

                if name.replace(" ", "").lower() != name_user:
                    continue

                empty_user = False
                select_system = self.clean_string(f"{table_td[1].find('a').text} - {table_td[0].find('span')['title']}")
                roles.setdefault(select_system, {'parent': "ЕИС", 'roles': {}})

                role = self.clean_string(table_td[5].text)
                if not role:
                    role = "Полномочия отсутствуют"
                roles[select_system]['roles'].setdefault(role, [])

                roles[select_system]['roles'][role].append(name)

            if empty_user:
                self.__log_queue.put({'code': 404, 'args': [name]})

        self.__log_queue.put({'code': 100})
        self.__driver.quit()
        self.__result_queue.put(roles)

    def open_sobi(self, main_url: str, id_url: str, roles_url: str, **kwards) -> None:
        try:
            self.__driver.get(main_url)
            self.__await_load()
        except Exception as e:
            self.__log_queue.put({'code': 403, 'discription': str(e)})
            self.__driver.quit()
            self.__result_queue.put(None)
            return

        roles = {}
        for name in self.__names:
            
            try:
                # "_" - в соби соответствует 1 любому символу
                correct_name = re.sub(r'[её]', '_', name)
                response_id = self.__get_response(id_url, correct_name)
                if len(response_id['list']) > 0:
                    response_roles = self.__get_response(roles_url, response_id['list'][0]['id'])
                else:
                    self.__log_queue.put({'code': 404, 'args': [name]})
                    continue
            except Exception as e:
                self.__log_queue.put({'code': 401, 'discription': str(e)})
                continue
            
            for role in response_roles['list']:
                if len(role['groups']) == 0:
                    role['groups'].append(None)
                    
                for group in role['groups']:
                    select_system, parent = (role['systemName'], None) if group == None else (group, role['systemName'])

                    roles.setdefault(select_system, {'parent': parent, 'roles': {}})
                    roles[select_system]['roles'].setdefault(role['roleName'], [])
                    
                    roles[select_system]['roles'][role['roleName']].append(name)

        self.__log_queue.put({'code': 100})
        self.__driver.quit()
        self.__result_queue.put(roles)
