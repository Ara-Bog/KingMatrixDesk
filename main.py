from PyQt5 import uic
from PyQt5.QtCore import Qt, QSettings, pyqtSignal
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtWidgets import QMessageBox, QFileDialog, QMainWindow, QApplication, QDialog, QCheckBox
from psycopg2 import connect
import sys
from datetime import datetime
import threading
# custom
from handler import HandlerRoles
import sys
import os
import passwords
import re
from xlrd import open_workbook
import requests

from PyQt5.QtCore import QTimer


SYSTEMS =  [
    ('SOBI', 'ПОИБ СОБИ'),
    ('EIS', 'ЕИС'),
    ('AXIOK', 'Аксиок Планирование'),
    ('EBP', 'ЕБП'),
    ('SEDS', 'СедЫ'),
]

# Шаблоны логов
MESSAGES = {
    100: {'type_msg': 'info', 'title': "Сбор данных в системе - {} закончен."},
    # 102: {'type_msg': 'info', 'title': "Начат сбор по пользователю - {}."},
    # 200: {'type_msg': 'success', 'title': "Данные пользователя успешно получены!"},
    201: {'type_msg': 'success', 'title': "Данные добавлены в базу данных!"},
    202: {'type_msg': 'info', 'title': "Начат сбор в системе - {}."},
    400: {'type_msg': 'error', 'title': "Ошибка добавления данных по системе {} в базу данных!"},
    401: {'type_msg': 'error', 'title': "Ошибка в получении данных пользователя!"},
    403: {'type_msg': 'error', 'title': "Запрос не может быть обработан."},
    404: {'type_msg': 'warn', 'title': "Пользователь {} не найден в подсистеме."},
    405: {'type_msg': 'warn', 'title': "Не удалось расшифровать данные пользователя {}."},
    406: {'type_msg': 'warn', 'title': "У пользователя {} отсутствуют роли."},
    500: {'type_msg': 'error', 'title': "Системная ошибка."}
}

TYPES_MSGS = {
    "info": QMessageBox.Information,
    "err": QMessageBox.Critical,
    "warn": QMessageBox.Warning
}

def show_messagebox(type_msg:str, title:str, text:str, cancel: bool = False): 
    msg = QMessageBox() 
    msg.setIcon(TYPES_MSGS[type_msg]) 

    msg.setText(text) 
    
    msg.setWindowTitle(title) 
    
    msg.setStandardButtons(QMessageBox.Ok) 

    if cancel:
        msg.addButton(QMessageBox.Cancel)
    
    return msg.exec_() == QMessageBox.Ok

class MyModel(QStandardItemModel):
    '''Модель для вывода логов'''
    def __init__(self, parent=None):
        super(MyModel, self).__init__(parent)
        self.log_symbols = {
            'info': 'ℹ',
            'error': '❌',
            'success': '✅'
        }
        self.setColumnCount(1)
        self.setHorizontalHeaderLabels(['Логи'])

    def add_data(self, data: list):
        symbol = self.log_symbols.get(data[1], data[1])
        row_msg = QStandardItem(f'{data[0]}\n{symbol} - {data[2]}\n')
        if data[3] != "":
            system_item = QStandardItem(data[3])
            row_msg.appendRow(system_item)
            
        self.insertRow(0, row_msg)

class LoaderView(QDialog):
    loadingPaused = pyqtSignal(bool)
    closeLoading = pyqtSignal()

    def __init__(self):
        super(LoaderView, self).__init__()

        ui_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'interfaces/loadView.ui')
        uic.loadUi(ui_file, self)
        self.user_initiated_close = True

    def increase(self):
        self.progressBar.setValue(self.progressBar.value() + 1)

        if self.progressBar.value() == self.progressBar.maximum():
            show_messagebox("info", "Загрузка EXCEL", "Все строки обработаны.")
            self.reset()

    def start(self, max_val):
        self.progressBar.setValue(0)
        self.progressBar.setMaximum(max_val)

    def reset(self):
        self.progressBar.setValue(0)
        self.progressBar.setMaximum(0)
        self.close()
        
    def closeEvent(self, event):
        if self.user_initiated_close:
            self.loadingPaused.emit(True)
            
            reply = show_messagebox("warn", "Подтверждение", "Вы уверены, что хотите отменить загрузку?", True)

            if reply:
                self.closeLoading.emit() 
                event.accept() 
            else:
                self.loadingPaused.emit(False)
                event.ignore()
        else:
            event.accept()  

    def reject(self):
        self.user_initiated_close = False 
        super(LoaderView, self).reject() 

    def close(self):
        self.user_initiated_close = False 
        super(LoaderView, self).close() 

