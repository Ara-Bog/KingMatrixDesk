from PyQt5 import uic
from PyQt5.QtCore import Qt, QSettings, pyqtSignal
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtWidgets import QMessageBox, QFileDialog, QMainWindow, QApplication, QDialog, QDialogButtonBox
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

from PyQt5.QtCore import QTimer

'Шаблоны логов'
MESSAGES = {
    100: {'type_msg': 'info', 'title': "Сбор данных в системе - {} закончен."},
    102: {'type_msg': 'info', 'title': "Начат сбор по пользователю - {}."},
    200: {'type_msg': 'success', 'title': "Данные пользователя успешно получены!"},
    201: {'type_msg': 'success', 'title': "Данные добавлены в базу данных!"},
    202: {'type_msg': 'info', 'title': "Начат сбор в системе - {}."},
    400: {'type_msg': 'error', 'title': "Ошибка добавления данных по системе {} в базу данных!"},
    401: {'type_msg': 'error', 'title': "Ошибка в получении данных пользователя!"},
    403: {'type_msg': 'error', 'title': "Запрос не может быть обработан."},
    404: {'type_msg': 'info', 'title': "Пользователь не найден в подсистеме."},
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

        ui_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'loadView.ui')
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
    callbackLogs = pyqtSignal(int, str)

    __script_ASFK = passwords.SCRIPTS['ASFK']
    __script_SUFD = passwords.SCRIPTS['SUFD']

    def __init__(self):
        super(ExcelLoader, self).__init__()

        ui_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'selectExcel.ui')
        uic.loadUi(ui_file, self)
        self.fileDialog.clicked.connect(self.openFileDialog)
        self.copy_script.clicked.connect(self.copyScript)

        self.loading = False
        self.loadingPause = False

        self.__loader = LoaderView()
        self.__loader.loadingPaused.connect(self.pauseLoading) 
        self.__loader.closeLoading.connect(self.closeLoading) 

        self.output_data = None
        self.list_users = set()
        self.select_system = None
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
        self.select_system = None
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
        if self.asfk_check.isChecked():
            buffer = self.__script_ASFK
        elif self.sufd_check.isChecked():
            buffer = self.__script_SUFD
        else:
            text = "Не выбрана ни одна подсистема"

        if buffer:
            if self.minimize_script.isChecked():
                buffer = buffer.replace('\n', '')
                buffer = re.sub(r'\t+', ' ', buffer)
                buffer = re.sub(r'\s+', ' ', buffer)
            clipboard.setText(buffer)
        
        show_messagebox("info" if buffer else 'warn', "Копирование скрипта", text)
    
    def accept(self):
        if not self.asfk_check.isChecked() and not self.sufd_check.isChecked():
            show_messagebox("warn", "Загрузка EXCEL", "Не выбрана ни одна подсистема.")
            return
        if not os.path.exists(self.excelPath.text()):
            show_messagebox("err", "Загрузка EXCEL", "Неверный путь к файлу.")
            return
        
        try:
            self.select_system = 'АСФК' if self.asfk_check.isChecked() else 'СУФД' # ПОМЕНЯТЬ!!!
            self.output_data = {self.select_system: {'parent': None, 'roles': {}}}
            self.select_sheet_file = open_workbook(self.excelPath.text()).sheet_by_index(0)
            self.current_iteration = 1
            self.total_iterations = self.select_sheet_file.nrows
            self.__loader.start(self.select_sheet_file.nrows - 1)
            self.loading = True
            self.loadingPause = False
            self.readExcel() 
            self.__loader.show()
        except Exception as e:
            self.callbackLogs.emit(401, str(e))
            show_messagebox("err", "Ошибка загрузки", str(e))

    def readExcel(self):
        if not self.loading or self.loadingPause: return 
        if self.current_iteration < self.total_iterations:
            try:
                user = self.select_sheet_file.cell_value(self.current_iteration, 0)
                role_list = self.select_sheet_file.cell_value(self.current_iteration, 2).split('|')
                for role in role_list:
                    if role:
                        self.output_data[self.select_system]['roles'].setdefault(role, [])
                        self.output_data[self.select_system]['roles'][role].append(user)
                self.list_users.add(user)
                self.__loader.increase()
                self.current_iteration += 1
                QTimer.singleShot(0, self.readExcel)
            except Exception as e:
                self.callbackLogs.emit(401, str(e))
                show_messagebox("err", "Ошибка загрузки", str(e))
                self.closeLoading()
                self.__loader.reset()
        else:
            self.callbackData.emit({'data': self.output_data, 'users': self.list_users})
            self.closeLoading()
        
