ip = '192.168.2.169'
username = 'ufk48'
password = 'admin'

import psycopg2
from sshtunnel import SSHTunnelForwarder

# Параметры SSH соединения
ssh_host = '192.168.2.169'
ssh_port = 3389
ssh_user = 'ufk48'
ssh_password = 'admin'

# Параметры подключения к базе данных
db_host = 'database_server_address'
db_port = 5432
db_user = 'your_db_username'
db_password = 'your_db_password'
db_name = 'your_db_name'

# Создаем SSH туннель
with SSHTunnelForwarder(
    (ssh_host, ssh_port),
    ssh_username=ssh_user,
    ssh_password=ssh_password,
    remote_bind_address=(db_host, db_port)
) as tunnel:
    print("Ok")
    # Подключаемся к базе данных через туннель
    # conn = psycopg2.connect(
    #     host='localhost',
    #     port=tunnel.local_bind_port,
    #     user=db_user,
    #     password=db_password,
    #     dbname=db_name
    # )

    # # Создаем курсор для выполнения запросов
    # cursor = conn.cursor()
    
    # # Пример выполнения запроса
    # cursor.execute('SELECT version()')
    # result = cursor.fetchone()
    # print(result)
    
    # # Закрываем соединение
    # cursor.close()
    # conn.close()