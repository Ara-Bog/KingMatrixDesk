from PyQt5 import uic
from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtWidgets import QMessageBox, QFileDialog, QMainWindow, QApplication
from psycopg2 import connect
import sys
from datetime import datetime
import threading
# custom
from handler import HandlerRoles
import sys
import os
import passwords

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
}

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

# # Для динамического изменения ширины колонок таблицы
# class ItemWordWrap(QStyledItemDelegate):
#     def __init__(self, parent=None):
#         QStyledItemDelegate.__init__(self, parent)
#         self.parent = parent

#     def sizeHint(self, option, index):
#         text = index.model().data(index)
#         document = QTextDocument()
#         document.setHtml(text) 
#         width = index.model().data(index, QtCore.Qt.UserRole+1)
#         if not width:
#             width = 20
#         document.setTextWidth(width) 
#         return QtCore.QSize(math.ceil(document.idealWidth() + 10),  math.ceil(document.size().height()))    

#     def paint(self, painter, option, index):
#         text = index.model().data(index) 
#         document = QTextDocument()
#         document.setHtml(text)       
#         document.setTextWidth(option.rect.width())
#         index.model().setData(index, option.rect.width(), QtCore.Qt.UserRole+1)
#         painter.save() 
#         painter.translate(option.rect.x(), option.rect.y()) 
#         document.drawContents(painter)
#         painter.restore()

class Ui(QMainWindow):
    __types_msg = {
        "info": QMessageBox.Information,
        "err": QMessageBox.Critical,
        "warn": QMessageBox.Warning
    }
    def __init__(self, handles: dict):
        super(Ui, self).__init__()
        self.conn_matrix = connect(
            database='matrix', **passwords.DB
            # database="matrix", user='postgres', password='admin', host='localhost', port= '5432'
        )
        self.conn_auth = connect(
            database='auth_db', **passwords.DB
            # database="auth_db", user='postgres', password='admin', host='localhost', port= '5432'
        )
        
        self.list_systems = {}
        self.list_users = {}
        ui_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MainWindow.ui')
        uic.loadUi(ui_file, self)
        self.select_departments.currentIndexChanged.connect(self.onChangeDepartment)
        self.submit.clicked.connect(self.get_data_tree)
        self.getDefaultData()
        self.model = MyModel()
        self.outView.setModel(self.model)
        self.clear_logs.clicked.connect(self.clear)
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

    def onChangeDepartment(self, index):
        self.setListEmpoyees(self.select_departments.itemData(index))
        
    def getDefaultData(self):
        settings = QSettings("Matrix", "Settings")
        self.browserPath.setText(settings.value("browserPath", ""))

        cursor_matrix = self.conn_matrix.cursor()
        cursor_matrix.execute('''SELECT * FROM "KingMatrixAPI_systems"''')

        self.list_systems = {row[1]: {'id': row[0], 'name': row[1], 'parent': row[2]} for row in cursor_matrix.fetchall()}
        cursor_matrix.close()

        self.select_employee.clear()
        cursor_auth = self.conn_auth.cursor()
        cursor_auth.execute('''SELECT id, name FROM "Auth_LDAP_departments"''')
        for id, name in cursor_auth.fetchall():
            self.select_departments.addItem(name, id)
        cursor_auth.close()
        
    def clear(self):
        self.model.removeRows(0, self.model.rowCount())

    def addLogs(self, code, title_args = [""], discription=""):
        msg = MESSAGES[code]
        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self.model.add_data([now, msg['type_msg'], msg['title'].format(*title_args), discription])

    def get_data_tree(self):
        if self.select_departments.currentIndex() == -1:
            self.show_messagebox("err", "Ошибка запроса", "Не выбран ни один отедел!") 
            return
        if self.select_employee.currentIndex() == -1:
            if not self.show_messagebox("info", "Подтвердите действие", "Сотрудник не выбран, запрос данных будет производится по каждому сотруднику отдела.", True):
                return
            list_users = [self.select_employee.itemText(i) for i in range(self.select_employee.count())]
        else:
            list_users = [self.select_employee.currentText()]
        if not any([self.checker_poib.isChecked(), self.checker_axiok.isChecked(), self.checker_eis.isChecked()]):
            if not self.show_messagebox("info", "Подтвердите действие", "Не выбрана ни одна подсистема. Поиск будет производится по всем имеющимся.", True):
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
        counter = {'check': 0, 'create': 0, 'errors': 0}
        for key in data:
            counter['check'] += 1
            try:
                # добавление систем, при их отсутствии
                if key not in self.list_systems:
                    added_data = {'id': None,'name': key, 'parent': None}
                    id_parent = None
                    name_parent = data[key]['parent']
                    if name_parent != None:
                        id_parent = self.list_systems.get(name_parent, {}).get('id', None)
                        if id_parent == None:
                            id_parent = self.addNewSystem(name_parent)
                            self.list_systems.update({name_parent: {'id': id_parent, 'name': name_parent, 'parent': None}})
                        added_data['parent'] = id_parent
                    
                    added_data['id'] = self.addNewSystem(key, id_parent)
                    self.list_systems.update({key: added_data})
                # добавление роли пользователю
                id_system = self.list_systems[key]['id']
                counter['check'] -= 1
                for role in data[key]['roles']:
                    for user in data[key]['roles'][role]:
                        counter['check'] += 1
                        id_user = self.list_users[user]
                        role_id = self.addRoles(id_system, id_user, role)
                        if role_id:
                            counter['create'] += 1
            except Exception as e:
                counter['errors'] += 1
                self.addLogs(400, [key], str(e))
        self.addLogs(201, [], f'Общее количество - {counter["check"]};Создано - {counter["create"]}; Ошибок - {counter["errors"]}')
        self.conn_matrix.commit()


    def addRoles(self, id_system, id_user, role):
        cursor_matrix = self.conn_matrix.cursor()
        cursor_matrix.execute('''
                            INSERT INTO "KingMatrixAPI_roles" (system_id, "user", name) 
                            SELECT %s, %s, %s
                            WHERE NOT EXISTS (SELECT 1 FROM "KingMatrixAPI_roles" WHERE system_id = %s AND "user" = %s AND name = %s)
                            RETURNING id''', (id_system, id_user, role, id_system, id_user, role))
        data = cursor_matrix.fetchone()
        cursor_matrix.close()
        return data

    def addNewSystem(self, system_name, id_parent=None):
        cursor_matrix = self.conn_matrix.cursor()
        cursor_matrix.execute('''INSERT INTO "KingMatrixAPI_systems" (name, parent_id) VALUES (%s, %s) RETURNING id''', (system_name, id_parent))
        data = cursor_matrix.fetchone()
        cursor_matrix.close()
        return data


    def show_messagebox(self, type_msg:str, title:str, text:str, cancel: bool = False): 
        msg = QMessageBox() 
        msg.setIcon(self.__types_msg[type_msg]) 
    
        msg.setText(text) 
        
        msg.setWindowTitle(title) 
        
        msg.setStandardButtons(QMessageBox.Ok) 

        if cancel:
            msg.addButton(QMessageBox.Cancel)
        
        return msg.exec_() == QMessageBox.Ok 
    
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
