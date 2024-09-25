from PyQt5 import QtCore, QtWidgets
from PyQt5.QtGui import QStandardItemModel, QStandardItem
# custom
from sobi import HandleSelfSignedCertificate
from PyQt5.QtSql import QSqlDatabase, QSqlQuery, QSqlTableModel, QSqlQueryModel
import psycopg2

names_list = [
    'Болдаков Алексей Ильич',
    'Макаров Михаил Игоревич'
]

# TEST_DATA = {
#     'АОКЗ': {'Пользователь СКЗИ': ['Болдаков Алексей Ильич']}, 
#     'Официальный сайт для размещения информации о государственных и муниципальных учреждениях': {'Территориальный орган федерального казначейства_подг': ['Болдаков Алексей Ильич'], 'Территориальный орган федерального казначейства_публ': ['Болдаков Алексей Ильич']}, 'Подсистема обеспечения информационной безопасности': {'Визирующий': ['Болдаков Алексей Ильич'], 'Регистратор': ['Болдаков Алексей Ильич', 'Макаров Михаил Игоревич'], 'Оператор ИС': ['Макаров Михаил Игоревич']}, 'Подсистема управления жизненным циклом Системы управления эксплуатации Федерального казначейства': {'ФК.Инженер': ['Болдаков Алексей Ильич'], 'ФК.Специалист': ['Болдаков Алексей Ильич']}, 'Система комплексного информационно-аналитического обеспечения деятельности органов Федерального казначейства': {'СКИАО.011 ИАП, Сотрудник ТОФК': ['Болдаков Алексей Ильич'], 'СКИАО.027 СПД, Ввод данных': ['Болдаков Алексей Ильич'], 'СКИАО.031 СПД, Согласующий': ['Болдаков Алексей Ильич'], 'СКИАО.080 СПД, Передача на утверждение': ['Болдаков Алексей Ильич']}, 'Электронный бюджет': {'БО_ДО.009 ТОФК.Просмотр БО_ДО': ['Болдаков Алексей Ильич', 'Макаров Михаил Игоревич'], 'ПИАО.100 Кассовое планирование и прогнозирование': ['Болдаков Алексей Ильич'], 'ПИАО.200 Исполнение бюджетов': ['Болдаков Алексей Ильич'], 'ПИАО.300 НП и ГП': ['Болдаков Алексей Ильич'], 'ПИАО.400 Перечни и реестры': ['Болдаков Алексей Ильич'], 'ПИАО.500 Закупки': ['Болдаков Алексей Ильич'], 'ПИАО.600 Бюджетный учет': ['Болдаков Алексей Ильич'], 'ПИАО.700 Контроль и надзор': ['Болдаков Алексей Ильич'], 'ПИАО.800 Казначейское сопровождение': ['Болдаков Алексей Ильич'], 'ПИАО.ФК': 
# ['Болдаков Алексей Ильич'], 'ПИАО.ФК.000 Просмотр всего': ['Болдаков Алексей Ильич'], 'УиО Создание документа Карточка учета первичного документа': ['Болдаков Алексей Ильич'], 'УиО Формирование документов по администрированию доходов c ЦБ ввод': ['Болдаков Алексей Ильич'], 'УиО Формирование документов по учету операций по предоставлению бюджетных кредитов с ЦБ ввод': ['Болдаков Алексей Ильич'], 'УНФА Комиссия по приему и списанию нефинансовых активов c ЦБ ввод': ['Болдаков Алексей Ильич'], 'УНФА Комиссия по приему и списанию нефинансовых активов c ЦБ согласование': ['Болдаков Алексей Ильич'], 'УНФА Формирование первичных документов c ЦБ ввод': ['Болдаков Алексей Ильич'], 'УНФА Формирование первичных документов c ЦБ согласование': ['Болдаков Алексей Ильич'], 'УНФА. Формирование документов по проведению инвентаризаций нефинансовых активов c ЦБ ввод': ['Болдаков Алексей Ильич'], 'УНФА. Формирование документов по проведению инвентаризаций нефинансовых активов c ЦБ согласование': ['Болдаков Алексей Ильич'], 'УНФА_УиО Голосование за резолюцию по комиссионному решению': ['Болдаков Алексей Ильич'], 'УНФА_УИО Просмотр документов бухгалтерского учета, формирование отчетов, поступивших задач пользователей учреждения в конечном статусе документа': ['Болдаков Алексей Ильич'], 'УНФА_УиО Просмотр документов бухгалтерского учета, формирование отчетов, просмотр поступивших задач пользователей учреждения': ['Болдаков Алексей Ильич'], 'УНФА_УИО Установка учреждений Администратор': ['Болдаков Алексей Ильич'], 'УНФА_УиО Формирование документов по решению комиссии ': ['Болдаков Алексей Ильич'], 'РУБПНУБП.009 - Чтение всех документов УО': ['Макаров Михаил Игоревич'], 'РУБПНУБП.010 - Чтение всех документов всех УО': ['Макаров Михаил Игоревич'], 'УНФА_УИО Локальный администратор ЦБ ввод': ['Макаров Михаил Игоревич'], 'УНФА_УИО Формирование бухгалтерских проводок и обработка документов сотрудник ЦБ ввод': ['Макаров Михаил Игоревич']}}