class ExcelLoader(QDialog):
    callbackData = pyqtSignal(dict)
    callbackLogs = pyqtSignal(int, list, str)

    __sed_fio_pattern = r'FIO.{5}([А-Яа-я\s]+)'
    __sed_roles_pattern = r"Roles.{5}([A-Za-z\r]+)"

    def __init__(self):
        super(ExcelLoader, self).__init__()

        ui_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'interfaces/selectExcel.ui')
        uic.loadUi(ui_file, self)
        self.file_dialog.clicked.connect(self.openFileDialog)
        self.copy_script.clicked.connect(self.copyScript)

        self.loading = False
        self.loadingPause = False

        self.__loader = LoaderView()
        self.__loader.loadingPaused.connect(self.pauseLoading) 
        self.__loader.closeLoading.connect(self.closeLoading) 
        for item in passwords.SCRIPTS.items():
            self.selectSystem.addItem(*item)

        self.output_data = None
        self.list_users = set()
        self.calledMethod = None
        self.select_file = None
        self.current_iteration = 0
        self.total_iterations = 0

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                filePath = url.toLocalFile()
                self.excelPath.setText(filePath)

    def pauseLoading(self, status):
        self.loadingPause = status
        if not status: self.readExcel()

    def closeLoading(self):
        self.output_data = None
        self.list_users = set()
        self.calledMethod = None
        self.select_sheet_file = None
        self.current_iteration = -1
        self.total_iterations = 0
        self.loading = False

    def openFileDialog(self):
        filePath, _ = QFileDialog.getOpenFileName(self, "Выбор EXCEL файла", self.excelPath.text(), "Excel Files (*.xls)")
        if filePath:
            self.excelPath.setText(filePath)

    def copyScript(self):
        clipboard = QApplication.clipboard()

        text = "Скрипт скопирован в буфер обмена"
        buffer = ''
        cur_index = self.selectSystem.currentIndex()
        if cur_index == -1:
            text = "Не выбрана ни одна подсистема"
        else:
            buffer = self.selectSystem.itemData(cur_index)
            clipboard.setText(buffer)
        
        show_messagebox("info" if buffer else 'warn', "Копирование скрипта", text)
    
    def loadSUFD(self):
        user = self.select_sheet_file.cell_value(self.current_iteration, 0)
        sysname_user = self.select_sheet_file.cell_value(self.current_iteration, 1)
        role_list = self.select_sheet_file.cell_value(self.current_iteration, 2).split('|')
        
        return sysname_user, user, role_list

    def loadSED(self):
        sysname_user = self.select_sheet_file.cell_value(self.current_iteration, 0)
        sign = self.select_sheet_file.cell_value(self.current_iteration, 2)

        binary_data = bytes.fromhex(self.select_sheet_file.cell_value(self.current_iteration, 1))
        data = binary_data.decode('cp1251', errors='ignore')


        match_user = re.search(self.__sed_fio_pattern, data)
        user = match_user.group(1) if match_user else None

        if re.search('Blocked', data):
            return None, user, []

        match_roles = re.search(self.__sed_roles_pattern, data)
        role_list = match_roles.group(1).split('\r')[:-1] if match_roles else [] 
        role_list.append(sign)

        return sysname_user, user, role_list 

    def loadCKS(self):
        sysname_user = self.select_sheet_file.cell_value(self.current_iteration, 0)
        user = self.select_sheet_file.cell_value(self.current_iteration, 1)
        oed = self.select_sheet_file.cell_value(self.current_iteration, 2)
        sysadmin = self.select_sheet_file.cell_value(self.current_iteration, 3)
        admkompl = self.select_sheet_file.cell_value(self.current_iteration, 4)

        role_list = []

        if sysadmin:
            role_list.append('Системный администратор')
        if admkompl:
            role_list.append('Администратор комплекса')
        if oed:
            role_list.append('Работа с ЭОД (РКЦ/Банком). Настройка автоматов комплекса')

        return sysname_user, user, role_list 

    def accept(self):
        select_system = self.selectSystem.currentText()
        if not select_system:
            show_messagebox("warn", "Загрузка EXCEL", "Не выбрана ни одна подсистема.")
            return
        if not os.path.exists(self.excelPath.text()):
            show_messagebox("err", "Загрузка EXCEL", "Неверный путь к файлу.")
            return
        try:
            match select_system:
                case 'ASFK' | 'SUFD':
                    self.calledMethod = self.loadSUFD
                    self.current_iteration = 1
                case 'SED1K' | 'SED2K' | 'SED3K':
                    self.calledMethod = self.loadSED
                    self.current_iteration = 0
                case 'CKS':
                    self.calledMethod = self.loadCKS
                    self.current_iteration = 0
                case _:
                    self.current_iteration = 1

            self.output_data = {select_system: {'parent': None, 'roles': {}}}
            self.select_sheet_file = open_workbook(self.excelPath.text()).sheet_by_index(0)
            self.total_iterations = self.select_sheet_file.nrows
            self.__loader.start(self.select_sheet_file.nrows - 1)
            self.loading = True
            self.loadingPause = False
            self.callbackLogs.emit(202, [select_system], '')
            self.readExcel() 
            self.__loader.show()
        except Exception as e:
            self.callbackLogs.emit(401, None, str(e))
            show_messagebox("err", "Ошибка загрузки", str(e))

    def readExcel(self):
        if not self.loading or self.loadingPause: return 
        if self.current_iteration < self.total_iterations:
            try:
                login, user, role_list = self.calledMethod()

                if login:
                    if login not in self.output_data:
                        self.output_data[login] = {'parent': self.selectSystem.currentText(), 'roles': {}}

                    self.list_users.add(user)
                    for role in role_list:
                        self.output_data[login]['roles'][role] = [user]

                self.__loader.increase()
                self.current_iteration += 1
                QTimer.singleShot(0, self.readExcel)
            except Exception as e:
                self.callbackLogs.emit(401, None, str(e))
                show_messagebox("err", "Ошибка загрузки", str(e))
                self.closeLoading()
                self.__loader.reset()
        else:
            self.callbackData.emit({'data': self.output_data, 'users': self.list_users, 'system': self.selectSystem.currentText()})
            self.closeLoading()
        
