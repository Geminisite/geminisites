import sqlite3

# Устанавливаем соединение с базой данных
connection = sqlite3.connect('chat_app.db')
cursor = connection.cursor()

# Создаем таблицу для хранения чатов
# Каждый чат имеет ID, заголовок и системный промпт
cursor.execute('''
    CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        system_prompt TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

# Создаем таблицу для хранения сообщений
# Каждое сообщение привязано к чату через chat_id
cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        role TEXT NOT NULL, -- 'user' или 'model'
        content TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (chat_id) REFERENCES chats (id)
    )
''')

# Сохраняем изменения и закрываем соединение
connection.commit()
connection.close()

print("База данных и таблицы успешно созданы.")