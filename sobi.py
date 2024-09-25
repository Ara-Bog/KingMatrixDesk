import threading
import time
from selenium import webdriver
import pyautogui
import json
import queue

class HandleSelfSignedCertificate:
    __get_id_url = "https://sobi.cert.roskazna.ru/poib/am/api/accounts/?page=1&limit=10&name={}&org=Управление федерального казначейства по Московской области&orderByAsc=name"
    __get_roles_url = "https://sobi.cert.roskazna.ru/poib/am/api/accounts/{}/roles/?enrichGroups=true"

    def __init__(self):
        self.driver = None
        self.options = webdriver.ChromeOptions()
        self.options.set_capability(
                        "goog:loggingPrefs", {"performance": "ALL"}
                    )
        # self.options.add_argument('--headless')
        self.options.add_argument('--auto-select-certificate')
        # self.options.add_argument('--ssl-client-certificate')
        self.options.binary_location = 'C:/Users/UFK/AppData/Local/Chromium/Application/chrome.exe'

    def open_browser(self, names):
        result_queue = queue.Queue()
        
        self.driver = webdriver.Chrome(options=self.options)
        self.driver.set_window_size(10, 10)
        t1 = threading.Thread(target=self.open_url, args=(names, result_queue))
        t2 = threading.Thread(target=self.click_enter)

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        return result_queue.get()

    def get_response(self, url:str, *args):
        script = f"""
            arguments[0](fetch('{url.format(*args)}').then(response => response.json()));
        """
        response = self.driver.execute_async_script(script)
        response_json = json.dumps(response, ensure_ascii=False)
        response = json.loads(response_json)
        return response

    def open_url(self, names, result_queue):
        self.driver.get("https://sobi.cert.roskazna.ru/")
        while self.driver.execute_script("return document.readyState") != "complete":
            time.sleep(2)
        time.sleep(15)
        roles = {}
        for name in names:
            response_id = self.get_response(self.__get_id_url, name)
            response_roles = self.get_response(self.__get_roles_url, response_id['list'][0]['id'])
            
            for role in response_roles['list']:
                roles.setdefault(role['systemName'], {})
                roles[role['systemName']].setdefault(role['roleName'], [])
                roles[role['systemName']][role['roleName']].append(name)

        self.driver.quit()
        result_queue.put(roles)

    def click_enter(self):
        time.sleep(2)
        pyautogui.press('enter')