class Ui(QMainWindow):
    def __init__(self, handler):
        super(Ui, self).__init__()
        self.conn_auth = connect(
            database='auth_db', **passwords.DB
        )

        self.__excel_loader = ExcelLoader()
        self.__excel_loader.callbackData.connect(self.loadExcel) 
        self.__excel_loader.callbackLogs.connect(lambda code, args, err: self.addLogs(code, args, err)) 
        self.list_users = {}
        self.select_users = []
        ui_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'interfaces/MainWindow.ui')
        uic.loadUi(ui_file, self)

        self.systems_mapping = {}
        self.setup_dynamic_checkboxes()
        self.selectDepartments.currentIndexChanged.connect(self.onChangeDepartment)
        self.submit.clicked.connect(self.get_data_tree)
        self.getDefaultData()
        self.model = MyModel()
        self.outView.setModel(self.model)
        self.clear_logs.clicked.connect(lambda: self.model.removeRows(0, self.model.rowCount()))
        self.load_excel.clicked.connect(lambda: self.__excel_loader.show())
        self.file_dialog.clicked.connect(self.openFileDialog)
        self.callAPI.clicked.connect(self.sync_ldap_users)
        self.handler = handler
        self.selectVersionBrowser.addItems(handler.get_supported_chrome())
        self.selectVersionBrowser.setCurrentIndex(0)
        self.cache = []
        self.show()
    
    def setup_dynamic_checkboxes(self):
        """Автоматически распределяем чекбоксы по checkboxLayout"""
        
        columns_per_row = 5  # Максимальное количество чекбоксов в строке
        
        for i, (system_code, display_name) in enumerate(SYSTEMS):
            checkbox = QCheckBox(display_name)
            checkbox.setCursor(Qt.PointingHandCursor)
            
            row = i // columns_per_row
            col = i % columns_per_row
            
            self.checkboxLayout.addWidget(checkbox, row, col)
            self.systems_mapping[system_code] = checkbox

    def get_checked_systems(self):
        return [system for system, checkbox in self.systems_mapping.items() 
                if checkbox.isChecked()]
    
    def loadExcel(self, data):
        roles = data['data'] # dict
        users = data['users'] # set

        id_system = self.addNewSystem(data['system'])
        with self.conn_auth.cursor() as cursor_matrix:
            cursor_matrix.execute('''
                UPDATE "matrix_userroles" 
                SET "isChecked" = FALSE  
                WHERE "system_id" IN (SELECT id FROM "matrix_systems" WHERE "parent_id" = %s)
            ''', (id_system,))
            
        with self.conn_auth.cursor() as cursor_auth:
            cursor_auth.execute('''
                        SELECT id, name 
                        FROM "Auth_LDAP_customuser" 
                        WHERE name IN %s
                        ''', (tuple(users), ))
            
            self.list_users.clear()
            self.select_users.clear()
            for id, name in cursor_auth.fetchall():
                self.select_users.append(name)
                self.list_users[name] = id

        t1 = threading.Thread(target=self.restructurData, args=(roles,))
        t1.start()

    def openFileDialog(self):
        filePath, _ = QFileDialog.getOpenFileName(self, "Путь к браузеру", self.browserPath.text(), "Executable Files (*.exe *.bin *.sh)")
        if filePath:
            self.browserPath.setText(filePath)

    def setListEmpoyees(self, department_id: int):
        self.selectEmployee.clear()
        cursor = self.conn_auth.cursor()
        cursor.execute('''SELECT id, name FROM "Auth_LDAP_customuser" WHERE department_id = %s ORDER BY name''', (department_id,))
        self.list_users.clear()
        self.selectEmployee.addItem('Все', 0)
        self.selectEmployee.setCurrentIndex(0)
        for id, name in cursor.fetchall():
            self.list_users[name] = id
            self.selectEmployee.addItem(name, id)
            
        cursor.close()

    def onChangeEmployee(self, text):
        if text == '':
            self.selectEmployee.setCurrentIndex(0)

    def onChangeDepartment(self, index):
        self.setListEmpoyees(self.selectDepartments.itemData(index))
        
    def getDefaultData(self):
        settings = QSettings("Matrix", "Settings")
        self.browserPath.setText(settings.value("browserPath", ""))

        self.selectEmployee.clear()
        cursor_auth = self.conn_auth.cursor()
        cursor_auth.execute('''SELECT id, name FROM "Auth_LDAP_departments" ORDER BY "sortBy"''')
        self.selectDepartments.addItem("Все отделы", 0)
        self.selectDepartments.setCurrentIndex(0)
        for id, name in cursor_auth.fetchall():
            self.selectDepartments.addItem(name, id)
        cursor_auth.close()

    def addLogs(self, code, title_args = [""], discription=""):
        msg = MESSAGES[code]
        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self.model.add_data([now, msg['type_msg'], msg['title'].format(*title_args), discription])

    def getAllUsers(self):
        cursor = self.conn_auth.cursor()
        out = []
        cursor.execute('''SELECT id, name FROM "Auth_LDAP_customuser" WHERE is_superuser = False''')
        self.list_users.clear()
        for id, name in cursor.fetchall():
            self.list_users[name] = id
            out.append(name)
        return out

    def get_data_tree(self):
        if self.selectDepartments.currentIndex() == 0:
            self.select_users = self.getAllUsers()
        elif self.selectEmployee.currentIndex() == 0:
            self.select_users = [self.selectEmployee.itemText(i+1) for i in range(self.selectEmployee.count() - 1)]
        else:
            self.select_users = [self.selectEmployee.currentText()]
        list_systems = self.get_checked_systems()
        if not list_systems:
            if not show_messagebox("info", "Подтвердите действие", "Не выбрана ни одна подсистема. Поиск будет производится по всем имеющимся.", True):
                return
            list_systems = self.systems_mapping.keys()
        t1 = threading.Thread(target=self.process_logs, args=(list_systems,))
        t1.start()

    def process_logs(self, list_systems):
        for system_el in list_systems:
            self.addLogs(202, [system_el], '')

            next_is_data = False
            for log in handler.start(self.select_users, system_el, self.browserPath.text(), self.selectVersionBrowser.currentText()):
                if next_is_data:
                    if log:
                        self.restructurData(log)
                elif log['code'] == 100:
                    next_is_data = True
                    self.addLogs(100, [system_el], '')
                else:
                    self.addLogs(log['code'], log.get('args', []), log.get('discription', ""))
    
    def sync_ldap_users(self):
        url = passwords.API_LDAP
        try:
            response = requests.post(url)
            response.raise_for_status()
            show_messagebox('info', 'Выполнено', f'Пользователи успешно обновлены!\n{response.json()}')
            print('Response:', response.json()) 
        except requests.exceptions.RequestException as e:
            show_messagebox('err', 'Ошибка', f'Ошибка запроса сервера: {e}')

    def restructurData(self, data: dict):
        counter = {'check': 0, 'create': 0, 'errors': 0, 'undefined': 0}
        list_systems = {}
        systems_cleared = []

        for key in data:
            counter['check'] += 1
            updated_users = set()
            added_data = {'id': None, 'name': key, 'parent': None}
            id_parent = None

            try:
                name_parent = data[key]['parent']

                if name_parent is not None:
                    id_parent = list_systems.get(name_parent, {}).get('id', None)
                    if id_parent is None:
                        id_parent = self.addNewSystem(name_parent)
                        list_systems.update({name_parent: {'id': id_parent, 'name': name_parent, 'parent': None}})
                    added_data['parent'] = id_parent

                added_data['id'] = self.addNewSystem(key, id_parent)
                
                select_system_id = id_parent if id_parent else added_data['id']

                if select_system_id not in systems_cleared:
                    self.setDeleteFlag(select_system_id)
                    systems_cleared.append(select_system_id)
                
                list_systems.update({key: added_data})

                # добавление роли пользователю
                id_system = added_data['id']
                counter['check'] -= 1
                for role in data[key]['roles']:
                    if not role:
                        continue
                    role_id = self.addNewRole(role) 

                    for user in data[key]['roles'][role]:
                        counter['check'] += 1
                        id_user = self.list_users.get(user, -1)
                        if id_user == -1:
                            counter['undefined'] += 1
                            continue
                        updated_users.add(id_user)
                        relation = self.addUserRoles(id_user, role_id, id_system)
                        if relation:
                            counter['create'] += 1
                self.addLogsMatrix(updated_users, added_data['id'])
            except Exception as e:
                print("ERROR restructurData:", e)
                counter['errors'] += 1
                self.addLogs(400, [key], str(e))
        count_delete = self.deleteInactiveRoles()
        self.addLogs(201, [], f'Общее количество - {counter["check"]}; Создано - {counter["create"]}; Ошибок - {counter["errors"]}; Не найден пользователь - {counter["undefined"]}; Удалено полномочий - {count_delete}')
        self.conn_auth.commit()

    def deleteInactiveRoles(self):
        with self.conn_auth.cursor() as cursor_matrix:
            cursor_matrix.execute('''
                DELETE FROM "matrix_userroles" 
                WHERE "isChecked" = FALSE
            ''', ())

            data = cursor_matrix.rowcount
        return data

    def setDeleteFlag(self, id_system: str):
        with self.conn_auth.cursor() as cursor_matrix:
            cursor_matrix.execute('''
                UPDATE "matrix_userroles" 
                SET "isChecked" = FALSE  
                WHERE "user_id" IN %s
                                AND ("system_id" = %s
                                OR "system_id" IN (SELECT id FROM "matrix_systems" WHERE "parent_id" = %s))
            ''', (tuple(self.list_users[name] for name in self.select_users), id_system, id_system))

    def addLogsMatrix(self, users, system):
        with self.conn_auth.cursor() as cursor_matrix:
            cursor_matrix.execute('''
                DELETE FROM "matrix_logupdates"  
                WHERE "user_id" = ANY(%s::int[])  AND "system_id" = %s
            ''', (list(users), system))
            cursor_matrix.execute('''
                INSERT INTO "matrix_logupdates" ("user_id", "system_id", "date_msg") 
                SELECT unnest(%s::int[]), %s, NOW()
            ''', (list(users), system))
            data = cursor_matrix.rowcount

        return data
    
    def addUserRoles(self, id_user, id_role, id_system):
        with self.conn_auth.cursor() as cursor_matrix:
            cursor_matrix.execute('''
                SELECT id FROM "matrix_userroles" WHERE "user_id" = %s AND "role_id" = %s AND "system_id" = %s
            ''', (id_user, id_role, id_system))
                
            data = cursor_matrix.fetchone()
            if data:
                cursor_matrix.execute('''
                    UPDATE "matrix_userroles" 
                    SET "isChecked" = TRUE 
                    WHERE "id" = %s
                ''', (data,))
                return None
            else:
                cursor_matrix.execute('''
                    INSERT INTO "matrix_userroles" ("user_id", role_id, "system_id", "isChecked") 
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                ''', (id_user, id_role, id_system, True))
                
                data = cursor_matrix.fetchone()
            return data[0]

    def addNewRole(self, role):
        with self.conn_auth.cursor() as cursor_matrix:
            # Сначала проверяем, существует ли роль
            cursor_matrix.execute('''
                SELECT id FROM "matrix_roles" WHERE name = %s
            ''', (role,))
            
            data = cursor_matrix.fetchone()
            
            if data is None:
                cursor_matrix.execute('''
                    INSERT INTO "matrix_roles" (name) 
                    VALUES (%s)
                    RETURNING id
                ''', (role,))
                data = cursor_matrix.fetchone()
        self.conn_auth.commit()

        return data[0]

    def addNewSystem(self, system_name, id_parent=None):
        with self.conn_auth.cursor() as cursor_matrix:
            # Сначала проверяем, существует ли система
            if id_parent:
                cursor_matrix.execute('''
                    SELECT id FROM "matrix_systems" WHERE name = %s AND parent_id = %s
                ''', (system_name, id_parent))
            else:
                cursor_matrix.execute('''
                    SELECT id FROM "matrix_systems" WHERE name = %s AND parent_id IS NULL
                ''', (system_name,))
            
            data = cursor_matrix.fetchone()
            if data is None:
                cursor_matrix.execute('''
                    INSERT INTO "matrix_systems" (name, parent_id) 
                    VALUES (%s, %s)
                    RETURNING id
                ''', (system_name, id_parent))
                
                data = cursor_matrix.fetchone()
        self.conn_auth.commit()
        
        return data[0]
    
    def closeEvent(self, event):
        self.conn_auth.close()
        settings = QSettings("Matrix", "Settings")
        settings.setValue("browserPath", self.browserPath.text())
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    handler = HandlerRoles()
    ui = Ui(handler)
    sys.exit(app.exec_())