class MyModel(QStandardItemModel):
    def __init__(self, parent=None):
        super(MyModel, self).__init__(parent)

    def setup_data(self, data: dict, employee: list):
        self.clear()

        self.setColumnCount(len(employee) + 1)
        self.setHorizontalHeaderLabels(['Подсистема/Роль', *employee])

        for system, roles in data.items():
            system_item = QStandardItem(system)
            for role, users in roles.items():
                role_item = QStandardItem(role)
                system_item.appendRow([role_item, *[QStandardItem('✅' if user in employee else '❌') for user in users]])
                
            self.appendRow(system_item)

class Ui_MainWindow(object):
    def __init__(self, request: callable):
        self.request = request
        self.conn_matrix = psycopg2.connect(
            database="matrix", user='postgres', password='admin', host='localhost', port= '5432'
        )
        self.conn_auth = psycopg2.connect(
            database="auth_db", user='postgres', password='admin', host='localhost', port= '5432'
        )
        

    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(640, 480)
        MainWindow.setMinimumSize(QtCore.QSize(640, 480))
        MainWindow.setMaximumSize(QtCore.QSize(640, 480))
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.gridLayoutWidget = QtWidgets.QWidget(self.centralwidget)
        self.gridLayoutWidget.setGeometry(QtCore.QRect(0, -1, 641, 41))
        self.gridLayoutWidget.setObjectName("gridLayoutWidget")
        self.filterWrap = QtWidgets.QGridLayout(self.gridLayoutWidget)
        self.filterWrap.setContentsMargins(15, 20, 15, 0)
        self.filterWrap.setSpacing(10)
        self.filterWrap.setObjectName("filterWrap")
        self.select_departments = QtWidgets.QComboBox(self.gridLayoutWidget)
        self.select_departments.setWhatsThis("")
        self.select_departments.setEditable(True)
        self.select_departments.setObjectName("select_departments")
        self.filterWrap.addWidget(self.select_departments, 0, 0, 1, 1)
        self.select_employee = QtWidgets.QComboBox(self.gridLayoutWidget)
        self.select_employee.setEditable(True)
        self.select_employee.setFrame(True)
        self.select_employee.setObjectName("select_employee")
        self.filterWrap.addWidget(self.select_employee, 0, 1, 1, 1)
        self.gridLayoutWidget_2 = QtWidgets.QWidget(self.centralwidget)
        self.gridLayoutWidget_2.setGeometry(QtCore.QRect(0, 70, 641, 41))
        self.gridLayoutWidget_2.setObjectName("gridLayoutWidget_2")
        self.gridLayout = QtWidgets.QGridLayout(self.gridLayoutWidget_2)
        self.gridLayout.setContentsMargins(15, 0, 15, 0)
        self.gridLayout.setObjectName("gridLayout")
        self.checker_poib = QtWidgets.QCheckBox(self.gridLayoutWidget_2)
        self.checker_poib.setObjectName("checker_poib")
        self.gridLayout.addWidget(self.checker_poib, 0, 0, 1, 1)
        self.checker_eis = QtWidgets.QCheckBox(self.gridLayoutWidget_2)
        self.checker_eis.setObjectName("checker_eis")
        self.gridLayout.addWidget(self.checker_eis, 0, 1, 1, 1)
        self.checker_axiok = QtWidgets.QCheckBox(self.gridLayoutWidget_2)
        self.checker_axiok.setObjectName("checker_axiok")
        self.gridLayout.addWidget(self.checker_axiok, 0, 2, 1, 1)
        self.outView = QtWidgets.QTreeView(self.centralwidget)
        self.outView.setGeometry(QtCore.QRect(0, 160, 641, 271))
        self.outView.setObjectName("outView")
        self.model = MyModel()
        self.outView.setModel(self.model)
        self.horizontalLayoutWidget = QtWidgets.QWidget(self.centralwidget)
        self.horizontalLayoutWidget.setGeometry(QtCore.QRect(320, 110, 321, 51))
        self.horizontalLayoutWidget.setObjectName("horizontalLayoutWidget")
        self.horizontalLayout = QtWidgets.QHBoxLayout(self.horizontalLayoutWidget)
        self.horizontalLayout.setContentsMargins(0, 0, 15, 0)
        self.horizontalLayout.setSpacing(10)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.submit = QtWidgets.QPushButton(self.horizontalLayoutWidget)
        self.submit.clicked.connect(self.get_data_tree)
        self.submit.setObjectName("submit")
        self.horizontalLayout.addWidget(self.submit)
        self.clear = QtWidgets.QPushButton(self.horizontalLayoutWidget)
        self.clear.setObjectName("clear")
        self.horizontalLayout.addWidget(self.clear)
        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 640, 21))
        self.menubar.setObjectName("menubar")
        MainWindow.setMenuBar(self.menubar)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def setListEmpoyees(self, items):
        self.select_employee.clear()
        self.select_employee.addItems(items)

    def setListDepartments(self, items):
        self.select_employee.clear()
        cursor = self.conn_auth.cursor()
        cursor.execute('''SELECT name FROM "Auth_LDAP_departments"''')
        self.select_employee.addItems([item[0] for item in cursor.fetchall()])

    def get_data_tree(self):
        employee = self.select_employee.currentText()
        data_tree = self.request(names_list)
        self.model.setup_data(data_tree, [employee])

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "Тестовый пример"))
        self.select_departments.setPlaceholderText(_translate("MainWindow", "Выберите отдел"))
        self.select_employee.setPlaceholderText(_translate("MainWindow", "Выберите сотрудника"))
        self.checker_poib.setText(_translate("MainWindow", "ПОИБ СОБИ"))
        self.checker_eis.setText(_translate("MainWindow", "ЕИС"))
        self.checker_axiok.setText(_translate("MainWindow", "Аксиок Планирование"))
        self.submit.setText(_translate("MainWindow", "Получить данные"))
        self.clear.setText(_translate("MainWindow", "Очистить вывод"))
    
    def __del__(self):
        self.conn_matrix.close()
        self.conn_auth.close()
        
if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    handler = HandleSelfSignedCertificate()
    MainWindow = QtWidgets.QMainWindow()
    ui = Ui_MainWindow(handler.open_browser)
    ui.setupUi(MainWindow)
    ui.setListEmpoyees(names_list)
    MainWindow.show()
    sys.exit(app.exec_())
