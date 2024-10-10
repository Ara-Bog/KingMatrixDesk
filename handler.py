import threading
import time
from selenium import webdriver
import json
from queue import Queue
import urllib.parse
from bs4 import BeautifulSoup as bs
import requests
import passwords

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
            'default_filter': {
                'page': 1,
                'start': 0,
                'limit': 1000,
                'records': '[]'
            }
        }
    }

    def __init__(self):
        self.__driver = None
        self.__options = webdriver.ChromeOptions()
        self.__options.set_capability(
                        "goog:loggingPrefs", {"performance": "ALL"}
                    )
        self.__options.add_argument('--auto-select-certificate')
        # self.__options.binary_location = '/usr/bin/chromium-gost'

        self.__routes['functions'] = {'SOBI': self.open_sobi, 'EIS': self.open_eis}
        

    
    def __await_load(self):
        while self.__driver.execute_script("return document.readyState") != "complete":
            time.sleep(1)

    def start(self, names: list, system: str, chromium_path: str):
        if system not in self.__routes:
            yield {'code': 403, 'args': []}
            return 
        self.__result_queue = Queue()
        self.__log_queue = Queue()
        self.__names = names
        self.__options.binary_location = chromium_path

        self.__driver = webdriver.Chrome(options=self.__options)
        self.__driver.set_window_size(800, 800)
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
    
    def open_axiok(self, default_filter):
        s = requests.Session()
        server = passwords.AXIOK['server']
        try:
            s.post(f"{server}/login", data=passwords.AXIOK['auth'])
        except Exception as e:
            self.__log_queue.put({'code': 403, 'discription': str(e)})
            return
        
        roles = {'Аксиок Планирование': {'parent': None, 'roles': {}}}
        link_roles = roles['Аксиок Планирование']['roles']
        for name in self.__names:
            self.__log_queue.put({'code': 102, 'args': [name]})
            try:
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
                data = s.post(f"{server}/action/Operator/ListByOrganization", params={'_dc': current_datetime}, data=urllib.parse.urlencode(user_filter)).json()['data']
                if len(data):
                    roles_filter = {'objectId': data[0]['Id'], **default_filter}
                    data = s.post(f"{server}/action/Operator/GetOperatorRoles", params={'_dc': current_datetime}, data=urllib.parse.urlencode(roles_filter)).json()['data']
                    for role in data:
                        link_roles.append(role['Name'])    
                    self.__log_queue.put({'code': 200})            
                else:
                    self.__log_queue.put({'code': 404})
            except Exception as e:
                self.__log_queue.put({'code': 401, 'discription': str(e)})
                continue

        self.__log_queue.put({'code': 100})
        self.__driver.quit()
        self.__result_queue.put(roles)
    
    def open_eis(self, main_url: str, users_url: str, users_search_url: str, cookies: str) -> None:
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

        latest_url = users_search_url
        roles = {"ЕИС": {'parent': None, 'roles': {}}}
        for name in self.__names:
            self.__log_queue.put({'code': 102, 'args': [name]})
            try:
                login = urllib.parse.quote(name.split(' ')[0])
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
                name_user = f"{table_td[2].text} {table_td[3].text} {table_td[4].text}"
                if name.replace(" ", "").lower() != name_user.replace(" ", "").lower():
                    continue

                empty_user = False
                select_system = f"{table_td[1].find('a').text} - {table_td[0].find('span')['title']}"
                roles.setdefault(select_system, {'parent': "ЕИС", 'roles': {}})

                roles[select_system]['roles'].setdefault(table_td[5].text, [])
                
                roles[select_system]['roles'][table_td[5].text].append(name)
            
            if empty_user:
                self.__log_queue.put({'code': 404})
            else:
                self.__log_queue.put({'code': 200})

        self.__log_queue.put({'code': 100})
        self.__driver.quit()
        self.__result_queue.put(roles)

    def open_sobi(self, main_url: str, id_url: str, roles_url: str) -> None:
        try:
            self.__driver.get(main_url)
            self.__await_load()
        except Exception as e:
            self.__log_queue.put({'code': 403, 'discription': str(e)})

        roles = {}
        for name in self.__names:
            self.__log_queue.put({'code': 102, 'args': [name]})
            try:
                response_id = self.__get_response(id_url, name)
                if len(response_id['list']) > 0:
                    response_roles = self.__get_response(roles_url, response_id['list'][0]['id'])
                    self.__log_queue.put({'code': 200})
                else:
                    self.__log_queue.put({'code': 404})
            except Exception as e:
                print(e)
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

    