class Ui(QMainWindow):
    def __init__(self, handles: dict):
        super(Ui, self).__init__()
        self.conn_matrix = connect(
            # database='matrix', **passwords.DB
            database="matrix", user='postgres', password='admin', host='localhost', port= '5432'
        )
        self.conn_auth = connect(
            # database='auth_db', **passwords.DB
            database="auth_db", user='postgres', password='admin', host='localhost', port= '5432'
        )

        self.__excel_loader = ExcelLoader()
        self.__excel_loader.callbackData.connect(self.loadExcel) 
        self.__excel_loader.callbackLogs.connect(lambda code, err: self.addLogs(code, [''], err)) 

        self.list_users = {}
        ui_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MainWindow.ui')
        uic.loadUi(ui_file, self)
        self.select_departments.currentIndexChanged.connect(self.onChangeDepartment)
        self.submit.clicked.connect(self.get_data_tree)
        self.getDefaultData()
        self.model = MyModel()
        self.outView.setModel(self.model)
        self.clear_logs.clicked.connect(lambda: self.model.removeRows(0, self.model.rowCount()))
        self.load_excel.clicked.connect(lambda: self.__excel_loader.show())
        self.fileDialog.clicked.connect(self.openFileDialog)
        # self.outView.setItemDelegate(ItemWordWrap(self.outView))
        self.handler = handler
        self.cache = []
        self.show()

    def openFileDialog(self):
        filePath, _ = QFileDialog.getOpenFileName(self, "Путь к браузеру", self.browserPath.text(), "Executable Files (*.exe *.bin *.sh)")
        if filePath:
            self.browserPath.setText(filePath)

    def setListEmpoyees(self, department_id: int):
        self.select_employee.clear()
        cursor = self.conn_auth.cursor()
        cursor.execute('''SELECT id, name FROM "Auth_LDAP_customuser" WHERE department_id = %s''', (department_id,))
        self.list_users.clear()
        for id, name in cursor.fetchall():
            self.list_users[name] = id
            self.select_employee.addItem(name, id)
            
        cursor.close()

    def loadExcel(self, data):
        roles = data['data'] # its dict
        users = data['users'] # its set

        user_list = list(users)

        placeholders = ', '.join(['%s'] * len(user_list))

        cursor = self.conn_auth.cursor()
        cursor.execute(f'''SELECT id, lower(replace(name, ' ', '')) as name FROM "Auth_LDAP_customuser" WHERE lower(replace(name, ' ', '')) IN  ({placeholders})''', user_list)
        self.list_users.clear()
        for id, name in cursor.fetchall():
            self.list_users[name] = id

        t1 = threading.Thread(target=self.restructurData, args=(roles,))
        t1.start()

    def onChangeEmployee(self, text):
        if text == '':
            self.combobox.setCurrentIndex(-1)

    def onChangeDepartment(self, index):
        self.setListEmpoyees(self.select_departments.itemData(index))
        
    def getDefaultData(self):
        settings = QSettings("Matrix", "Settings")
        self.browserPath.setText(settings.value("browserPath", ""))

        self.select_employee.clear()
        cursor_auth = self.conn_auth.cursor()
        cursor_auth.execute('''SELECT id, name FROM "Auth_LDAP_departments"''')
        for id, name in cursor_auth.fetchall():
            self.select_departments.addItem(name, id)
        cursor_auth.close()

    def addLogs(self, code, title_args = [""], discription=""):
        msg = MESSAGES[code]
        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self.model.add_data([now, msg['type_msg'], msg['title'].format(*title_args), discription])

    def get_data_tree(self):
        if self.select_departments.currentIndex() == -1:
            show_messagebox("err", "Ошибка запроса", "Не выбран ни один отедел!") 
            return
        if self.select_employee.currentIndex() == -1:
            if not show_messagebox("info", "Подтвердите действие", "Сотрудник не выбран, запрос данных будет производится по каждому сотруднику отдела.", True):
                return
            list_users = [self.select_employee.itemText(i) for i in range(self.select_employee.count())]
        else:
            list_users = [self.select_employee.currentText()]
        if not any([self.checker_poib.isChecked(), self.checker_axiok.isChecked(), self.checker_eis.isChecked()]):
            if not show_messagebox("info", "Подтвердите действие", "Не выбрана ни одна подсистема. Поиск будет производится по всем имеющимся.", True):
                return
            list_systems = ['SOBI', 'AXIOK', 'EIS']
        else:
            list_systems = [system for system, checkbox in [('SOBI', self.checker_poib), ('AXIOK', self.checker_axiok), ('EIS', self.checker_eis)] if checkbox.isChecked()]

        t1 = threading.Thread(target=self.process_logs, args=(list_systems, list_users))
        t1.start()

    def process_logs(self, list_systems, list_users):
        for system_el in list_systems:
            self.addLogs(202, [system_el], '')

            next_is_data = False
            for log in handler.start(list_users, system_el, self.browserPath.text()):
                if next_is_data:
                    self.restructurData(log)
                elif log['code'] == 100:
                    next_is_data = True
                    self.addLogs(100, [system_el], '')
                else:
                    self.addLogs(log['code'], log.get('args', []), log.get('discription', ""))

    def restructurData(self, data: dict):
        counter = {'check': 0, 'create': 0, 'errors': 0, 'undefined': 0}
        list_systems = {}
        self.setDeleteFlag()

        for key in data:
            counter['check'] += 1
            updated_users = set()
            # try:
            if True:
                added_data = {'id': None, 'name': key, 'parent': None}
                id_parent = None
                name_parent = data[key]['parent']
                if name_parent != None:
                    id_parent = list_systems.get(name_parent, {}).get('id', None)
                    if id_parent == None:
                        id_parent = self.addNewSystem(name_parent)
                        list_systems.update({name_parent: {'id': id_parent, 'name': name_parent, 'parent': None}})
                    added_data['parent'] = id_parent
                
                added_data['id'] = self.addNewSystem(key, id_parent)
                list_systems.update({key: added_data})

                # добавление роли пользователю
                id_system = list_systems[key]['id']
                counter['check'] -= 1
                for role in data[key]['roles']:
                    role_id = self.addNewRole(id_system, role)

                    for user in data[key]['roles'][role]:
                        counter['check'] += 1
                        id_user = self.list_users.get(user, -1)
                        if id_user == -1:
                            counter['undefined'] += 1
                            continue
                        updated_users.add(id_user)
                        relation = self.addUserRoles(id_user, role_id)
                        if relation:
                            counter['create'] += 1
                self.addLogsMatrix(updated_users, added_data['id'])
            # except Exception as e:
            #     counter['errors'] += 1
            #     self.addLogs(400, [key], str(e))
        count_delete = self.deleteInactiveRoles()
        self.addLogs(201, [], f'Общее количество - {counter["check"]}; Создано - {counter["create"]}; Ошибок - {counter["errors"]}; Не найден пользователь - {counter["undefined"]}; Удалено полномочий - {count_delete}')
        self.conn_matrix.commit()

    def deleteInactiveRoles(self):
        cursor_matrix = self.conn_matrix.cursor()
        cursor_matrix.execute('''
            DELETE FROM "KingMatrixAPI_userroles" 
            WHERE "isChecked" = FALSE''', ())

        data = cursor_matrix.rowcount
        cursor_matrix.close()
        return data

    def setDeleteFlag(self):
        cursor_matrix = self.conn_matrix.cursor()
        cursor_matrix.execute('''
            UPDATE "KingMatrixAPI_userroles" 
            SET "isChecked" = FALSE 
            WHERE "user" IN %s
        ''', (tuple(self.list_users.values()),))
        
        cursor_matrix.close()

    def addLogsMatrix(self, users, system):
        with self.conn_matrix.cursor() as cursor_matrix:
            cursor_matrix.execute('''
                DELETE FROM "KingMatrixAPI_logupdates"  
                WHERE "user" = ANY(%s::int[])  AND system_id = %s
            ''', (list(users), system))
            cursor_matrix.execute('''
                INSERT INTO "KingMatrixAPI_logupdates" ("user", system_id, date_msg) 
                SELECT unnest(%s::int[]), %s, NOW()
            ''', (list(users), system))
            data = cursor_matrix.rowcount

        return data

    def addUserRoles(self, id_user, id_role):
        with self.conn_matrix.cursor() as cursor_matrix:
            cursor_matrix.execute('''
                SELECT id FROM "KingMatrixAPI_userroles" WHERE "user" = %s AND role_id = %s
            ''', (id_user, id_role))
                
            data = cursor_matrix.fetchone()
            if data:
                cursor_matrix.execute('''
                    UPDATE "KingMatrixAPI_userroles" 
                    SET "isChecked" = TRUE 
                    WHERE "id" = %s
                ''', (data))
                return None
            else:
                cursor_matrix.execute('''
                    INSERT INTO "KingMatrixAPI_userroles" ("user", role_id, "isChecked") 
                    VALUES (%s, %s, %s)
                    RETURNING id
                ''', (id_user, id_role, True))
                
                data = cursor_matrix.fetchone()
            return data[0]

    def addNewRole(self, id_system, role):
        with self.conn_matrix.cursor() as cursor_matrix:
            
            # Сначала проверяем, существует ли роль
            cursor_matrix.execute('''
                SELECT id FROM "KingMatrixAPI_roles" WHERE system_id = %s AND name = %s
            ''', (id_system, role))
            
            data = cursor_matrix.fetchone()
            
            if data is None:
                cursor_matrix.execute('''
                    INSERT INTO "KingMatrixAPI_roles" (system_id, name) 
                    VALUES (%s, %s)
                    RETURNING id
                ''', (id_system, role))
                data = cursor_matrix.fetchone()

        return data[0]

    def addNewSystem(self, system_name, id_parent=None):
        with self.conn_matrix.cursor() as cursor_matrix:
            # Сначала проверяем, существует ли система
            if id_parent:
                cursor_matrix.execute('''
                    SELECT id FROM "KingMatrixAPI_systems" WHERE name = %s AND parent_id = %s
                ''', (system_name, id_parent))
            else:
                cursor_matrix.execute('''
                    SELECT id FROM "KingMatrixAPI_systems" WHERE name = %s AND parent_id IS NULL
                ''', (system_name,))
            
            data = cursor_matrix.fetchone()
            if data is None:
                cursor_matrix.execute('''
                    INSERT INTO "KingMatrixAPI_systems" (name, parent_id) 
                    VALUES (%s, %s)
                    RETURNING id
                ''', (system_name, id_parent))
                
                data = cursor_matrix.fetchone()
        
        return data[0]
    
    def closeEvent(self, event):
        self.conn_matrix.close()
        self.conn_auth.close()
        settings = QSettings("Matrix", "Settings")
        settings.setValue("browserPath", self.browserPath.text())
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    handler = HandlerRoles()
    ui = Ui(handler)
    sys.exit(app.exec_())
