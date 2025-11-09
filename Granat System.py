import logging
import sqlite3
import secrets
import os
import random
import hashlib
import asyncio
from telegram.ext import ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from datetime import datetime, timedelta
from telegram.ext import CallbackQueryHandler
# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "8272125084:AAFdH3YqYdIVk93PWQwsVXgLa5ib_EZ9svY"
BOT_USERNAME = "GraphiteSystem_bot"
OPERATOR_CHAT_ID = "7026338104"
OPERATORS = [OPERATOR_CHAT_ID]
# ======================================================

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def is_operator(user_id):
    return str(user_id) in OPERATORS
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()
def generate_credentials():
    login = secrets.token_hex(4)
    password = secrets.token_hex(4)
    return login, password
def generate_unique_token():
    return secrets.token_hex(8)
def generate_salon_link(unique_token):
    return f'https://t.me/{BOT_USERNAME}?start={unique_token}'
def generate_captcha():
    """Генерирует простую математическую капчу"""
    operations = {
        'plus': ('+', lambda a, b: a + b),
        'minus': ('-', lambda a, b: a - b)
    }
    
    op_name, (op_symbol, op_func) = random.choice(list(operations.items()))
    
    if op_name == 'plus':
        a = random.randint(1, 15)
        b = random.randint(1, 15)
    else:  # minus
        a = random.randint(10, 20)
        b = random.randint(1, 9)
    
    question = f"{a} {op_symbol} {b}"
    answer = op_func(a, b)
    
    return question, str(answer)
def register_bot_user(telegram_user_id, username, first_name):
    """Регистрирует или обновляет пользователя в базе"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Сначала проверяем, существует ли пользователь
        cursor.execute('SELECT id FROM bot_users WHERE telegram_user_id = ?', (telegram_user_id,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            # 🔧 ОБНОВЛЯЕМ СУЩЕСТВУЮЩЕГО ПОЛЬЗОВАТЕЛЯ
            cursor.execute('''
                UPDATE bot_users 
                SET username = ?, first_name = ?, last_activity = CURRENT_TIMESTAMP 
                WHERE telegram_user_id = ?
            ''', (username, first_name, telegram_user_id))
            print(f"✅ Обновлен пользователь {telegram_user_id} в базе")
        else:
            # 🔧 СОЗДАЕМ НОВОГО ПОЛЬЗОВАТЕЛЯ
            cursor.execute('''
                INSERT INTO bot_users 
                (telegram_user_id, username, first_name, last_activity) 
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (telegram_user_id, username, first_name))
            print(f"✅ Создан новый пользователь {telegram_user_id} в базе")
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка регистрации пользователя: {e}")
        return False
def get_user_captcha_status(telegram_user_id):
    """Проверяет, прошел ли пользователь капчу"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT captcha_passed FROM bot_users 
            WHERE telegram_user_id = ?
        ''', (telegram_user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            # 🔧 ИСПРАВЛЕНИЕ: правильно обрабатываем boolean из SQLite
            status = result[0]
            print(f"🔍 Статус капчи для {telegram_user_id}: raw={status}, bool={bool(status)}")
            
            # SQLite возвращает 1/0 как integer, преобразуем в boolean
            return bool(status)
        
        print(f"🔍 Пользователь {telegram_user_id} не найден в базе")
        return False
        
    except Exception as e:
        print(f"❌ Ошибка при проверке статуса капчи: {e}")
        return False
def mark_captcha_passed(telegram_user_id):
    """Отмечает, что пользователь прошел капчу"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        print(f"🔍 mark_captcha_passed: обновляем пользователя {telegram_user_id}")
        
        # Обновляем существующего пользователя
        cursor.execute('''
            UPDATE bot_users 
            SET captcha_passed = 1, last_activity = CURRENT_TIMESTAMP 
            WHERE telegram_user_id = ?
        ''', (telegram_user_id,))
        
        # Проверяем, сколько строк было обновлено
        rows_updated = cursor.rowcount
        
        if rows_updated == 0:
            print(f"⚠️ Пользователь {telegram_user_id} не найден, создаем нового")
            # Если пользователь не найден, создаем нового
            cursor.execute('''
                INSERT INTO bot_users 
                (telegram_user_id, captcha_passed, last_activity) 
                VALUES (?, 1, CURRENT_TIMESTAMP)
            ''', (telegram_user_id,))
        
        # Проверяем результат
        cursor.execute('SELECT captcha_passed FROM bot_users WHERE telegram_user_id = ?', (telegram_user_id,))
        result = cursor.fetchone()
        new_status = result[0] if result else None
        
        conn.commit()
        conn.close()
        
        print(f"✅ Капча отмечена как пройденная для пользователя {telegram_user_id}, новый статус: {new_status}")
        return True
        
    except sqlite3.IntegrityError as e:
        print(f"❌ IntegrityError при обновлении капчи: {e}")
        return False
    except Exception as e:
        print(f"❌ Ошибка при отметке капчи: {e}")
        return False
def update_user_activity(telegram_user_id):
    """Обновляет время последней активности"""
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE bot_users 
        SET last_activity = CURRENT_TIMESTAMP 
        WHERE telegram_user_id = ?
    ''', (telegram_user_id,))
    
    conn.commit()
    conn.close()
def is_maintenance_mode_active():
    """Проверяет, активен ли режим технического обслуживания"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        cursor.execute('SELECT is_active FROM maintenance_mode WHERE is_active = 1 ORDER BY id DESC LIMIT 1')
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except Exception as e:
        print(f"❌ Ошибка проверки режима обслуживания: {e}")
        return False
async def check_maintenance_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет режим обслуживания и блокирует действия (кроме оператора)"""
    # 🔧 ОПЕРАТОР МОЖЕТ ВСЕГДА ПОЛЬЗОВАТЬСЯ БОТОМ
    user_id = update.effective_user.id
    if is_operator(user_id):
        return False
    
    if is_maintenance_mode_active():
        maintenance_message = get_maintenance_message()
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.answer("🔧 Режим технического обслуживания", show_alert=True)
            await update.callback_query.edit_message_text(maintenance_message)
        else:
            await update.message.reply_text(maintenance_message)
        return True
    return False
def get_maintenance_message():
    """Получает сообщение о техническом обслуживании"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        cursor.execute('SELECT message FROM maintenance_mode WHERE is_active = 1 ORDER BY id DESC LIMIT 1')
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else "🔧 На данный момент бот находится на техническом обслуживании. Приносим извинения за временные неудобства."
    except:
        return "🔧 Техническое обслуживание"
# ==================== БАЗА ДАННЫХ ====================
def add_booking_to_history(booking_id, action_type, action_by, notes=None):
    """Добавляет запись в историю"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Получаем информацию о записи
        cursor.execute('''
            SELECT b.salon_id, b.client_name, b.client_phone, s.name, m.name, 
                   b.booking_date, b.status, b.confirmed, b.completed
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            WHERE b.id = ?
        ''', (booking_id,))
        
        booking = cursor.fetchone()
        
        if booking:
            salon_id, client_name, client_phone, service_name, master_name, booking_date, status, confirmed, completed = booking
            
            cursor.execute('''
                INSERT INTO booking_history 
                (booking_id, salon_id, client_name, client_phone, service_name, master_name, 
                 booking_date, status, confirmed, completed, action_type, action_by, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (booking_id, salon_id, client_name, client_phone, service_name, master_name,
                  booking_date, status, confirmed, completed, action_type, action_by, notes))
        
        conn.commit()
        conn.close()
        print(f"✅ Запись {booking_id} добавлена в историю ({action_type} by {action_by})")
        
    except Exception as e:
        print(f"❌ Ошибка при добавлении в историю: {e}")
async def owner_booking_history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """История записей для владельца"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Статистика по истории
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled,
            SUM(CASE WHEN action_type = 'created' THEN 1 ELSE 0 END) as created
        FROM booking_history 
        WHERE salon_id = ?
    ''', (salon_id,))
    
    stats = cursor.fetchone()
    
    # Последние записи
    cursor.execute('''
        SELECT client_name, service_name, master_name, booking_date, status, action_type, action_time
        FROM booking_history 
        WHERE salon_id = ?
        ORDER BY action_time DESC 
        LIMIT 10
    ''', (salon_id,))
    
    recent_history = cursor.fetchall()
    conn.close()
    
    history_text = (
        f"📚 **История записей**\n🏪 {salon_name}\n\n"
        f"📊 Статистика:\n"
        f"• Всего действий: {stats[0]}\n"
        f"• Созданных записей: {stats[3]}\n"
        f"• Завершенных: {stats[1]}\n"
        f"• Отмененных: {stats[2]}\n\n"
    )
    
    if recent_history:
        history_text += "🕐 **Последние действия:**\n"
        for record in recent_history:
            client_name, service_name, master_name, booking_date, status, action_type, action_time = record
            
            try:
                if isinstance(booking_date, str):
                    booking_dt = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
                else:
                    booking_dt = booking_date
                booking_str = booking_dt.strftime('%d.%m %H:%M')
            except:
                booking_str = "дата не определена"
            
            try:
                if isinstance(action_time, str):
                    action_dt = datetime.strptime(action_time, '%Y-%m-%d %H:%M:%S')
                else:
                    action_dt = action_time
                action_str = action_dt.strftime('%d.%m %H:%M')
            except:
                action_str = "дата не определена"
            
            action_emoji = {
                'created': '📝',
                'confirmed': '✅',
                'cancelled': '❌',
                'completed': '🏁',
                'reminded': '🔔'
            }.get(action_type, '📋')
            
            history_text += (
                f"{action_emoji} {client_name} - {service_name}\n"
                f"   📅 {booking_str} | {action_str}\n"
                f"   👨‍💼 {master_name} | {status}\n\n"
            )
    
    keyboard = [
        [InlineKeyboardButton("📋 Текущие записи", callback_data="owner_bookings")],
        [InlineKeyboardButton("🔙 Назад", callback_data="owner_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(history_text, reply_markup=reply_markup)
async def client_booking_history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """История записей для клиента"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT b.id, b.booking_date, s.name as service_name, 
               m.name as master_name, sl.name as salon_name,
               b.status, b.confirmed, b.completed
        FROM bookings b
        JOIN services s ON b.service_id = s.id
        JOIN masters m ON b.master_id = m.id
        JOIN salons sl ON b.salon_id = sl.id
        WHERE b.user_id = ?
        ORDER BY b.booking_date DESC
        LIMIT 10
    ''', (user_id,))
    
    bookings = cursor.fetchall()
    conn.close()
    
    if not bookings:
        keyboard = [
            [InlineKeyboardButton("💅 Записаться", callback_data="book_service_main")],
            [InlineKeyboardButton("🔙 Назад", callback_data="client_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📚 **История ваших записей**\n\n"
            "У вас пока нет записей в истории.\n\n"
            "💡 Запишитесь на услугу, чтобы начать историю!",
            reply_markup=reply_markup
        )
        return
    
    history_text = "📚 **История ваших записей**\n\n"
    
    for booking in bookings:
        booking_id, booking_date, service_name, master_name, salon_name, status, confirmed, completed = booking
        
        try:
            if isinstance(booking_date, str):
                booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
            else:
                booking_datetime = booking_date
            
            formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
            
            # Определяем статус
            if status == 'completed':
                status_emoji = "🏁"
                status_text = "Завершена"
            elif status == 'cancelled':
                status_emoji = "❌"
                status_text = "Отменена"
            elif completed:
                status_emoji = "✅"
                status_text = "Подтверждена салоном"
            elif confirmed:
                status_emoji = "⏳"
                status_text = "Ожидает салон"
            else:
                status_emoji = "📝"
                status_text = "Ожидает подтверждения"
                
        except Exception as e:
            formatted_date = "дата не определена"
            status_emoji = "❓"
            status_text = "Неизвестно"
        
        history_text += (
            f"{status_emoji} **{formatted_date}**\n"
            f"🏪 {salon_name}\n"
            f"💅 {service_name} | 👨‍💼 {master_name}\n"
            f"📊 {status_text}\n\n"
        )
    
    keyboard = [
        [InlineKeyboardButton("📋 Активные записи", callback_data="my_bookings_main")],
        [InlineKeyboardButton("💅 Записаться", callback_data="book_service_main")],
        [InlineKeyboardButton("🔙 Назад", callback_data="client_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(history_text, reply_markup=reply_markup)
def cleanup_unconfirmed_bookings():
    """Очищает неподтвержденные записи, которые занимают время"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Находим записи, которые не подтверждены и время записи уже близко
        current_time = datetime.now()
        
        cursor.execute('''
            SELECT b.id, b.booking_date, b.client_name, s.duration 
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            WHERE b.confirmed = 0 
            AND b.status = 'confirmed'
            AND b.booking_date > ?
            AND b.booking_date < datetime(?, '+30 minutes')
        ''', (current_time, current_time.strftime('%Y-%m-%d %H:%M:%S')))
        
        unconfirmed_bookings = cursor.fetchall()
        
        deleted_count = 0
        for booking in unconfirmed_bookings:
            booking_id, booking_date, client_name, duration = booking
            
            # Отменяем запись
            cursor.execute('UPDATE bookings SET status = "cancelled" WHERE id = ?', (booking_id,))
            
            # Удаляем напоминания
            cursor.execute('DELETE FROM booking_reminders WHERE booking_id = ?', (booking_id,))
            
            deleted_count += 1
            print(f"🗑️ Автоматически удалена неподтвержденная запись {booking_id} для {client_name}")
        
        conn.commit()
        conn.close()
        
        if deleted_count > 0:
            print(f"✅ Удалено {deleted_count} неподтвержденных записей")
            
        return deleted_count
        
    except Exception as e:
        print(f"❌ Ошибка при очистке неподтвержденных записей: {e}")
        return 0
def init_db():
    if not os.path.exists('salons.db'):
        print("🗄️ Создание новой базы данных...")
    else:
        print("🗄️ База данных уже существует, продолжаем работу...")
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS maintenance_mode (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            is_active BOOLEAN DEFAULT 0,
            message TEXT,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS booking_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER,
            salon_id INTEGER,
            client_name TEXT,
            client_phone TEXT,
            service_name TEXT,
            master_name TEXT,
            booking_date TIMESTAMP,
            status TEXT,
            confirmed BOOLEAN DEFAULT 0,
            completed BOOLEAN DEFAULT 0,
            action_type TEXT, -- 'created', 'confirmed', 'cancelled', 'completed', 'reminded'
            action_by TEXT, -- 'client', 'salon', 'system'
            action_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            FOREIGN KEY (booking_id) REFERENCES bookings (id),
            FOREIGN KEY (salon_id) REFERENCES salons (id)
        )
    ''')
    try:
        cursor.execute("ALTER TABLE bookings ADD COLUMN completed BOOLEAN DEFAULT 0")
        print("✅ Колонка completed добавлена в таблицу bookings")
    except sqlite3.OperationalError:
        print("✅ Колонка completed уже существует")
    # Таблица салонов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS salons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            telegram_chat_id TEXT,
            unique_token TEXT UNIQUE,
            owner_login TEXT UNIQUE,
            owner_password TEXT,
            is_active BOOLEAN DEFAULT 1,  -- 🔧 НОВАЯ КОЛОНКА ДЛЯ АКТИВНОСТИ
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Пользователи бота
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_user_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            captcha_passed BOOLEAN DEFAULT 0,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица мастеров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS masters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            salon_id INTEGER,
            name TEXT NOT NULL,
            specialization TEXT,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (salon_id) REFERENCES salons (id)
        )
    ''')
    
    # Таблица услуг с полем для диапазона цен
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            salon_id INTEGER,
            name TEXT NOT NULL,
            price TEXT,
            duration INTEGER,
            is_range_price BOOLEAN DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (salon_id) REFERENCES salons (id)
        )
    ''')
    
    # 🔧 ДОБАВЛЯЕМ КОЛОНКУ ЕСЛИ ТАБЛИЦА УЖЕ СУЩЕСТВУЕТ
    try:
        cursor.execute("ALTER TABLE services ADD COLUMN is_range_price BOOLEAN DEFAULT 0")
        print("✅ Колонка is_range_price добавлена в таблицу services")
    except sqlite3.OperationalError:
        print("✅ Колонка is_range_price уже существует")
    
    # Связь мастеров и услуг
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS master_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_id INTEGER,
            service_id INTEGER,
            FOREIGN KEY (master_id) REFERENCES masters (id),
            FOREIGN KEY (service_id) REFERENCES services (id),
            UNIQUE(master_id, service_id)
        )
    ''')
    
    # Таблица записей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            salon_id INTEGER,
            master_id INTEGER,
            service_id INTEGER,
            client_name TEXT,
            client_phone TEXT,
            booking_date TIMESTAMP,
            status TEXT DEFAULT 'confirmed',
            user_id INTEGER,
            confirmed BOOLEAN DEFAULT 0,  -- 🔧 НОВОЕ ПОЛЕ: подтверждена ли запись
            reminder_before_hours INTEGER DEFAULT 24,                   
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (salon_id) REFERENCES salons (id),
            FOREIGN KEY (master_id) REFERENCES masters (id),
            FOREIGN KEY (service_id) REFERENCES services (id)
        )
    ''')
    try:
        cursor.execute("ALTER TABLE salons ADD COLUMN is_active BOOLEAN DEFAULT 1")
        print("✅ Колонка is_active добавлена в таблицу salons")
    except sqlite3.OperationalError:
        print("✅ Колонка is_active уже существует")
    try:
        cursor.execute("ALTER TABLE bookings ADD COLUMN reminder_before_hours INTEGER DEFAULT 24")
        print("✅ Колонка reminder_before_hours добавлена в таблицу bookings")
    except sqlite3.OperationalError:
        print("✅ Колонка reminder_before_hours уже существует")
    # 🔧 ДОБАВЛЯЕМ КОЛОНКУ confirmed ЕСЛИ ТАБЛИЦА УЖЕ СУЩЕСТВУЕТ
    try:
        cursor.execute("ALTER TABLE bookings ADD COLUMN confirmed BOOLEAN DEFAULT 0")
        print("✅ Колонка confirmed добавлена в таблицу bookings")
    except sqlite3.OperationalError:
        print("✅ Колонка confirmed уже существует")
    
    # 🔧 ДОБАВЛЯЕМ КОЛОНКУ user_id ЕСЛИ ТАБЛИЦА УЖЕ СУЩЕСТВУЕТ
    try:
        cursor.execute("ALTER TABLE bookings ADD COLUMN user_id INTEGER")
        print("✅ Колонка user_id добавлена в таблицу bookings")
    except sqlite3.OperationalError:
        print("✅ Колонка user_id уже существует")
    
    # Таблица напоминаний
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS booking_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER,
            reminder_sent BOOLEAN DEFAULT 0,
            reminder_time TIMESTAMP,
            send_to_salon BOOLEAN DEFAULT 1,  -- 🔧 Отправлять ли напоминание салону
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (booking_id) REFERENCES bookings (id) ON DELETE CASCADE
        )
    ''')
    
    # 🔧 ДОБАВЛЯЕМ КОЛОНКУ send_to_salon ЕСЛИ ТАБЛИЦА УЖЕ СУЩЕСТВУЕТ
    try:
        cursor.execute("ALTER TABLE booking_reminders ADD COLUMN send_to_salon BOOLEAN DEFAULT 1")
        print("✅ Колонка send_to_salon добавлена в таблицу booking_reminders")
    except sqlite3.OperationalError:
        print("✅ Колонка send_to_salon уже существует")
    
    # Таблица времени работы
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS working_hours (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            salon_id INTEGER,
            day_of_week INTEGER,
            start_time TIME,
            end_time TIME,
            is_working BOOLEAN DEFAULT 1,
            FOREIGN KEY (salon_id) REFERENCES salons (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Все таблицы проверены/созданы")
def is_time_slot_available(salon_id, booking_datetime, master_id=None, service_id=None):
    """Проверяет, доступно ли время для записи (рабочий день, время и занятость мастера)"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Получаем день недели (0-6, где 0 - понедельник)
        day_of_week = booking_datetime.weekday()
        
        # Проверяем, рабочий ли это день
        cursor.execute('''
            SELECT is_working, start_time, end_time 
            FROM working_hours 
            WHERE salon_id = ? AND day_of_week = ?
        ''', (salon_id, day_of_week))
        
        working_hours = cursor.fetchone()
        
        if not working_hours or not working_hours[0]:  # is_working = False
            conn.close()
            return False, "❌ В этот день салон не работает"
        
        # Преобразуем время в объекты time для сравнения
        start_time = datetime.strptime(working_hours[1], '%H:%M').time()
        end_time = datetime.strptime(working_hours[2], '%H:%M').time()
        booking_time = booking_datetime.time()
        
        # Проверяем, что время записи в пределах рабочего времени
        if not (start_time <= booking_time <= end_time):
            conn.close()
            return False, f"❌ Время вне рабочего графика ({working_hours[1]}-{working_hours[2]})"
        
        # 🔧 ПРОВЕРКА ЗАНЯТОСТИ МАСТЕРА (ТОЛЬКО ЕСЛИ УКАЗАН МАСТЕР)
        if master_id:
            # Получаем длительность текущей услуги
            current_service_duration = 60  # значение по умолчанию
            if service_id:
                cursor.execute('SELECT duration FROM services WHERE id = ?', (service_id,))
                service_result = cursor.fetchone()
                if service_result and service_result[0]:
                    current_service_duration = service_result[0]
            
            # Рассчитываем время окончания текущей услуги
            current_booking_end = booking_datetime + timedelta(minutes=current_service_duration)
            
            # 🔧 ИСПРАВЛЕНИЕ: ищем только пересекающиеся записи, а не все записи за день
            cursor.execute('''
                SELECT b.booking_date, s.duration, m.name as master_name, srv.name as service_name
                FROM bookings b
                JOIN masters m ON b.master_id = m.id
                JOIN services s ON b.service_id = s.id
                JOIN services srv ON b.service_id = srv.id
                WHERE b.master_id = ? 
                AND b.status = 'confirmed'
                AND DATE(b.booking_date) = DATE(?)
                AND (
                    -- Проверяем пересечение временных интервалов
                    (b.booking_date < ? AND datetime(b.booking_date, '+' || s.duration || ' minutes') > ?)
                    OR
                    (b.booking_date >= ? AND b.booking_date < ?)
                )
            ''', (master_id, booking_datetime, current_booking_end, booking_datetime, booking_datetime, current_booking_end))
            
            conflicting_bookings = cursor.fetchall()
            
            if conflicting_bookings:
                conflicting_booking = conflicting_bookings[0]
                master_name = conflicting_booking[2]
                service_name = conflicting_booking[3]
                conn.close()
                return False, f"❌ Мастер {master_name} уже занят в это время (запись на {service_name})"
        
        conn.close()
        return True, "✅ Время доступно для записи"
            
    except Exception as e:
        print(f"❌ Ошибка при проверке времени: {e}")
        return False, "❌ Ошибка при проверке доступности времени"
def check_user_in_database(telegram_user_id):
    """Проверяет, есть ли пользователь в базе и его статус"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT telegram_user_id, username, first_name, captcha_passed, registration_date 
            FROM bot_users 
            WHERE telegram_user_id = ?
        ''', (telegram_user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            print(f"📊 Пользователь в базе: ID={result[0]}, Username={result[1]}, Name={result[2]}, Captcha={result[3]}, RegDate={result[4]}")
            return True
        else:
            print(f"📊 Пользователь {telegram_user_id} не найден в базе")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка при проверке пользователя в базе: {e}")
        return False
def check_table_structure():
    """Проверяет структуру таблицы bot_users"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Получаем информацию о колонках таблицы
        cursor.execute("PRAGMA table_info(bot_users)")
        columns = cursor.fetchall()
        
        print("📋 Структура таблицы bot_users:")
        for col in columns:
            print(f"  {col[1]} ({col[2]}) - default: {col[4]}")
        
        conn.close()
    except Exception as e:
        print(f"❌ Ошибка при проверке структуры таблицы: {e}")
def debug_user_status(telegram_user_id):
    """Детальная отладка статуса пользователя"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, telegram_user_id, username, first_name, captcha_passed, registration_date 
            FROM bot_users 
            WHERE telegram_user_id = ?
        ''', (telegram_user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            user_id, tg_id, username, first_name, captcha_passed, reg_date = result
            print(f"🔍 ДЕТАЛЬНАЯ ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ:")
            print(f"   ID в базе: {user_id}")
            print(f"   Telegram ID: {tg_id}")
            print(f"   Username: {username}")
            print(f"   Имя: {first_name}")
            print(f"   Капча пройдена: {captcha_passed} (тип: {type(captcha_passed)})")
            print(f"   Дата регистрации: {reg_date}")
            return True
        else:
            print(f"🔍 Пользователь {telegram_user_id} не найден в базе")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка при детальной проверке пользователя: {e}")
        return False
def schedule_booking_reminder(booking_id, booking_datetime):
    """Создает запись о напоминании с кнопкой подтверждения"""
    try:
        current_time = datetime.now()
        
        # Вычисляем разницу между текущим временем и временем записи
        time_difference = booking_datetime - current_time
        total_minutes = time_difference.total_seconds() / 60
        total_hours = total_minutes / 60
        
        print(f"🔍 Время записи: {booking_datetime}, сейчас: {current_time}")
        print(f"🔍 Разница: {total_minutes:.1f} минут ({total_hours:.1f} часов)")
        
        # 🔧 УМНАЯ ЛОГИКА НАПОМИНАНИЙ:
        if total_minutes <= 5:
            # Если запись создана менее чем за 5 минут до времени записи
            # Отправляем мгновенное напоминание с кнопкой подтверждения
            reminder_time = current_time + timedelta(minutes=1)
            send_instant = True
            send_to_salon = False
            print(f"🔔 Запись создана в последний момент, мгновенное напоминание с кнопкой")
            
        elif total_minutes <= 30:
            # Если запись создана за 5-30 минут до времени записи
            # Отправляем напоминание сразу с кнопкой подтверждения
            reminder_time = current_time + timedelta(minutes=1)
            send_instant = True
            send_to_salon = False
            print(f"🔔 Запись создана незадолго до времени, напоминание с кнопкой")
            
        else:
            # Стандартный случай - напоминание за 30 минут С КНОПКОЙ
            reminder_time = booking_datetime - timedelta(minutes=30)
            send_instant = False
            send_to_salon = True
            print(f"🔔 Стандартное напоминание за 30 минут с кнопкой")
        
        # 🔧 ПРЕОБРАЗУЕМ В СТРОКУ ДЛЯ БАЗЫ ДАННЫХ
        reminder_time_str = reminder_time.strftime('%Y-%m-%d %H:%M:%S')
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO booking_reminders (booking_id, reminder_time, send_to_salon)
            VALUES (?, ?, ?)
        ''', (booking_id, reminder_time_str, 1 if send_to_salon else 0))
        
        conn.commit()
        conn.close()
        
        print(f"✅ Напоминание создано для записи {booking_id} на {reminder_time_str}")
        print(f"📱 Отправка салону: {'ДА' if send_to_salon else 'НЕТ'}")
        
        # 🔧 ЕСЛИ НУЖНО МГНОВЕННОЕ НАПОМИНАНИЕ - ОТПРАВЛЯЕМ СРАЗУ С КНОПКОЙ
        if send_instant:
            asyncio.create_task(send_instant_reminder_with_confirmation(booking_id, total_minutes))
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при создании напоминания: {e}")
        return False
async def handle_reminder_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора времени напоминания"""
    query = update.callback_query
    await query.answer()
    
    try:
        reminder_choice = query.data
        user = query.from_user
        
        print(f"🔍 Выбор напоминания: {reminder_choice} от пользователя {user.id}")
        
        if not context.user_data.get('waiting_for_reminder_choice'):
            await query.edit_message_text("❌ Ошибка сессии. Начните запись заново.")
            return
        
        # 🔧 ОПРЕДЕЛЯЕМ ВРЕМЯ НАПОМИНАНИЯ
        if reminder_choice == "reminder_24":
            reminder_hours = 24
            reminder_text = "за 24 часа"
        elif reminder_choice == "reminder_1":
            reminder_hours = 1
            reminder_text = "за 1 час"
        else:
            await query.edit_message_text("❌ Неверный выбор. Попробуйте еще раз.")
            return
        
        # 🔧 СОХРАНЯЕМ ВЫБОР В КОНТЕКСТ
        context.user_data['reminder_before_hours'] = reminder_hours
        context.user_data['waiting_for_reminder_choice'] = False
        
        print(f"✅ Выбрано напоминание {reminder_text}, создаем запись...")
        
        # 🔧 СОЗДАЕМ ЗАПИСЬ В БАЗЕ ДАННЫХ
        await create_booking_with_reminder(update, context, reminder_hours)
        
    except Exception as e:
        await query.edit_message_text("❌ Ошибка при выборе напоминания. Попробуйте еще раз.")
        logger.error(f"Error in handle_reminder_choice: {e}")
async def create_booking_with_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE, reminder_hours):
    """Создает запись с выбранным временем напоминания"""
    try:
        query = update.callback_query
        
        # 🔧 ПОЛУЧАЕМ ДАННЫЕ ИЗ КОНТЕКСТА
        current_salon_id = context.user_data.get('current_salon_id')
        current_salon_name = context.user_data.get('current_salon_name')
        selected_date = context.user_data.get('selected_date')
        selected_time = context.user_data.get('selected_time')
        master_id = context.user_data.get('master_id')
        service_id = context.user_data.get('service_id')
        client_name = context.user_data.get('client_name')
        client_phone = context.user_data.get('client_phone')
        
        if not all([current_salon_id, selected_date, selected_time, master_id, service_id, client_name, client_phone]):
            await query.edit_message_text("❌ Ошибка: недостаточно данных. Начните запись заново.")
            return
        
        # 🔧 СОЗДАЕМ ОБЪЕКТ DATETIME
        booking_datetime = datetime.strptime(f"{selected_date} {selected_time}", '%Y-%m-%d %H:%M')
        booking_datetime_str = booking_datetime.strftime('%Y-%m-%d %H:%M:%S')
        
        # 🔧 ПРОВЕРЯЕМ ДОСТУПНОСТЬ ВРЕМЕНИ
        is_available, message = is_time_slot_available(current_salon_id, booking_datetime, master_id, service_id)
        
        if not is_available:
            await query.edit_message_text(
                f"❌ **Невозможно создать запись!**\n\n"
                f"{message}\n\n"
                f"Пожалуйста, выберите другое время через меню записи"
            )
            return
        
        # 🔧 СОХРАНЯЕМ ЗАПИСЬ В БАЗУ С ВРЕМЕНЕМ НАПОМИНАНИЯ
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO bookings (salon_id, master_id, service_id, client_name, client_phone, 
                                booking_date, user_id, confirmed, reminder_before_hours)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (current_salon_id, master_id, service_id, client_name, client_phone, 
              booking_datetime_str, query.from_user.id, 0, reminder_hours))
        
        booking_id = cursor.lastrowid
        
        # Получаем названия услуги и мастера для сообщения
        cursor.execute('SELECT name FROM services WHERE id = ?', (service_id,))
        service_name = cursor.fetchone()[0]
        
        cursor.execute('SELECT name FROM masters WHERE id = ?', (master_id,))
        master_name = cursor.fetchone()[0]
        
        conn.commit()
        conn.close()

        # 🔧 СОЗДАЕМ НАПОМИНАНИЕ С ВЫБРАННЫМ ВРЕМЕНЕМ
        reminder_datetime = booking_datetime - timedelta(hours=reminder_hours)
        schedule_custom_reminder(booking_id, booking_datetime, reminder_hours)
        
        # 🔧 БЕЗОПАСНАЯ ОЧИСТКА КОНТЕКСТА
        keys_to_remove = [
            'selected_date', 'selected_time', 'master_id', 'service_id',
            'client_name', 'client_phone', 'reminder_before_hours'
        ]
        
        for key in keys_to_remove:
            context.user_data.pop(key, None)
        
        formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
        reminder_text = "за 24 часа" if reminder_hours == 24 else "за 1 час"
        
        # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ ПРОСМОТРА ЗАПИСЕЙ
        keyboard = [
            [InlineKeyboardButton("📋 Посмотреть мои записи", callback_data="my_bookings_main")],
            [InlineKeyboardButton("💅 Записаться еще", callback_data="book_service_main")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu_return")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ **Запись успешно создана!**\n\n"
            f"💅 Услуга: {service_name}\n"
            f"👨‍💼 Мастер: {master_name}\n"
            f"📅 Дата: {formatted_date}\n"
            f"👤 Ваше имя: {client_name}\n"
            f"📞 Телефон: {client_phone}\n"
            f"🔔 Напоминание: {reminder_text}\n\n"
            f"Ждем вас в {current_salon_name}! 💫",
            reply_markup=reply_markup
        )
        
        # 🔧 ОТПРАВЛЯЕМ УВЕДОМЛЕНИЕ В САЛОН
        await send_notification_to_salon(current_salon_id, client_name, client_phone, service_name, master_name, booking_datetime)
        
    except Exception as e:
        await query.edit_message_text("❌ Ошибка при создании записи. Попробуйте еще раз.")
        logger.error(f"Error in create_booking_with_reminder: {e}")
        print(f"❌ Детали ошибки: {e}")
def schedule_custom_reminder(booking_id, booking_datetime, reminder_hours):
    """Создает напоминание с выбранным временем"""
    try:
        # Вычисляем время напоминания
        reminder_time = booking_datetime - timedelta(hours=reminder_hours)
        
        # 🔧 ПРЕОБРАЗУЕМ В СТРОКУ ДЛЯ БАЗЫ ДАННЫХ
        reminder_time_str = reminder_time.strftime('%Y-%m-%d %H:%M:%S')
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO booking_reminders (booking_id, reminder_time, send_to_salon)
            VALUES (?, ?, ?)
        ''', (booking_id, reminder_time_str, 1))
        
        conn.commit()
        conn.close()
        
        print(f"✅ Напоминание создано для записи {booking_id} на {reminder_time_str} (за {reminder_hours} часов)")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при создании напоминания: {e}")
        return False
# ==================== УВЕДОМЛЕНИЯ ====================
async def send_notification_to_salon(salon_id, client_name, client_phone, service_name, master_name, booking_date):
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        cursor.execute('SELECT telegram_chat_id FROM salons WHERE id = ?', (salon_id,))
        salon_chat = cursor.fetchone()
        conn.close()
        
        if salon_chat and salon_chat[0]:
            notification_app = Application.builder().token(BOT_TOKEN).build()
            await notification_app.initialize()
            
            formatted_date = booking_date.strftime('%d.%m.%Y в %H:%M')
            
            # 🔧 ИЗМЕНЯЕМ ТЕКСТ - ЗАПИСЬ ЕЩЕ НЕ ПОДТВЕРЖДЕНА
            notification_text = (
                "🔔 **НОВАЯ ЗАПИСЬ!**\n\n"
                f"👤 Клиент: {client_name}\n"
                f"📞 Телефон: {client_phone}\n"
                f"💅 Услуга: {service_name}\n"
                f"👩‍💼 Мастер: {master_name}\n"
                f"📅 Дата: {formatted_date}\n\n"
                f"⏳ **Запись ожидает подтверждения клиентом**"
            )
            
            await notification_app.bot.send_message(chat_id=salon_chat[0], text=notification_text)
            await notification_app.shutdown()
            print(f"📨 Уведомление отправлено салону {salon_id}")
            
    except Exception as e:
        print(f"❌ Ошибка отправки уведомления: {e}")
async def send_instant_reminder_with_confirmation(booking_id, minutes_until):
    """Отправляет мгновенное напоминание с кнопкой подтверждения"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Получаем информацию о записи
        cursor.execute('''
            SELECT b.client_name, b.booking_date, s.name as service_name, 
                   m.name as master_name, sl.name as salon_name, b.user_id, b.confirmed
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            JOIN salons sl ON b.salon_id = sl.id
            WHERE b.id = ?
        ''', (booking_id,))
        
        booking = cursor.fetchone()
        conn.close()
        
        if not booking:
            print(f"❌ Запись {booking_id} не найдена для мгновенного напоминания")
            return
        
        client_name, booking_date, service_name, master_name, salon_name, user_id, confirmed = booking
        
        # 🔧 ОБРАБАТЫВАЕМ ДАТУ
        try:
            if isinstance(booking_date, str):
                booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
            else:
                booking_datetime = booking_date
            
            formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
        except Exception as e:
            print(f"❌ Ошибка обработки даты: {e}")
            formatted_date = "скоро"
        
        # 🔧 ФОРМИРУЕМ ТЕКСТ В ЗАВИСИМОСТИ ОТ ВРЕМЕНИ ДО ЗАПИСИ
        hours_until = minutes_until / 60
        
        if minutes_until <= 30:
            time_text = "очень скоро"
            urgency_emoji = "🚨"
        elif hours_until < 1:
            time_text = f"через {int(minutes_until)} минут"
            urgency_emoji = "⚠️"
        elif hours_until < 2:
            time_text = f"через {int(hours_until)} час"
            urgency_emoji = "🔔"
        elif hours_until < 5:
            time_text = f"через {int(hours_until)} часа"
            urgency_emoji = "🔔"
        else:
            time_text = f"через {int(hours_until)} часов"
            urgency_emoji = "🔔"
        
        # 🔧 СООБЩЕНИЕ ДЛЯ КЛИЕНТА С КНОПКОЙ ПОДТВЕРЖДЕНИЯ
        if confirmed:
            # Если уже подтверждено
            client_reminder_text = (
                f"{urgency_emoji} **СКОРАЯ ЗАПИСЬ!**\n\n"
                f"У вас запись {time_text}:\n\n"
                f"🏪 Салон: {salon_name}\n"
                f"💅 Услуга: {service_name}\n"
                f"👨‍💼 Мастер: {master_name}\n"
                f"📅 Время: {formatted_date}\n\n"
                f"✅ <b>Запись подтверждена</b>\n\n"
                f"📍 Пожалуйста, не опаздывайте!"
            )
            keyboard = []
        else:
            # Если не подтверждено - показываем кнопку
            client_reminder_text = (
                f"{urgency_emoji} **СКОРАЯ ЗАПИСЬ!**\n\n"
                f"У вас запись {time_text}:\n\n"
                f"🏪 Салон: {salon_name}\n"
                f"💅 Услуга: {service_name}\n"
                f"👨‍💼 Мастер: {master_name}\n"
                f"📅 Время: {formatted_date}\n\n"
                f"⏳ <b>Запись ожидает подтверждения</b>\n\n"
                f"📍 Пожалуйста, подтвердите, что придете:"
            )
            # 🔧 ВСЕГДА ДОБАВЛЯЕМ КНОПКУ ПОДТВЕРЖДЕНИЯ
            keyboard = [
                [InlineKeyboardButton("✅ Подтвердить запись", callback_data=f"confirm_booking_{booking_id}")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        # 🔧 ОТПРАВЛЯЕМ ТОЛЬКО КЛИЕНТУ
        if user_id:
            app = Application.builder().token(BOT_TOKEN).build()
            await app.initialize()
            
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text=client_reminder_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                print(f"✅ Мгновенное напоминание с кнопкой отправлено клиенту {client_name} ({time_text})")
            except Exception as e:
                print(f"❌ Не удалось отправить мгновенное напоминание клиенту: {e}")
            
            await app.shutdown()
        
    except Exception as e:
        print(f"❌ Ошибка при отправке мгновенного напоминания: {e}")
# ==================== ТЕСТОВЫЕ КОМАНДЫ НЕ ЗАБУДЬ УДАЛИТЬ!!!!!!!!!! ====================
async def test_booking_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда для имитации начала записи"""
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите ID записи для тестирования\n"
                "Пример: /test_booking 123"
            )
            return
        
        booking_id = int(context.args[0])
        
        # Имитируем начало времени услуги
        success = await send_salon_confirmation_notification(booking_id)
        
        if success:
            await update.message.reply_text(
                f"✅ Тестовое уведомление для записи {booking_id} отправлено!\n"
                f"⏰ Время начала услуги имитировано"
            )
        else:
            await update.message.reply_text(
                f"❌ Не удалось отправить уведомление для записи {booking_id}\n"
                f"⚠️ Проверьте существование записи"
            )
            
    except ValueError:
        await update.message.reply_text("❌ Неверный формат ID записи")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
# ==================== КОМАНДЫ ДЛЯ КЛИЕНТОВ ====================
async def maintenance_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена ввода даты техперерыва"""
    query = update.callback_query
    await query.answer()
    
    # 🔧 СБРАСЫВАЕМ ФЛАГИ
    context.user_data.pop('waiting_for_maintenance_date', None)
    
    await operator_maintenance_handler(update, context)
async def maintenance_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущий статус системы"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_operator(user_id):
        await query.edit_message_text("❌ Доступ запрещен")
        return
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # 🔧 ПОЛУЧАЕМ ТЕКУЩИЙ СТАТУС
    cursor.execute('''
        SELECT is_active, message, start_time, end_time 
        FROM maintenance_mode 
        ORDER BY id DESC LIMIT 1
    ''')
    status = cursor.fetchone()
    
    status_text = "🟢 **Система работает нормально**\n\n"
    maintenance_active = False
    
    if status:
        is_active, message, start_time, end_time = status
        
        if is_active:
            status_text = "🔴 **РЕЖИМ ТЕХНИЧЕСКОГО ОБСЛУЖИВАНИЯ**\n\n"
            maintenance_active = True
        else:
            # 🔧 ПРОВЕРЯЕМ ЗАПЛАНИРОВАННЫЕ ПЕРЕРЫВЫ
            if start_time and datetime.now() < datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S'):
                status_text = "🟡 **ЗАПЛАНИРОВАН ТЕХНИЧЕСКИЙ ПЕРЕРЫВ**\n\n"
        
        status_text += f"📝 Сообщение: {message}\n"
        
        if start_time:
            start_dt = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
            status_text += f"⏰ Начало: {start_dt.strftime('%d.%m.%Y %H:%M')}\n"
        
        if end_time:
            end_dt = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
            status_text += f"⏱️ Окончание: {end_dt.strftime('%d.%m.%Y %H:%M')}\n"
    
    # 🔧 СТАТИСТИКА СИСТЕМЫ
    cursor.execute('SELECT COUNT(*) FROM salons WHERE is_active = 1')
    active_salons = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM bot_users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "confirmed" AND booking_date > datetime("now")')
    active_bookings = cursor.fetchone()[0]
    
    conn.close()
    
    status_text += f"\n📊 **Статистика системы:**\n"
    status_text += f"• Активных салонов: {active_salons}\n"
    status_text += f"• Пользователей: {total_users}\n"
    status_text += f"• Активных записей: {active_bookings}\n"
    
    keyboard = []
    if maintenance_active:
        keyboard.append([InlineKeyboardButton("🟢 Выключить обслуживание", callback_data="maintenance_disable")])
    else:
        keyboard.append([InlineKeyboardButton("🔴 Включить обслуживание", callback_data="maintenance_enable")])
    
    keyboard.extend([
        [InlineKeyboardButton("📅 Запланировать перерыв", callback_data="maintenance_schedule")],
        [InlineKeyboardButton("🔄 Обновить статус", callback_data="maintenance_status")],
        [InlineKeyboardButton("🔙 Назад", callback_data="operator_maintenance")]
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(status_text, reply_markup=reply_markup)
async def maintenance_disable_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выключает режим технического обслуживания"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_operator(user_id):
        await query.edit_message_text("❌ Доступ запрещен")
        return
    
    # Выключаем режим обслуживания
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE maintenance_mode SET is_active = 0 WHERE is_active = 1')
    conn.commit()
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("🔧 К управлению", callback_data="operator_maintenance")],
        [InlineKeyboardButton("🔙 В панель оператора", callback_data="operator_panel_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🟢 **Режим технического обслуживания ВЫКЛЮЧЕН!**\n\n"
        "Система снова доступна для всех пользователей.",
        reply_markup=reply_markup
    )
async def check_unconfirmed_bookings(context: ContextTypes.DEFAULT_TYPE):
    """Фоновая задача: проверяет и удаляет неподтвержденные записи"""
    try:
        current_time = datetime.now()
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # 🔧 НАХОДИМ ЗАПИСИ, КОТОРЫЕ ДОЛЖНЫ БЫТЬ ПОДТВЕРЖДЕНЫ, НО НЕ БЫЛИ
        cursor.execute('''
            SELECT b.id, b.booking_date, b.client_name, s.duration, 
                   s.name as service_name, m.name as master_name, sl.name as salon_name
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            JOIN salons sl ON b.salon_id = sl.id
            WHERE b.status = 'confirmed' 
            AND b.confirmed = 0
            AND b.booking_date <= datetime('now', '+5 minutes')
            AND b.booking_date >= datetime('now', '-30 minutes')
        ''')
        
        unconfirmed_bookings = cursor.fetchall()
        
        deleted_count = 0
        for booking in unconfirmed_bookings:
            booking_id, booking_date, client_name, duration, service_name, master_name, salon_name = booking
            
            # 🔧 АВТОМАТИЧЕСКИ ОТМЕНЯЕМ ЗАПИСЬ
            cursor.execute('UPDATE bookings SET status = "cancelled" WHERE id = ?', (booking_id,))
            
            # 🔧 УДАЛЯЕМ НАПОМИНАНИЯ
            cursor.execute('DELETE FROM booking_reminders WHERE booking_id = ?', (booking_id,))
            
            deleted_count += 1
            
            # 🔧 ДОБАВЛЯЕМ В ИСТОРИЮ
            add_booking_to_history(booking_id, 'cancelled', 'system', 
                                f'Автоматическая отмена: клиент не подтвердил запись')
            
            print(f"🗑️ Автоматически удалена неподтвержденная запись {booking_id} для {client_name}")
        
        conn.commit()
        conn.close()
        
        if deleted_count > 0:
            print(f"✅ Автоматически удалено {deleted_count} неподтвержденных записей")
            
        return deleted_count
        
    except Exception as e:
        print(f"❌ Ошибка при автоматической очистке записей: {e}")
        return 0
async def operator_maintenance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление режимом технического обслуживания"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_operator(user_id):
        await query.edit_message_text("❌ Доступ запрещен")
        return
    
    keyboard = [
        [InlineKeyboardButton("🛑 Включить режим обслуживания", callback_data="maintenance_enable")],
        [InlineKeyboardButton("📅 Запланировать перерыв", callback_data="maintenance_schedule")],
        [InlineKeyboardButton("🔄 Статус системы", callback_data="maintenance_status")],
        [InlineKeyboardButton("🔙 Назад", callback_data="operator_panel_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🔧 **Управление техническим обслуживанием**\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )
async def maintenance_enable_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Включение режима технического обслуживания"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_operator(user_id):
        await query.edit_message_text("❌ Доступ запрещен")
        return
    
    # Включаем режим обслуживания
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Отключаем предыдущие режимы
    cursor.execute('UPDATE maintenance_mode SET is_active = 0')
    
    # Создаем новый режим
    message = "На данный момент, бот находится на техническом обслуживании или обновление системы, убедительная просьба звонить для записи в салон. Приносим вам извинения за доставленные неудобства. Granat system"
    
    cursor.execute('''
        INSERT INTO maintenance_mode (is_active, message, start_time)
        VALUES (1, ?, datetime('now'))
    ''', (message,))
    
    conn.commit()
    conn.close()
    
    # 🔧 ОТПРАВЛЯЕМ УВЕДОМЛЕНИЕ ВСЕМ ПОЛЬЗОВАТЕЛЯМ
    await send_maintenance_notification_to_all(message)
    
    keyboard = [
        [InlineKeyboardButton("🔧 К управлению", callback_data="operator_maintenance")],
        [InlineKeyboardButton("🔙 В панель оператора", callback_data="operator_panel_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🛑 **Режим технического обслуживания ВКЛЮЧЕН!**\n\n"
        "Все пользователи получили уведомление.\n\n"
        "Система временно недоступна для записи.",
        reply_markup=reply_markup
    )
async def send_maintenance_notification_to_all(message):
    """Отправляет уведомление о техническом обслуживании всем пользователям"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Получаем всех пользователей
        cursor.execute('SELECT DISTINCT telegram_user_id FROM bot_users WHERE telegram_user_id IS NOT NULL')
        users = cursor.fetchall()
        conn.close()
        
        app = Application.builder().token(BOT_TOKEN).build()
        await app.initialize()
        
        sent_count = 0
        for user in users:
            try:
                await app.bot.send_message(
                    chat_id=user[0],
                    text=f"🔧 **УВЕДОМЛЕНИЕ О ТЕХНИЧЕСКОМ ОБСЛУЖИВАНИИ**\n\n{message}"
                )
                sent_count += 1
            except Exception as e:
                print(f"❌ Не удалось отправить уведомление пользователю {user[0]}: {e}")
        
        await app.shutdown()
        print(f"✅ Уведомление о техобслуживании отправлено {sent_count} пользователям")
        
    except Exception as e:
        print(f"❌ Ошибка при отправке уведомлений: {e}")
async def maintenance_schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запланированный технический перерыв"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_operator(user_id):
        await query.edit_message_text("❌ Доступ запрещен")
        return
    
    context.user_data['waiting_for_maintenance_date'] = True
    
    keyboard = [
        [InlineKeyboardButton("🔙 Отменить", callback_data="operator_maintenance")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📅 **Запланировать технический перерыв**\n\n"
        "Введите дату и время перерыва в формате:\n"
        "`ДД.ММ.ГГГГ ЧЧ:ММ`\n\n"
        "Например: `15.11.2024 14:00`\n\n"
        "💡 Уведомление будет отправлено всем пользователям заранее.",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
async def handle_maintenance_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода даты технического перерыва с проверкой контекста"""
    if not context.user_data.get('waiting_for_maintenance_date'):
        # 🔧 ИГНОРИРУЕМ СООБЩЕНИЕ, ЕСЛИ НЕ ЖДЕМ ДАТУ
        return
    
    try:
        date_text = update.message.text.strip()
        maintenance_datetime = datetime.strptime(date_text, '%d.%m.%Y %H:%M')
        
        # 🔧 ПРОВЕРЯЕМ, ЧТО ДАТА В БУДУЩЕМ
        if maintenance_datetime <= datetime.now():
            await update.message.reply_text(
                "❌ Дата должна быть в будущем!\n\n"
                "Введите дату и время перерыва в формате:\n"
                "`ДД.ММ.ГГГГ ЧЧ:ММ`\n\n"
                "Например: `15.11.2024 14:00`",
                parse_mode='HTML'
            )
            return
        
        # Сохраняем запланированный перерыв
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        message = f"🔧 Уведомление о запланированном техническом перерыве: {date_text} будет назначен технический перерыв системы. Приносим извинения за временные неудобства."
        
        cursor.execute('''
            INSERT INTO maintenance_mode (is_active, message, start_time, end_time)
            VALUES (0, ?, ?, ?)
        ''', (message, 
              maintenance_datetime.strftime('%Y-%m-%d %H:%M:%S'),
              (maintenance_datetime + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')))
        
        conn.commit()
        conn.close()
        
        # 🔧 СБРАСЫВАЕМ ФЛАГ ОЖИДАНИЯ
        context.user_data['waiting_for_maintenance_date'] = False
        
        # 🔧 ОТПРАВЛЯЕМ УВЕДОМЛЕНИЕ О ПЕРЕРЫВЕ
        await send_maintenance_notification_to_all(message)
        
        keyboard = [
            [InlineKeyboardButton("🔧 К управлению", callback_data="operator_maintenance")],
            [InlineKeyboardButton("🔙 В панель оператора", callback_data="operator_panel_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ **Технический перерыв запланирован!**\n\n"
            f"📅 Дата: {date_text}\n"
            f"⏰ Продолжительность: 1 час\n\n"
            f"Все пользователи получили уведомление.",
            reply_markup=reply_markup
        )
        
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат даты!\n\n"
            "Введите дату в формате: `ДД.ММ.ГГГГ ЧЧ:ММ`\n"
            "Например: `15.11.2024 14:00`\n\n"
            "Попробуйте еще раз:",
            parse_mode='HTML'
        )
async def handle_salon_confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик подтверждения записи салоном"""
    query = update.callback_query
    await query.answer()
    
    try:
        booking_id = int(query.data.split('_')[2])
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Получаем информацию о записи
        cursor.execute('''
            SELECT b.client_name, b.booking_date, s.name, m.name, sl.name, b.id
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            JOIN salons sl ON b.salon_id = sl.id
            WHERE b.id = ?
        ''', (booking_id,))
        
        booking = cursor.fetchone()
        
        if not booking:
            await query.edit_message_text("❌ Запись не найдена")
            conn.close()
            return
        
        client_name, booking_date, service_name, master_name, salon_name, booking_id = booking
        
        # Отмечаем запись как завершенную
        cursor.execute('UPDATE bookings SET status = "completed", completed = 1 WHERE id = ?', (booking_id,))
        conn.commit()
        conn.close()
        
        # 🔧 ДОБАВЛЯЕМ В ИСТОРИЮ
        add_booking_to_history(booking_id, 'completed', 'salon', 'Запись подтверждена салоном')
        
        await query.edit_message_text(
            f"✅ **Запись подтверждена!**\n\n"
            f"👤 Клиент: {client_name}\n"
            f"💅 Услуга: {service_name}\n"
            f"👨‍💼 Мастер: {master_name}\n\n"
            f"Запись успешно завершена."
        )
        
    except Exception as e:
        await query.edit_message_text("❌ Ошибка при подтверждении записи")
        logger.error(f"Error in handle_salon_confirm_booking: {e}")
async def handle_salon_cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик отмены записи салоном"""
    query = update.callback_query
    await query.answer()
    
    try:
        booking_id = int(query.data.split('_')[2])
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Получаем информацию о записи
        cursor.execute('''
            SELECT b.client_name, b.booking_date, s.name, m.name, sl.name, b.id
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            JOIN salons sl ON b.salon_id = sl.id
            WHERE b.id = ?
        ''', (booking_id,))
        
        booking = cursor.fetchone()
        
        if not booking:
            await query.edit_message_text("❌ Запись не найдена")
            conn.close()
            return
        
        client_name, booking_date, service_name, master_name, salon_name, booking_id = booking
        
        # Отменяем запись
        cursor.execute('UPDATE bookings SET status = "cancelled" WHERE id = ?', (booking_id,))
        conn.commit()
        conn.close()
        
        # 🔧 ДОБАВЛЯЕМ В ИСТОРИЮ
        add_booking_to_history(booking_id, 'cancelled', 'salon', 'Запись отменена салоном')
        
        await query.edit_message_text(
            f"❌ **Запись отменена!**\n\n"
            f"👤 Клиент: {client_name}\n"
            f"💅 Услуга: {service_name}\n"
            f"👨‍💼 Мастер: {master_name}\n\n"
            f"Запись была отменена салоном."
        )
        
    except Exception as e:
        await query.edit_message_text("❌ Ошибка при отмене записи")
        logger.error(f"Error in handle_salon_cancel_booking: {e}")
async def send_salon_confirmation_notification(booking_id):
    """Отправляет уведомление салону для подтверждения записи в начале времени услуги"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT b.booking_date, s.name as service_name, m.name as master_name,
                   b.client_name, b.client_phone, sl.name as salon_name, 
                   sl.telegram_chat_id, b.id, s.duration
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            JOIN salons sl ON b.salon_id = sl.id
            WHERE b.id = ?
        ''', (booking_id,))
        
        booking = cursor.fetchone()
        
        if not booking or not booking[6]:  # telegram_chat_id
            conn.close()
            return False
        
        booking_date, service_name, master_name, client_name, client_phone, salon_name, salon_chat_id, booking_id, duration = booking
        
        # 🔧 ОБРАБАТЫВАЕМ ДАТУ
        try:
            if isinstance(booking_date, str):
                booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
            else:
                booking_datetime = booking_date
            
            formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
            
            # 🔧 ВЫЧИСЛЯЕМ ВРЕМЯ ОКОНЧАНИЯ УСЛУГИ
            end_time = booking_datetime + timedelta(minutes=duration)
            formatted_end_time = end_time.strftime('%H:%M')
            
        except:
            formatted_date = "дата не определена"
            formatted_end_time = "время не определено"
        
        notification_text = (
            f"🕐 **ПОДТВЕРЖДЕНИЕ ЗАПИСИ**\n\n"
            f"Клиент пришел на запись:\n\n"
            f"👤 Клиент: {client_name}\n"
            f"📞 Телефон: {client_phone}\n"
            f"💅 Услуга: {service_name}\n"
            f"👨‍💼 Мастер: {master_name}\n"
            f"⏰ Время: {formatted_date}\n"
            f"⏱️ Длительность: {duration} мин.\n"
            f"🏁 Окончание: {formatted_end_time}\n\n"
            f"Подтвердите, что запись состоялась:"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить запись", callback_data=f"salon_confirm_{booking_id}"),
                InlineKeyboardButton("❌ Отмена записи", callback_data=f"salon_cancel_{booking_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        app = Application.builder().token(BOT_TOKEN).build()
        await app.initialize()
        
        try:
            await app.bot.send_message(
                chat_id=salon_chat_id,
                text=notification_text,
                reply_markup=reply_markup
            )
            print(f"✅ Уведомление для подтверждения отправлено салону {salon_name}")
            success = True
            
            # 🔧 ДОБАВЛЯЕМ ЗАПИСЬ В ИСТОРИЮ
            add_booking_to_history(booking_id, 'reminded', 'system', 'Уведомление салону о начале записи')
            
        except Exception as e:
            print(f"❌ Не удалось отправить уведомление салону: {e}")
            success = False
        
        await app.shutdown()
        conn.close()
        return success
        
    except Exception as e:
        print(f"❌ Ошибка при отправке уведомления салону: {e}")
        return False
async def check_salon_access(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет, активен ли салон и доступен ли для использования"""
    salon_id = context.user_data.get('current_salon_id')
    if not salon_id:
        return False
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT is_active FROM salons WHERE id = ?', (salon_id,))
    result = cursor.fetchone()
    conn.close()
    
    return result and result[0]  # True если салон активен
async def book_service_main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_maintenance_mode(update, context):
        return
    """Главный обработчик записи на услугу"""
    # 🔒 ПРОВЕРКА ДОСТУПА К САЛОНУ
    if not context.user_data.get('current_salon_id'):
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.answer("❌ Для записи используйте ссылку салона", show_alert=True)
        return
    
    # 🔒 ПРОВЕРКА АКТИВНОСТИ САЛОНА
    if not await check_salon_access(context):
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                "❌ **Салон временно недоступен**\n\n"
                "Этот салон временно отключен администратором.\n"
                "Пожалуйста, обратитесь к администратору салона."
            )
        return
    
    await book_service_callback(update, context)
async def show_masters_main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_maintenance_mode(update, context):
        return
    """Показ мастеров через инлайн-кнопку"""
    if hasattr(update, 'callback_query') and update.callback_query:
        query = update.callback_query
        await query.answer()
        # Используем существующую функцию show_masters_callback
        await show_masters_callback(update, context)
    else:
        await show_masters_callback(update, context)
async def show_services_main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_maintenance_mode(update, context):
        return
    """Показ услуг через инлайн-кнопку"""
    if hasattr(update, 'callback_query') and update.callback_query:
        query = update.callback_query
        await query.answer()
        # Используем существующую функцию show_services_callback
        await show_services_callback(update, context)
    else:
        await show_services_callback(update, context)
async def my_bookings_main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_maintenance_mode(update, context):
        return
    """Обработчик кнопки 'Мои записи' из главного меню"""
    query = update.callback_query
    await query.answer()
    
    print(f"🔍 Нажата кнопка 'Мои записи' пользователем {query.from_user.id}")
    
    # Просто вызываем существующую функцию my_bookings
    await my_bookings(update, context)
async def show_client_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню для клиентов в салоне"""
    salon_name = context.user_data.get('current_salon_name', 'салон')
    
    keyboard = [
        [InlineKeyboardButton("💅 Записаться на услугу", callback_data="book_service_main")],
        [InlineKeyboardButton("👨‍💼 Наши мастера", callback_data="show_masters_main")],
        [InlineKeyboardButton("💎 Наши услуги", callback_data="show_services_main")],
        [InlineKeyboardButton("📋 Мои записи", callback_data="my_bookings_main")],
        [InlineKeyboardButton("📚 История записей", callback_data="client_booking_history")],
        [InlineKeyboardButton("❓ Помощь", callback_data="show_faq")],
        [InlineKeyboardButton("🔐 Вход для владельцев", callback_data="owner_login_start")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu_return")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(
            f"🏪 **{salon_name}**\n\n"
            f"Выберите действие:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            f"🏪 **{salon_name}**\n\n"
            f"Выберите действие:",
            reply_markup=reply_markup
        )
async def client_main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик главного меню клиента"""
    await show_client_main_menu(update, context)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    if await check_maintenance_mode(update, context):
        return    
    print(f"🔍 Команда /start от пользователя {user.id} ({user.first_name})")
    
    # 🔧 РЕГИСТРИРУЕМ/ОБНОВЛЯЕМ ПОЛЬЗОВАТЕЛЯ
    register_bot_user(user.id, user.username, user.first_name)
    update_user_activity(user.id)
    
    # 🔧 ЕСЛИ ЭТО ОПЕРАТОР
    if is_operator(user.id):
        print(f"🔍 Пользователь {user.id} - оператор")
        
        # Если оператор уже авторизован как владелец
        if context.user_data.get('owner_authenticated'):
            salon_name = context.user_data.get('current_salon_name', 'ваш салон')
            
            keyboard = [
                [InlineKeyboardButton("👨‍💼 Управление мастерами", callback_data="owner_manage_masters")],
                [InlineKeyboardButton("💅 Управление услугами", callback_data="owner_manage_services")],
                [InlineKeyboardButton("⚙️ Настройки салона", callback_data="owner_salon_settings")],
                [InlineKeyboardButton("📊 Статистика", callback_data="owner_stats")],
                [InlineKeyboardButton("🔗 Моя ссылка салона", callback_data="owner_get_link")],
                [InlineKeyboardButton("👑 Панель оператора", callback_data="operator_panel_main")],
                [InlineKeyboardButton("🚪 Выйти из системы", callback_data="owner_logout_handler")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"🏪 **Панель управления {salon_name}**\n\n"
                f"🔧 Вы вошли как оператор и владелец салона\n\n"
                f"Выберите раздел управления:",
                reply_markup=reply_markup
            )
            return
        
        # Если оператор не авторизован как владелец
        keyboard = [
            [InlineKeyboardButton("👑 Панель оператора", callback_data="operator_panel_main")],
            [InlineKeyboardButton("🔐 Войти как владелец", callback_data="owner_login_start")],
            [InlineKeyboardButton("🔗 Все ссылки салонов", callback_data="operator_all_links")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "👑 **Панель оператора**\n\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )
        return
    
    # 🔧 ЕСЛИ ПОЛЬЗОВАТЕЛЬ АВТОРИЗОВАН КАК ВЛАДЕЛЕЦ
    if context.user_data.get('owner_authenticated'):
        salon_name = context.user_data.get('current_salon_name', 'ваш салон')
        
        keyboard = [
            [InlineKeyboardButton("👨‍💼 Управление мастерами", callback_data="owner_manage_masters")],
            [InlineKeyboardButton("💅 Управление услугами", callback_data="owner_manage_services")],
            [InlineKeyboardButton("⚙️ Настройки салона", callback_data="owner_salon_settings")],
            [InlineKeyboardButton("📊 Статистика", callback_data="owner_stats")],
            [InlineKeyboardButton("🔗 Моя ссылка салона", callback_data="owner_get_link")],
            [InlineKeyboardButton("❓ Помощь", callback_data="show_faq")],
            [InlineKeyboardButton("🚪 Выйти", callback_data="owner_logout_handler")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🏪 **Добро пожаловать в {salon_name}!** 🎉\n\n"
            f"Выберите раздел управления:",
            reply_markup=reply_markup
        )
        return
    
    # 🔧 ПРОВЕРЯЕМ СТАТУС КАПЧИ
    user_captcha_passed = get_user_captcha_status(user.id)
    
    # 🔧 ЕСЛИ КАПЧА УЖЕ ПРОЙДЕНА
    if user_captcha_passed:
        # Проверяем, есть ли ссылка салона
        if context.args:
            salon_token = context.args[0]
            conn = sqlite3.connect('salons.db')
            cursor = conn.cursor()
            cursor.execute('SELECT id, name, is_active FROM salons WHERE unique_token = ?', (salon_token,))
            salon = cursor.fetchone()
            conn.close()
            if salon:
               salon_id, salon_name, is_active = salon
               
            if not is_active:
                await update.message.reply_text(
                    "❌ **Салон временно недоступен**\n\n"
                    "Этот салон временно отключен администратором.\n"
                    "Пожалуйста, обратитесь к администратору салона для уточнения информации."
                )
                return
            if salon:
                context.user_data['current_salon_id'] = salon[0]
                context.user_data['current_salon_name'] = salon[1]
                context.user_data['salon_token'] = salon_token
                
                # Клавиатура для клиента в салоне
                keyboard = [
                    [InlineKeyboardButton("💅 Записаться на услугу", callback_data="book_service_main")],
                    [InlineKeyboardButton("👨‍💼 Наши мастера", callback_data="show_masters_main")],
                    [InlineKeyboardButton("💎 Наши услуги", callback_data="show_services_main")],
                    [InlineKeyboardButton("📋 Мои записи", callback_data="my_bookings_main")],
                    [InlineKeyboardButton("📚 История записей", callback_data="client_booking_history")],
                    [InlineKeyboardButton("❓ Помощь", callback_data="show_faq")],
                    [InlineKeyboardButton("🔐 Вход для владельцев", callback_data="owner_login_start")],
                    [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu_return")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"🏪 Добро пожаловать в {salon[1]}! 🎉\n\n"
                    f"Выберите действие:",
                    reply_markup=reply_markup
                )
                return
        
        # 🔧 ОБЫЧНОЕ ПРИВЕТСТВИЕ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ С ПРОЙДЕННОЙ КАПЧЕЙ
        keyboard = [
            [InlineKeyboardButton("🔐 Вход для владельцев", callback_data="owner_login_start")],
            [InlineKeyboardButton("❓ Помощь", callback_data="show_faq")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"Привет {user.first_name}! 🎉\n"
            f"Добро пожаловать в систему записи!\n\n"
            f"👥 **Для клиентов:**\n"
            f"• Используйте уникальную ссылку салона\n\n"
            f"🏪 **Для владельцев салонов:**\n"
            f"• Войдите в систему управления\n\n",
            reply_markup=reply_markup
        )
        return
    
    # 🔧 ЕСЛИ КАПЧА НЕ ПРОЙДЕНА - ЗАПРАШИВАЕМ КАПЧУ
    print(f"🔍 Капча не пройдена, запрашиваем капчу")
    await ask_captcha(update, context)
async def fix_captcha_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для исправления статуса капчи (временная)"""
    user = update.message.from_user
    user_id = user.id
    
    print(f"🔧 Принудительно исправляем капчу для пользователя {user_id}")
    
    # Принудительно устанавливаем капчу как пройденную
    success = mark_captcha_passed(user_id)
    
    if success:
        await update.message.reply_text("✅ Статус капчи исправлен! Попробуйте /start снова.")
    else:
        await update.message.reply_text("❌ Не удалось исправить статус капчи.")
async def ask_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрос капчи при первом входе"""
    question, answer = generate_captcha()
    context.user_data['captcha_answer'] = answer
    context.user_data['waiting_for_captcha'] = True
    
    await update.message.reply_text(
        f"🤖 **Добро пожаловать!**\n\n"
        f"Пройдите простую проверку:\n"
        f"**{question}** = ?\n\n"
        f"Введите ответ цифрами:"
    )
async def verify_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка капчи"""
    if not context.user_data.get('waiting_for_captcha'):
        print("❌ verify_captcha: флаг waiting_for_captcha не установлен")
        return False
    
    user = update.message.from_user
    user_answer = update.message.text.strip()
    correct_answer = context.user_data.get('captcha_answer')
    
    print(f"🔍 Проверка капчи: пользователь {user.id}, ответ '{user_answer}', правильный '{correct_answer}'")
    
    if user_answer == correct_answer:
        # 🔧 ПОЛНАЯ ОЧИСТКА КОНТЕКСТА КАПЧИ
        context.user_data['waiting_for_captcha'] = False
        context.user_data.pop('captcha_answer', None)
        
        print(f"🔍 Капча верная, вызываем mark_captcha_passed для {user.id}")
        
        # 🔧 ОТМЕЧАЕМ В БАЗЕ, ЧТО КАПЧА ПРОЙДЕНА
        success = mark_captcha_passed(user.id)
        update_user_activity(user.id)
        
        print(f"🔍 Результат mark_captcha_passed: {success}")
        
        # 🔧 ПРОВЕРЯЕМ СРАЗУ ПОСЛЕ ОБНОВЛЕНИЯ
        new_status = get_user_captcha_status(user.id)
        print(f"🔍 Статус капчи после обновления: {new_status}")
        
        await update.message.reply_text(
            "✅ **Проверка пройдена!**\n\n"
            "Теперь вы можете пользоваться ботом.\n"
            "Используйте команды из меню 📋"
        )
        return True
    else:
        # Генерируем новую капчу при ошибке
        question, answer = generate_captcha()
        context.user_data['captcha_answer'] = answer
        
        await update.message.reply_text(
            f"❌ **Неверный ответ!**\n\n"
            f"Попробуйте еще раз:\n"
            f"**{question}** = ?\n\n"
            f"Введите ответ цифрами:"
        )
        return False
async def show_masters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ мастеров с проверкой авторизации для владельцев"""
    # Если пользователь авторизован как владелец, показываем расширенную информацию
    if context.user_data.get('owner_authenticated'):
        salon_id = context.user_data.get('current_salon_id')
        salon_name = context.user_data.get('current_salon_name', 'ваш салон')
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        cursor.execute('SELECT name, specialization FROM masters WHERE salon_id = ? AND is_active = 1', (salon_id,))
        masters = cursor.fetchall()
        conn.close()
        
        if masters:
            masters_text = f"👨‍💼 Мастера {salon_name}:\n\n"
            for master in masters:
                masters_text += f"• {master[0]} - {master[1]}\n"
            
            # Добавляем кнопки для владельцев
            keyboard = [[InlineKeyboardButton("⚙️ Управление мастерами", callback_data="owner_manage_masters")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(masters_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text("Мастера пока не добавлены")
    else:
        # Обычный показ для клиентов
        salon_id = context.user_data.get('current_salon_id', 1)
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        cursor.execute('SELECT name, specialization FROM masters WHERE salon_id = ? AND is_active = 1', (salon_id,))
        masters = cursor.fetchall()
        conn.close()
        
        salon_name = context.user_data.get('current_salon_name', 'Тестовый салон красоты')
        
        if masters:
            masters_text = f"👨‍💼 Мастера {salon_name}:\n\n"
            for master in masters:
                masters_text += f"• {master[0]} - {master[1]}\n"
            await update.message.reply_text(masters_text)
        else:
            await update.message.reply_text("Мастера пока не добавлены")
async def show_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    salon_id = context.user_data.get('current_salon_id', 1)
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name, price, duration, is_range_price FROM services WHERE salon_id = ? AND is_active = 1', (salon_id,))
    services = cursor.fetchall()
    conn.close()
    
    salon_name = context.user_data.get('current_salon_name', 'Тестовый салон красоты')
    
    if services:
        services_text = f"💅 Услуги {salon_name}:\n\n"
        for service in services:
            name, price, duration, is_range_price = service
            if is_range_price:
                # Диапазон цен
                price_text = f"{price} руб."
            else:
                # Фиксированная цена
                price_text = f"{price} руб."
            services_text += f"• {name} - {price_text} ({duration} мин.)\n"
        await update.message.reply_text(services_text)
    else:
        await update.message.reply_text("Услуги пока не добавлены")
async def book_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запись на услугу - работает и для сообщений, и для callback"""
    
    # 🔧 ОПРЕДЕЛЯЕМ ТИП UPDATE
    if hasattr(update, 'message') and update.message:
        # Это обычное сообщение
        message_func = update.message.reply_text
        user_message = update.message
    elif hasattr(update, 'callback_query') and update.callback_query:
        # Это callback query
        query = update.callback_query
        await query.answer()
        message_func = query.edit_message_text
        user_message = query
    else:
        # Неизвестный тип update
        return
    
    # 🔧 ПРОВЕРЯЕМ, ЧТО ПОЛЬЗОВАТЕЛЬ В КОНКРЕТНОМ САЛОНЕ
    salon_id = context.user_data.get('current_salon_id')
    if not salon_id:
        await message_func(
            "❌ **Не выбран салон!**\n\n"
            "Пожалуйста, используйте уникальную ссылку салона для записи.\n"
            "Если у вас нет ссылки, обратитесь к администратору салона."
        )
        return
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM services WHERE salon_id = ? AND is_active = 1', (salon_id,))
    services = cursor.fetchall()
    conn.close()
    
    if not services:
        await message_func("❌ Услуги пока не доступны")
        return
    
    salon_name = context.user_data.get('current_salon_name', 'салон')
    
    keyboard = [[InlineKeyboardButton(service[1], callback_data=f"service_{service[0]}")] for service in services]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message_func(
        f"💅 **Выберите услугу в {salon_name}:**",
        reply_markup=reply_markup
    )
async def handle_service_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = query.data.split('_')[1]
    context.user_data['service_id'] = service_id
    
    salon_id = context.user_data.get('current_salon_id', 1)
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # 🔧 ИСПРАВЛЕНИЕ: Выбираем только мастеров, которые могут выполнять эту услугу
    cursor.execute('''
        SELECT m.id, m.name, m.specialization 
        FROM masters m
        JOIN master_services ms ON m.id = ms.master_id
        WHERE m.salon_id = ? AND m.is_active = 1 AND ms.service_id = ?
    ''', (salon_id, service_id))
    
    masters = cursor.fetchall()
    conn.close()
    
    if not masters:
        await query.edit_message_text(
            "❌ **Нет доступных мастеров для этой услуги**\n\n"
            "К сожалению, сейчас нет мастеров, которые могут выполнить выбранную услугу.\n"
            "Пожалуйста, выберите другую услугу или обратитесь к администратору."
        )
        return
    
    keyboard = []
    for master in masters:
        # Добавляем специализацию в текст кнопки
        button_text = f"{master[1]} ({master[2]})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"master_{master[0]}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Получаем название услуги для сообщения
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM services WHERE id = ?', (service_id,))
    service_name = cursor.fetchone()[0]
    conn.close()
    
    await query.edit_message_text(
        f"💅 Услуга: <b>{service_name}</b>\n\n"
        f"👨‍💼 Выберите мастера:\n"
        f"(показаны только мастера с нужной специализацией)",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
async def handle_master_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора мастера с переходом к календарю"""
    query = update.callback_query
    await query.answer()
    
    # Сохраняем ID мастера
    master_id = query.data.split('_')[1]
    context.user_data['master_id'] = master_id
    
    # Получаем имя мастера для отладки
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM masters WHERE id = ?', (master_id,))
    master_name = cursor.fetchone()
    conn.close()
    
    print(f"🔧 Выбран мастер: ID={master_id}, Name={master_name}")
    
    # Переходим к календарю
    await show_calendar(update, context, week_offset=0)
async def show_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE, week_offset=0):
    """Показ календаря с перелистыванием по неделям"""
    query = update.callback_query
    if query:
        await query.answer()
    
    print(f"🔧 show_calendar вызван с week_offset={week_offset}")
    
    salon_id = context.user_data.get('current_salon_id', 1)
    today = datetime.now()
    
    # Вычисляем начало недели (понедельник)
    start_of_week = today + timedelta(days=-today.weekday() + (week_offset * 7))
    
    # Русские названия дней недели
    russian_weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    
    keyboard = []
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Показываем 7 дней текущей недели
    for i in range(7):
        date = start_of_week + timedelta(days=i)
        day_of_week = date.weekday()
        
        # Проверяем, рабочий ли это день
        cursor.execute('SELECT is_working FROM working_hours WHERE salon_id = ? AND day_of_week = ?', (salon_id, day_of_week))
        working_day = cursor.fetchone()
        
        date_str = date.strftime('%d.%m.%Y')
        weekday = russian_weekdays[day_of_week]
        
        # Проверяем, не прошедшая ли это дата
        is_past_date = date.date() < today.date()
        is_today = date.date() == today.date()
        
        if working_day and working_day[0] and not is_past_date:
            # Рабочий день в будущем - активная кнопка
            if is_today:
                button_text = f"🟢 {date_str} ({weekday}) - Сегодня"
            else:
                button_text = f"✅ {date_str} ({weekday})"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"date_{date.strftime('%Y-%m-%d')}")])
        else:
            # Выходной или прошедший день - неактивная кнопка
            if is_past_date:
                button_text = f"❌ {date_str} ({weekday}) - Прошедшая"
            elif is_today and (not working_day or not working_day[0]):
                button_text = f"🚫 {date_str} ({weekday}) - Выходной"
            else:
                button_text = f"🚫 {date_str} ({weekday}) - Выходной"
            keyboard.append([InlineKeyboardButton(button_text, callback_data="ignore")])
    
    conn.close()
    
    # Кнопки навигации
    nav_buttons = []
    
    # Кнопка "Назад" показывается всегда, кроме текущей недели
    if week_offset > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Предыдущая неделя", callback_data=f"calendar_prev_{week_offset-1}"))
    
    # Кнопка "Вперед" показывается всегда
    nav_buttons.append(InlineKeyboardButton("Следующая неделя ▶️", callback_data=f"calendar_next_{week_offset+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопка возврата к выбору мастера
    keyboard.append([InlineKeyboardButton("« Назад к выбору мастера", callback_data="back_to_master")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Формируем заголовок с диапазоном дат недели
    end_of_week = start_of_week + timedelta(days=6)
    week_range = f"{start_of_week.strftime('%d.%m.%Y')} - {end_of_week.strftime('%d.%m.%Y')}"
    
    # Определяем текст для текущей/будущей недели
    if week_offset == 0:
        week_info = "Текущая неделя"
    elif week_offset > 0:
        week_info = f"Через {week_offset} недель"
    else:
        week_info = f"{-week_offset} недель назад"
    
    message_text = (
        f"📅 **Выберите дату записи**\n"
        f"🗓️ Неделя: {week_range}\n"
        f"📋 {week_info}\n\n"
        f"🟢 Сегодня | ✅ Доступные даты\n"
        f"🚫 Выходные | ❌ Прошедшие даты\n\n"
        f"Используйте кнопки ниже для навигации по неделям"
    )
    
    # ПРОСТАЯ И НАДЕЖНАЯ ЛОГИКА
    if query:
        # Для callback query - редактируем сообщение
        await query.edit_message_text(message_text, reply_markup=reply_markup)
    else:
        # Для обычного сообщения - отправляем новое
        await update.message.reply_text(message_text, reply_markup=reply_markup)
    
    print("🔧 Календарь успешно отображен")
async def handle_calendar_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик навигации по календарю"""
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split('_')
    action = data_parts[1]  # prev или next
    week_offset = int(data_parts[2])
    
    await show_calendar(update, context, week_offset)
async def handle_ignore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для неактивных кнопок"""
    query = update.callback_query
    await query.answer("❌ Эта дата недоступна для записи", show_alert=True)
async def handle_back_to_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат к выбору мастера"""
    query = update.callback_query
    await query.answer()
    
    # Восстанавливаем контекст для возврата к выбору мастера
    service_id = context.user_data.get('service_id')
    salon_id = context.user_data.get('current_salon_id', 1)
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Получаем мастеров для выбранной услуги
    cursor.execute('''
        SELECT m.id, m.name, m.specialization 
        FROM masters m
        JOIN master_services ms ON m.id = ms.master_id
        WHERE m.salon_id = ? AND m.is_active = 1 AND ms.service_id = ?
    ''', (salon_id, service_id))
    
    masters = cursor.fetchall()
    conn.close()
    
    if not masters:
        await query.edit_message_text(
            "❌ **Нет доступных мастеров для этой услуги**\n\n"
            "К сожалению, сейчас нет мастеров, которые могут выполнить выбранную услугу.\n"
            "Пожалуйста, выберите другую услугу или обратитесь к администратору."
        )
        return
    
    keyboard = []
    for master in masters:
        button_text = f"{master[1]} ({master[2]})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"master_{master[0]}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Получаем название услуги для сообщения
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM services WHERE id = ?', (service_id,))
    service_name = cursor.fetchone()[0]
    conn.close()
    
    await query.edit_message_text(
        f"💅 Услуга: <b>{service_name}</b>\n\n"
        f"👨‍💼 Выберите мастера:\n"
        f"(показаны только мастера с нужной специализацией)",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    """Возврат к выбору мастера"""
    query = update.callback_query
    await query.answer()
    
    # Восстанавливаем контекст для возврата к выбору мастера
    service_id = context.user_data.get('service_id')
    salon_id = context.user_data.get('current_salon_id', 1)
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Получаем мастеров для выбранной услуги
    cursor.execute('''
        SELECT m.id, m.name, m.specialization 
        FROM masters m
        JOIN master_services ms ON m.id = ms.master_id
        WHERE m.salon_id = ? AND m.is_active = 1 AND ms.service_id = ?
    ''', (salon_id, service_id))
    
    masters = cursor.fetchall()
    conn.close()
    
    if not masters:
        await query.edit_message_text(
            "❌ **Нет доступных мастеров для этой услуги**\n\n"
            "К сожалению, сейчас нет мастеров, которые могут выполнить выбранную услугу.\n"
            "Пожалуйста, выберите другую услугу или обратитесь к администратору."
        )
        return
    
    keyboard = []
    for master in masters:
        button_text = f"{master[1]} ({master[2]})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"master_{master[0]}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Получаем название услуги для сообщения
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM services WHERE id = ?', (service_id,))
    service_name = cursor.fetchone()[0]
    conn.close()
    
    await query.edit_message_text(
        f"💅 Услуга: <b>{service_name}</b>\n\n"
        f"👨‍💼 Выберите мастера:\n"
        f"(показаны только мастера с нужной специализацией)",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
async def handle_date_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['selected_date'] = query.data.split('_')[1]
    await show_time_slots(update, context, context.user_data['selected_date'])
async def show_time_slots(update: Update, context: ContextTypes.DEFAULT_TYPE, selected_date):
    query = update.callback_query
    await query.answer()
    
    salon_id = context.user_data.get('current_salon_id', 1)
    selected_date_obj = datetime.strptime(selected_date, '%Y-%m-%d')
    day_of_week = selected_date_obj.weekday()
    master_id = context.user_data.get('master_id')
    service_id = context.user_data.get('service_id')
    
    # Получаем рабочее время для этого дня
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT start_time, end_time FROM working_hours WHERE salon_id = ? AND day_of_week = ?', (salon_id, day_of_week))
    working_hours = cursor.fetchone()
    conn.close()
    
    if not working_hours:
        # 🔧 ДОБАВЛЯЕМ КНОПКУ НАЗАД ДАЖЕ ПРИ ОШИБКЕ
        keyboard = [
            [InlineKeyboardButton("« Назад к датам", callback_data="back_to_calendar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("❌ На выбранную дату салон не работает", reply_markup=reply_markup)
        return
    
    # Преобразуем время в часы и минуты
    start_time = datetime.strptime(working_hours[0], '%H:%M')
    end_time = datetime.strptime(working_hours[1], '%H:%M')
    
    # 🔧 ВЫЧИТАЕМ ДЛИТЕЛЬНОСТЬ УСЛУГИ ИЗ КОНЕЧНОГО ВРЕМЕНИ
    service_duration = 0
    if service_id:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        cursor.execute('SELECT duration FROM services WHERE id = ?', (service_id,))
        service_duration_result = cursor.fetchone()
        conn.close()
        
        if service_duration_result and service_duration_result[0]:
            service_duration = service_duration_result[0]
            end_time = end_time - timedelta(minutes=service_duration)
            print(f"🔍 Учтена длительность услуги: {service_duration} мин. Новое конечное время: {end_time.strftime('%H:%M')}")
    
    # Генерируем временные слоты с интервалом 30 минут
    time_slots = []
    current_time = start_time
    while current_time <= end_time:
        time_slots.append(current_time.strftime('%H:%M'))
        current_time += timedelta(minutes=30)
    
    # 🔧 ПРОВЕРЯЕМ ЗАНЯТОСТЬ МАСТЕРА ДЛЯ КАЖДОГО СЛОТА
    available_slots = []
    for time_slot in time_slots:
        # Проверяем, не прошедшее ли это время (для сегодняшней даты)
        if selected_date_obj.date() == datetime.now().date():
            slot_time = datetime.strptime(time_slot, '%H:%M').time()
            if slot_time <= datetime.now().time():
                continue  # Пропускаем прошедшее время
        
        # Проверяем доступность времени у мастера
        booking_datetime = datetime.strptime(f"{selected_date} {time_slot}", '%Y-%m-%d %H:%M')
        is_available, message = is_time_slot_available(salon_id, booking_datetime, master_id, service_id)
        
        if is_available:
            available_slots.append(time_slot)
    
    # 🔧 ЕСЛИ НЕТ ДОСТУПНЫХ СЛОТОВ - ПОКАЗЫВАЕМ СООБЩЕНИЕ С КНОПКОЙ НАЗАД
    if not available_slots:
        formatted_date = selected_date_obj.strftime('%d.%m.%Y')
        
        # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ НАЗАД
        keyboard = [
            [InlineKeyboardButton("« Назад к датам", callback_data="back_to_calendar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"❌ **На {formatted_date} нет доступного времени**\n\n"
            f"Все временные слоты заняты или недоступны.\n"
            f"Пожалуйста, выберите другую дату",
            reply_markup=reply_markup
        )
        return
    
    # Создаем клавиатуру только для доступных слотов
    keyboard = []
    row = []
    for i, time_slot in enumerate(available_slots):
        row.append(InlineKeyboardButton(time_slot, callback_data=f"time_{time_slot}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    # 🔧 ДОБАВЛЯЕМ КНОПКУ НАЗАД В ЛЮБОМ СЛУЧАЕ
    keyboard.append([InlineKeyboardButton("« Назад к датам", callback_data="back_to_calendar")])
    
    formatted_date = selected_date_obj.strftime('%d.%m.%Y')
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Получаем имя мастера для сообщения
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM masters WHERE id = ?', (master_id,))
    master_name = cursor.fetchone()[0]
    conn.close()
    
    message_text = (
        f"🕐 **Выберите время на {formatted_date}:**\n"
        f"👨‍💼 Мастер: {master_name}\n"
        f"⏰ Рабочее время: {working_hours[0]} - {working_hours[1]}\n"
    )
    
    if service_duration > 0:
        message_text += f"⏱️ Длительность услуги: {service_duration} мин.\n"
    
    message_text += f"📅 Доступные временные интервалы:"
    
    await query.edit_message_text(message_text, reply_markup=reply_markup)
async def handle_time_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected_time = query.data.split('_')[1]
    
    # 🔧 ФИНАЛЬНАЯ ПРОВЕРКА ДОСТУПНОСТИ ВРЕМЕНИ
    selected_date = context.user_data['selected_date']
    booking_datetime = datetime.strptime(f"{selected_date} {selected_time}", '%Y-%m-%d %H:%M')
    
    salon_id = context.user_data.get('current_salon_id')
    master_id = context.user_data.get('master_id')
    service_id = context.user_data.get('service_id')
    
    is_available, message = is_time_slot_available(salon_id, booking_datetime, master_id, service_id)
    
    if not is_available:
        await query.edit_message_text(
            f"❌ **Время стало недоступно!**\n\n"
            f"{message}\n\n"
            f"Пожалуйста, выберите другое время."
        )
        return
    
    context.user_data['selected_time'] = selected_time
    context.user_data['waiting_for_contact'] = True
    
    # Остальная логика без изменений...
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM services WHERE id = ?', (context.user_data['service_id'],))
    service_name = cursor.fetchone()[0]
    cursor.execute('SELECT name FROM masters WHERE id = ?', (context.user_data['master_id'],))
    master_name = cursor.fetchone()[0]
    conn.close()
    
    formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
    await query.edit_message_text(
        f"📋 **Детали записи:**\n\n"
        f"💅 Услуга: {service_name}\n"
        f"👨‍💼 Мастер: {master_name}\n"
        f"📅 Дата: {formatted_date}\n\n"
        f"📝 <b>Введите ваше имя и телефон:</b>\n"
        f"<code>Имя Телефон</code>\n\n"
        f"<b>Пример:</b>\n"
        f"<code>Анна +79123456789</code>\n\n"
        f"⚠️ <b>Требования к имени:</b>\n"
        f"• Только буквы (без цифр)\n"
        f"• Минимум 2 символа, максимум 30\n"
        f"• Одно слово\n\n"
        f"⚠️ <b>Требования к телефону:</b>\n"
        f"• Минимум 10 цифр, максимум 15\n"
        f"• Должен начинаться с +7, 7, 8 или кода страны\n\n"
        f"📞 <b>Правильные форматы:</b>\n"
        f"+79123456789 (11 цифр)\n"
        f"89123456789 (11 цифр)\n"
        f"9123456789 (10 цифр)",
        parse_mode='HTML'
    )
async def handle_back_to_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик возврата к календарю"""
    query = update.callback_query
    await query.answer()
    
    # 🔧 ВОССТАНАВЛИВАЕМ КОНТЕКСТ ДЛЯ ВОЗВРАТА К КАЛЕНДАРЮ
    service_id = context.user_data.get('service_id')
    master_id = context.user_data.get('master_id')
    
    if not service_id or not master_id:
        # Если нет контекста, возвращаем к началу записи
        await book_service_callback(update, context)
        return
    
    # Возвращаемся к календарю с текущей неделей
    await show_calendar(update, context, week_offset=0)
async def handle_contact_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода имени и телефона с инлайн-кнопками"""
    if not context.user_data.get('waiting_for_contact'):
        return
    
    try:
        text = update.message.text.strip()
        user = update.message.from_user
        
        print(f"🔍 Обработка контакта от пользователя {user.id}: {text}")
        
        # 🔍 РАЗБИРАЕМ ВВОД
        parts = text.split()
        
        # Минимально должно быть 2 части: имя и телефон
        if len(parts) < 2:
            await update.message.reply_text(
                "❌ **Неверный формат ввода!**\n\n"
                "Пожалуйста, введите ИМЯ и ТЕЛЕФОН через пробел:\n"
                "Например: Анна +79123456789"
            )
            return
        
        client_name = parts[0]
        client_phone = ' '.join(parts[1:])
        
        # 🔒 ПРОВЕРКА ИМЕНИ
        if any(char.isdigit() for char in client_name):
            await update.message.reply_text(
                "❌ **Неверное имя!**\n\n"
                "Имя не должно содержать цифр.\n"
                "Пожалуйста, введите ваше имя и телефон еще раз:\n"
                "Например: Анна +79123456789"
            )
            return
        
        if len(client_name) < 2:
            await update.message.reply_text(
                "❌ **Неверное имя!**\n\n"
                "Имя должно содержать минимум 2 символа.\n"
                "Пожалуйста, введите ваше имя и телефон еще раз:\n"
                "Например: Анна +79123456789"
            )
            return
        
        if len(client_name) > 30:
            await update.message.reply_text(
                "❌ **Слишком длинное имя!**\n\n"
                "Имя должно быть не длиннее 30 символов.\n"
                "Пожалуйста, введите ваше имя и телефон еще раз:\n"
                "Например: Анна +79123456789"
            )
            return
        
        # 🔒 ПРОВЕРКА НОМЕРА ТЕЛЕФОНА
        cleaned_phone = ''.join(c for c in client_phone if c.isdigit() or c == '+')
        digits_only = ''.join(c for c in cleaned_phone if c.isdigit())
        
        if len(digits_only) < 10:
            await update.message.reply_text(
                "❌ **Неверный формат номера телефона!**\n\n"
                f"Введенный номер: {client_phone}\n"
                f"Найдено цифр: {len(digits_only)} (требуется минимум 10)\n\n"
                "Пожалуйста, введите ваше имя и телефон еще раз:\n"
                "Например: Анна +79123456789"
            )
            return
        
        if len(digits_only) > 15:
            await update.message.reply_text(
                "❌ **Слишком длинный номер телефона!**\n\n"
                f"Введенный номер: {client_phone}\n"
                f"Найдено цифр: {len(digits_only)} (максимум 15)\n\n"
                "Пожалуйста, введите корректный номер телефона:\n"
                "Например: Анna +79123456789"
            )
            return
        
        if not (cleaned_phone.startswith('+7') or 
                cleaned_phone.startswith('7') or 
                cleaned_phone.startswith('8') or 
                (cleaned_phone.startswith('+') and len(cleaned_phone) > 2) or
                (cleaned_phone[0].isdigit() if cleaned_phone else False)):
            await update.message.reply_text(
                "❌ **Неверный формат номера!**\n\n"
                f"Введенный номер: {client_phone}\n\n"
                "Номер должен начинаться с:\n"
                "• +7 (международный формат)\n"
                "• 7 или 8 (российский формат)\n"
                "• или код другой страны (+375, +44 и т.д.)\n\n"
                "Пожалуйста, введите корректный номер:"
            )
            return
        
        # Используем очищенный номер
        client_phone = cleaned_phone
        
        # 🔧 СОХРАНЯЕМ КОНТАКТНЫЕ ДАННЫЕ В КОНТЕКСТ
        context.user_data['client_name'] = client_name
        context.user_data['client_phone'] = client_phone
        
        # 🔧 ПЕРЕХОДИМ К ВЫБОРУ ВРЕМЕНИ НАПОМИНАНИЯ
        context.user_data['waiting_for_contact'] = False
        context.user_data['waiting_for_reminder_choice'] = True
        
        print(f"✅ Контактные данные сохранены, переходим к выбору напоминания")
        
        # 🔧 СОЗДАЕМ КЛАВИАТУРУ ДЛЯ ВЫБОРА НАПОМИНАНИЯ
        keyboard = [
            [InlineKeyboardButton("🔔 За 24 часа до записи", callback_data="reminder_24")],
            [InlineKeyboardButton("⏰ За 1 час до записи", callback_data="reminder_1")],
            [InlineKeyboardButton("🔙 Назад к выбору времени", callback_data="back_to_time_selection")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⏰ **Выберите время напоминания:**\n\n"
            "Когда вам напомнить о записи?\n\n"
            "🔔 <b>За 24 часа</b> - получите напоминание за сутки\n"
            "⏰ <b>За 1 час</b> - получите напоминание за час до записи\n\n"
            "💡 <i>Напоминание поможет не забыть о визите!</i>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        await update.message.reply_text("❌ Ошибка при обработке данных. Попробуйте еще раз.")
        logger.error(f"Error in handle_contact_input: {e}")
        print(f"❌ Детали ошибки: {e}")
async def get_my_salon_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, unique_token FROM salons WHERE is_active = 1')
    salons = cursor.fetchall()
    conn.close()
    
    links_text = "🔗 Уникальные ссылки салонов:\n\n"
    for salon in salons:
        salon_link = generate_salon_link(salon[2])
        links_text += f"🏪 {salon[1]}\n🔗 `{salon_link}`\n\n"
    
    await update.message.reply_text(links_text)
async def check_db_structure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет структуру базы данных"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Проверяем структуру таблицы bot_users
        cursor.execute("PRAGMA table_info(bot_users)")
        columns = cursor.fetchall()
        
        response = "📋 Структура таблицы bot_users:\n"
        for col in columns:
            response += f"• {col[1]} ({col[2]}) - default: {col[4]}\n"
        
        # Проверяем данные пользователя
        user = update.message.from_user
        cursor.execute('SELECT * FROM bot_users WHERE telegram_user_id = ?', (user.id,))
        user_data = cursor.fetchone()
        
        if user_data:
            response += f"\n📊 Данные пользователя {user.id}:\n"
            response += f"• ID: {user_data[0]}\n"
            response += f"• Telegram ID: {user_data[1]}\n"
            response += f"• Username: {user_data[2]}\n"
            response += f"• Имя: {user_data[3]}\n"
            response += f"• Капча: {user_data[5]} (тип: {type(user_data[5])})\n"
            response += f"• Регистрация: {user_data[4]}\n"
        else:
            response += f"\n❌ Пользователь {user.id} не найден в базе"
        
        conn.close()
        await update.message.reply_text(response)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
async def send_booking_reminder(booking_id):
    """Отправляет напоминание о записи клиенту ВСЕГДА с кнопкой подтверждения"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Проверяем, нужно ли отправлять напоминание салону
        cursor.execute('SELECT send_to_salon FROM booking_reminders WHERE booking_id = ?', (booking_id,))
        reminder_info = cursor.fetchone()
        
        send_to_salon = True
        if reminder_info:
            send_to_salon = bool(reminder_info[0])
        
        # Получаем информацию о записи
        cursor.execute('''
            SELECT b.client_name, b.client_phone, b.booking_date, 
                   s.name as service_name, m.name as master_name,
                   sl.name as salon_name, sl.telegram_chat_id,
                   b.id, b.salon_id, b.user_id, b.confirmed
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            JOIN salons sl ON b.salon_id = sl.id
            WHERE b.id = ?
        ''', (booking_id,))
        
        booking = cursor.fetchone()
        
        if not booking:
            print(f"❌ Запись {booking_id} не найдена")
            return False
        
        client_name, client_phone, booking_date, service_name, master_name, salon_name, salon_chat_id, booking_id, salon_id, user_id, confirmed = booking
        
        # 🔧 ОБРАБАТЫВАЕМ ДАТУ И ВЫЧИСЛЯЕМ ВРЕМЯ ДО ЗАПИСИ
        try:
            if isinstance(booking_date, str):
                booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
            else:
                booking_datetime = booking_date
            
            formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
            
            # 🔧 ВЫЧИСЛЯЕМ СКОЛЬКО ЧАСОВ ОСТАЛОСЬ ДО ЗАПИСИ
            current_time = datetime.now()
            time_difference = booking_datetime - current_time
            hours_until = time_difference.total_seconds() / 3600  # часов до записи
            
            # 🔧 ФОРМИРУЕМ ТЕКСТ В ЗАВИСИМОСТИ ОТ ВРЕМЕНИ
            if hours_until < 1:
                time_text = "менее чем через 1 час"
            elif hours_until < 2:
                time_text = f"через {int(hours_until)} час"
            elif hours_until < 5:
                time_text = f"через {int(hours_until)} часа"
            else:
                time_text = f"через {int(hours_until)} часов"
                
        except Exception as e:
            print(f"❌ Ошибка обработки даты: {e}")
            formatted_date = "дата не определена"
            time_text = "скоро"
        
        # 🔧 СООБЩЕНИЕ ДЛЯ КЛИЕНТА ВСЕГДА С КНОПКОЙ (если не подтверждено)
        if confirmed:
            # Если уже подтверждено
            client_reminder_text = (
                f"🔔 **НАПОМИНАНИЕ О ЗАПИСИ**\n\n"
                f"У вас запись {time_text}:\n\n"
                f"🏪 Салон: {salon_name}\n"
                f"💅 Услуга: {service_name}\n"
                f"👨‍💼 Мастер: {master_name}\n"
                f"📅 Время: {formatted_date}\n\n"
                f"✅ <b>Запись подтверждена</b>\n\n"
                f"📍 Не забудьте о визите!\n"
                f"⏰ Пожалуйста, приходите вовремя."
            )
            keyboard = []
        else:
            # 🔧 ВСЕГДА ПОКАЗЫВАЕМ КНОПКУ ПОДТВЕРЖДЕНИЯ
            client_reminder_text = (
                f"🔔 **НАПОМИНАНИЕ О ЗАПИСИ**\n\n"
                f"У вас запись {time_text}:\n\n"
                f"🏪 Салон: {salon_name}\n"
                f"💅 Услуга: {service_name}\n"
                f"👨‍💼 Мастер: {master_name}\n"
                f"📅 Время: {formatted_date}\n\n"
                f"⏳ <b>Запись ожидает подтверждения</b>\n\n"
                f"📍 Пожалуйста, подтвердите, что придете:\n"
                f"⏰ Это поможет салону подготовиться к вашему визиту"
            )
            # 🔧 КНОПКА ПОДТВЕРЖДЕНИЯ ВСЕГДА
            keyboard = [
                [InlineKeyboardButton("✅ Подтвердить запись", callback_data=f"confirm_booking_{booking_id}")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        # 🔧 СООБЩЕНИЕ ДЛЯ САЛОНА
        status_text = "✅ ПОДТВЕРЖДЕНА" if confirmed else "⏳ ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ"
        salon_reminder_text = (
            f"🔔 **НАПОМИНАНИЕ О ЗАПИСИ**\n\n"
            f"Запись {time_text}:\n\n"
            f"👤 Клиент: {client_name}\n"
            f"📞 Телефон: {client_phone}\n"
            f"💅 Услуга: {service_name}\n"
            f"👨‍💼 Мастер: {master_name}\n"
            f"📅 Время: {formatted_date}\n\n"
            f"📊 Статус: {status_text}\n"
            f"🆔 ID записи: {booking_id}"
        )
        
        # Отправляем напоминание через бота
        app = Application.builder().token(BOT_TOKEN).build()
        await app.initialize()
        
        success_count = 0
        
        # 🔧 ОТПРАВЛЯЕМ КЛИЕНТУ (ВСЕГДА)
        if user_id:
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text=client_reminder_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                print(f"✅ Напоминание с кнопкой отправлено клиенту {client_name} ({time_text})")
                success_count += 1
            except Exception as e:
                print(f"❌ Не удалось отправить напоминание клиенту: {e}")
        
        # 🔧 ОТПРАВЛЯЕМ В САЛОН (ТОЛЬКО ЕСЛИ РАЗРЕШЕНО)
        if send_to_salon and salon_chat_id:
            try:
                await app.bot.send_message(
                    chat_id=salon_chat_id,
                    text=salon_reminder_text
                )
                print(f"✅ Напоминание отправлено салону {salon_name} ({time_text})")
                success_count += 1
            except Exception as e:
                print(f"❌ Не удалось отправить напоминание салону: {e}")
        elif not send_to_salon:
            print(f"🔕 Напоминание салону отключено для записи {booking_id}")
        
        await app.shutdown()
        
        # Отмечаем напоминание как отправленное
        if success_count > 0:
            cursor.execute('''
                UPDATE booking_reminders 
                SET reminder_sent = 1 
                WHERE booking_id = ?
            ''', (booking_id,))
            conn.commit()
            print(f"✅ Напоминание для записи {booking_id} обработано")
        
        conn.close()
        return success_count > 0
        
    except Exception as e:
        print(f"❌ Ошибка при отправке напоминания: {e}")
        return False
async def check_booking_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Фоновая задача: проверяет и отправляет напоминания"""
    try:
        current_time = datetime.now()
        current_time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Ищем напоминания, которые нужно отправить (время наступило, но еще не отправлены)
        cursor.execute('''
            SELECT br.id, br.booking_id
            FROM booking_reminders br
            WHERE br.reminder_sent = 0 
            AND br.reminder_time <= ?
        ''', (current_time_str,))
        
        reminders_to_send = cursor.fetchall()
        conn.close()
        
        for reminder_id, booking_id in reminders_to_send:
            print(f"🔔 Отправка напоминания для записи {booking_id}")
            success = await send_booking_reminder(booking_id)
            
            if success:
                print(f"✅ Напоминание для записи {booking_id} отправлено")
            else:
                print(f"❌ Не удалось отправить напоминание для записи {booking_id}")
                
    except Exception as e:
        print(f"❌ Ошибка в фоновой задаче напоминаний: {e}")
async def check_booking_structure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет структуру таблицы bookings"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Проверяем структуру таблицы
        cursor.execute("PRAGMA table_info(bookings)")
        columns = cursor.fetchall()
        
        response = "📋 Структура таблицы bookings:\n"
        for col in columns:
            response += f"• {col[1]} ({col[2]})\n"
        
        # Проверяем несколько записей
        cursor.execute('SELECT id, booking_date, typeof(booking_date) FROM bookings LIMIT 3')
        sample_data = cursor.fetchall()
        
        response += "\n📊 Пример данных:\n"
        for row in sample_data:
            response += f"• ID {row[0]}: {row[1]} (тип: {row[2]})\n"
        
        conn.close()
        await update.message.reply_text(response)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
async def start_reminder_scheduler(application: Application):
    """Запускает планировщик напоминаний"""
    # Проверяем каждые 60 секунд
    application.job_queue.run_repeating(
        check_booking_reminders,
        interval=60,  # 60 секунд
        first=10      # Первый запуск через 10 секунд после старта
    )
    print("✅ Планировщик напоминаний запущен")
async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает активные записи клиента"""
    try:
        if hasattr(update, 'callback_query') and update.callback_query:
            user = update.callback_query.from_user
            context.user_data['current_query'] = update.callback_query
        elif hasattr(update, 'message') and update.message:
            user = update.message.from_user
        else:
            user = update.effective_user
        
        print(f"🔍 Просмотр активных записей для пользователя {user.id}")
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # 🔧 ТОЛЬКО АКТИВНЫЕ ЗАПИСИ (будущие и не завершенные)
        cursor.execute('''
            SELECT b.id, b.booking_date, s.name as service_name, 
                   m.name as master_name, sl.name as salon_name, 
                   b.status, b.client_name, b.confirmed, b.completed
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            JOIN salons sl ON b.salon_id = sl.id
            WHERE b.user_id = ? AND b.status = 'confirmed'
            AND b.booking_date > datetime('now')
            ORDER BY b.booking_date ASC
        ''', (user.id,))
        
        bookings = cursor.fetchall()
        conn.close()
        
        if not bookings:
            message_text = (
                "📋 **Ваши активные записи**\n\n"
                "У вас пока нет активных записей.\n\n"
                "💡 Чтобы записаться, используйте меню записи"
            )
            
            keyboard = [
                [InlineKeyboardButton("💅 Записаться", callback_data="book_service_main")],
                [InlineKeyboardButton("📚 История записей", callback_data="client_booking_history")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu_return")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(message_text, reply_markup=reply_markup)
            return
        
        # Сохраняем записи в контексте для постраничного просмотра
        context.user_data['user_bookings'] = bookings
        context.user_data['current_booking_page'] = 0
        
        # Показываем первую запись
        await show_booking_page(update, context, 0)
        
    except Exception as e:
        print(f"❌ Ошибка в my_bookings: {e}")
        error_text = "❌ Ошибка при загрузке записей. Попробуйте позже."
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="client_main_menu")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu_return")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(error_text, reply_markup=reply_markup)
        elif hasattr(update, 'message') and update.message:
            await update.message.reply_text(error_text, reply_markup=reply_markup)
async def show_booking_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page_number):
    """Показывает одну запись на странице с кнопками навигации"""
    bookings = context.user_data.get('user_bookings', [])
    
    if not bookings:
        # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ НАЗАД
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="client_main_menu")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu_return")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Определяем тип обновления
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text("❌ Записи не найдены", reply_markup=reply_markup)
        else:
            await update.message.reply_text("❌ Записи не найдены", reply_markup=reply_markup)
        return
    
    # Проверяем валидность номера страницы
    if page_number < 0:
        page_number = 0
    if page_number >= len(bookings):
        page_number = len(bookings) - 1
    
    # Сохраняем текущую страницу в контексте
    context.user_data['current_booking_page'] = page_number
    
    # Получаем запись для текущей страницы
    booking = bookings[page_number]
    booking_id, booking_date, service_name, master_name, salon_name, status, client_name, confirmed = booking
    
    # 🔧 ОБРАБАТЫВАЕМ ДАТУ
    try:
        if isinstance(booking_date, str):
            booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
        else:
            booking_datetime = booking_date
        
        formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
        time_until = (booking_datetime - datetime.now()).total_seconds() / 3600  # часов до записи
        
    except Exception as e:
        formatted_date = "дата не определена"
        time_until = 999
    
    # Формируем текст записи
    status_icon = "✅" if confirmed else "⏳"
    status_text = "Подтверждена" if confirmed else "Ожидает подтверждения"
    
    booking_text = (
        f"📋 **Ваша запись**\n\n"
        f"{status_icon} **Запись #{booking_id}**\n"
        f"🏪 Салон: {salon_name}\n"
        f"💅 Услуга: {service_name}\n"
        f"👨‍💼 Мастер: {master_name}\n"
        f"📅 Дата: {formatted_date}\n"
        f"📊 Статус: {status_text}\n"
        f"📄 Страница: {page_number + 1} из {len(bookings)}\n"
    )
    
    # 🔧 ПРЕДУПРЕЖДЕНИЕ О ПОЗДНЕЙ ОТМЕНЕ
    if time_until < 2:
        booking_text += f"\n⚠️ <b>Внимание!</b> Поздняя отмена (менее 2 часов до записи)\n"
    
    # Создаем клавиатуру
    keyboard = []
    
    # Кнопка удаления записи
    keyboard.append([InlineKeyboardButton("🗑️ Удалить запись", callback_data=f"delete_{booking_id}")])
    
    # Кнопки навигации
    nav_buttons = []
    
    if page_number > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"prev_{page_number-1}"))
    
    if page_number < len(bookings) - 1:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"next_{page_number+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # 🔧 ДОБАВЛЯЕМ КНОПКИ ОБНОВЛЕНИЯ И НАЗАД
    keyboard.append([InlineKeyboardButton("🔄 Обновить список", callback_data="refresh_bookings")])
    keyboard.append([InlineKeyboardButton("🔙 Назад в меню", callback_data="client_main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # 🔧 ОПРЕДЕЛЯЕМ ТИП ОТПРАВКИ СООБЩЕНИЯ
    if hasattr(update, 'callback_query') and update.callback_query:
        # Это callback query - редактируем существующее сообщение
        await update.callback_query.edit_message_text(
            booking_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    elif hasattr(update, 'message') and update.message:
        # Это обычное сообщение - отправляем новое
        await update.message.reply_text(
            booking_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    else:
        # Для других случаев используем application
        if hasattr(update, 'effective_chat'):
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=booking_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
async def handle_confirm_delete_from_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтвержденное удаление записи из просмотра"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Правильно парсим booking_id из callback данных
        data_parts = query.data.split('_')
        booking_id = int(data_parts[-1])  # Берем последнюю часть как ID
        
        user_id = query.from_user.id
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Получаем информацию о записи перед удалением
        cursor.execute('''
            SELECT b.booking_date, s.name, m.name, sl.name, b.client_name, 
                   sl.telegram_chat_id, b.client_phone
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            JOIN salons sl ON b.salon_id = sl.id
            WHERE b.id = ? AND b.user_id = ?
        ''', (booking_id, user_id))
        
        booking_info = cursor.fetchone()
        
        if not booking_info:
            await query.edit_message_text("❌ Запись не найдена")
            conn.close()
            return
        
        booking_date, service_name, master_name, salon_name, client_name, salon_chat_id, client_phone = booking_info
        
        # Отменяем запись
        cursor.execute('UPDATE bookings SET status = "cancelled" WHERE id = ?', (booking_id,))
        
        # Удаляем связанные напоминания
        cursor.execute('DELETE FROM booking_reminders WHERE booking_id = ?', (booking_id,))
        
        conn.commit()
        conn.close()
        
        # 🔧 ФОРМАТИРУЕМ ДАТУ ДЛЯ СООБЩЕНИЯ
        try:
            if isinstance(booking_date, str):
                booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
            else:
                booking_datetime = booking_date
            
            formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
        except:
            formatted_date = "дата не определена"
        
        # 🔔 УВЕДОМЛЯЕМ САЛОН ОБ ОТМЕНЕ
        await send_cancellation_notification(booking_id, client_name, client_phone, service_name, master_name, formatted_date, salon_chat_id)
        
        # Обновляем список записей в контексте
        if 'user_bookings' in context.user_data:
            # Удаляем отмененную запись из списка
            context.user_data['user_bookings'] = [
                booking for booking in context.user_data['user_bookings'] 
                if booking[0] != booking_id
            ]
        
        # Показываем обновленный список или сообщение об отсутствии записей
        bookings = context.user_data.get('user_bookings', [])
        
        if bookings:
            current_page = context.user_data.get('current_booking_page', 0)
            # Корректируем номер страницы если нужно
            if current_page >= len(bookings):
                current_page = len(bookings) - 1
            if current_page < 0:
                current_page = 0
            
            context.user_data['current_booking_page'] = current_page
            await show_booking_page(update, context, current_page)
        else:
            await query.edit_message_text(
                "✅ **Запись успешно удалена!**\n\n"
                "💫 У вас больше нет активных записей.\n\n"
                "📋 Чтобы записаться снова, используйте: /book"
            )
        
    except Exception as e:
        await query.edit_message_text("❌ Ошибка при удалении записи")
        logger.error(f"Error deleting booking from page: {e}")
async def handle_delete_booking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик удаления записи из просмотра"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Правильно парсим booking_id из callback данных
        data = query.data
        if data.startswith('delete_'):
            booking_id = int(data.split('_')[1])
        else:
            await query.edit_message_text("❌ Ошибка в формате запроса")
            return
        
        user_id = query.from_user.id
        
        # Получаем информацию о записи
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT b.booking_date, s.name, m.name, sl.name, b.client_name, b.status
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            JOIN salons sl ON b.salon_id = sl.id
            WHERE b.id = ? AND b.user_id = ?
        ''', (booking_id, user_id))
        
        booking = cursor.fetchone()
        conn.close()
        
        if not booking:
            await query.edit_message_text("❌ Запись не найдена или у вас нет прав для ее удаления")
            return
        
        booking_date, service_name, master_name, salon_name, client_name, status = booking
        
        if status == 'cancelled':
            await query.edit_message_text("❌ Эта запись уже отменена")
            return
        
        # 🔧 ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ
        try:
            if isinstance(booking_date, str):
                booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
            else:
                booking_datetime = booking_date
            
            formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
            time_until = (booking_datetime - datetime.now()).total_seconds() / 3600
            
        except Exception as e:
            formatted_date = "дата не определена"
            time_until = 999
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_{booking_id}"),
                InlineKeyboardButton("❌ Нет, оставить", callback_data="cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        warning_text = ""
        if time_until < 2:
            warning_text = "\n\n⚠️ <b>Внимание!</b> Поздняя отмена (менее 2 часов до записи)."
        
        await query.edit_message_text(
            f"❓ **Подтверждение удаления**\n\n"
            f"Вы действительно хотите удалить запись?\n\n"
            f"🆔 Запись #{booking_id}\n"
            f"🏪 Салон: {salon_name}\n"
            f"💅 Услуга: {service_name}\n"
            f"👨‍💼 Мастер: {master_name}\n"
            f"📅 Дата: {formatted_date}\n"
            f"{warning_text}",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        await query.edit_message_text("❌ Ошибка при обработке запроса")
        logger.error(f"Error in handle_delete_booking_callback: {e}")
async def handle_booking_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик навигации по записям"""
    query = update.callback_query
    
    try:
        # Сначала отвечаем на callback, чтобы убрать "часики"
        await query.answer()
        
        data = query.data
        print(f"🔍 Navigation callback data: {data}")  # Для отладки
        
        # Парсим номер страницы
        if data.startswith('prev_'):
            parts = data.split('_')
            if len(parts) >= 2:
                page_number = int(parts[1])
            else:
                await query.edit_message_text("❌ Ошибка: неверный формат команды 'назад'")
                return
                
        elif data.startswith('next_'):
            parts = data.split('_')
            if len(parts) >= 2:
                page_number = int(parts[1])
            else:
                await query.edit_message_text("❌ Ошибка: неверный формат команды 'вперед'")
                return
        else:
            await query.edit_message_text("❌ Неизвестная команда навигации")
            return
        
        # Проверяем, есть ли записи в контексте
        if 'user_bookings' not in context.user_data:
            # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ НАЗАД ДЛЯ ОШИБКИ
            keyboard = [
                [InlineKeyboardButton("🔙 Назад в меню", callback_data="client_main_menu")],
                [InlineKeyboardButton("📋 Мои записи", callback_data="my_bookings_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "❌ Данные записей устарели. Используйте кнопку ниже для обновления",
                reply_markup=reply_markup
            )
            return
        
        bookings = context.user_data['user_bookings']
        
        # Проверяем валидность номера страницы
        if page_number < 0:
            page_number = 0
        if page_number >= len(bookings):
            page_number = len(bookings) - 1
        
        print(f"🔍 Navigating to page {page_number}, total pages: {len(bookings)}")  # Для отладки
        
        await show_booking_page(update, context, page_number)
        
    except ValueError as e:
        # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ НАЗАД ДЛЯ ОШИБКИ
        keyboard = [
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="client_main_menu")],
            [InlineKeyboardButton("📋 Мои записи", callback_data="my_bookings_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text("❌ Ошибка: неверный номер страницы", reply_markup=reply_markup)
        logger.error(f"ValueError in handle_booking_navigation: {e}")
    except IndexError as e:
        # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ НАЗАД ДЛЯ ОШИБКИ
        keyboard = [
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="client_main_menu")],
            [InlineKeyboardButton("📋 Мои записи", callback_data="my_bookings_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text("❌ Ошибка: неверный формат команды навигации", reply_markup=reply_markup)
        logger.error(f"IndexError in handle_booking_navigation: {e}")
    except Exception as e:
        # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ НАЗАД ДЛЯ ОШИБКИ
        keyboard = [
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="client_main_menu")],
            [InlineKeyboardButton("📋 Мои записи", callback_data="my_bookings_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text("❌ Ошибка при навигации", reply_markup=reply_markup)
        logger.error(f"Error in handle_booking_navigation: {e}")
async def handle_confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтвержденное удаление записи из просмотра (НОВОЕ ИМЯ)"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Правильно парсим booking_id из callback данных
        data = query.data
        if data.startswith('confirm_'):
            booking_id = int(data.split('_')[1])
        else:
            await query.edit_message_text("❌ Ошибка в формате запроса")
            return
        
        user_id = query.from_user.id
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Получаем информацию о записи перед удалением
        cursor.execute('''
            SELECT b.booking_date, s.name, m.name, sl.name, b.client_name, 
                   sl.telegram_chat_id, b.client_phone
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            JOIN salons sl ON b.salon_id = sl.id
            WHERE b.id = ? AND b.user_id = ?
        ''', (booking_id, user_id))
        
        booking_info = cursor.fetchone()
        
        if not booking_info:
            await query.edit_message_text("❌ Запись не найдена")
            conn.close()
            return
        
        booking_date, service_name, master_name, salon_name, client_name, salon_chat_id, client_phone = booking_info
        
        # Отменяем запись
        cursor.execute('UPDATE bookings SET status = "cancelled" WHERE id = ?', (booking_id,))
        
        # Удаляем связанные напоминания
        cursor.execute('DELETE FROM booking_reminders WHERE booking_id = ?', (booking_id,))
        
        conn.commit()
        conn.close()
        
        # 🔧 ФОРМАТИРУЕМ ДАТУ ДЛЯ СООБЩЕНИЯ
        try:
            if isinstance(booking_date, str):
                booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
            else:
                booking_datetime = booking_date
            
            formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
        except:
            formatted_date = "дата не определена"
        
        # 🔔 УВЕДОМЛЯЕМ САЛОН ОБ ОТМЕНЕ
        await send_cancellation_notification(booking_id, client_name, client_phone, service_name, master_name, formatted_date, salon_chat_id)
        
        # Обновляем список записей в контексте
        if 'user_bookings' in context.user_data:
            # Удаляем отмененную запись из списка
            context.user_data['user_bookings'] = [
                booking for booking in context.user_data['user_bookings'] 
                if booking[0] != booking_id
            ]
        
        # Показываем обновленный список или сообщение об отсутствии записей
        bookings = context.user_data.get('user_bookings', [])
        
        if bookings:
            current_page = context.user_data.get('current_booking_page', 0)
            # Корректируем номер страницы если нужно
            if current_page >= len(bookings):
                current_page = len(bookings) - 1
            if current_page < 0:
                current_page = 0
            
            context.user_data['current_booking_page'] = current_page
            await show_booking_page(update, context, current_page)
        else:
            await query.edit_message_text(
                "✅ **Запись успешно удалена!**\n\n"
                "💫 У вас больше нет активных записей.\n\n"
                "📋 Чтобы записаться снова, используйте: /book"
            )
        
    except Exception as e:
        await query.edit_message_text("❌ Ошибка при удалении записи")
        logger.error(f"Error deleting booking: {e}")
async def handle_cancel_deletion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена удаления записи (НОВОЕ ИМЯ)"""
    query = update.callback_query
    await query.answer()
    
    current_page = context.user_data.get('current_booking_page', 0)
    await show_booking_page(update, context, current_page)
async def handle_refresh_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обновление списка записей"""
    query = update.callback_query
    
    try:
        await query.answer("🔄 Обновляем список...")
        
        # Загружаем актуальные данные из базы
        user = query.from_user
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT b.id, b.booking_date, s.name as service_name, 
                   m.name as master_name, sl.name as salon_name, 
                   b.status, b.client_name, b.confirmed
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            JOIN salons sl ON b.salon_id = sl.id
            WHERE b.user_id = ? AND b.status = 'confirmed'
            AND b.booking_date > datetime('now')
            ORDER BY b.booking_date ASC
        ''', (user.id,))
        
        bookings = cursor.fetchall()
        conn.close()
        
        if not bookings:
            await query.edit_message_text(
                "📋 **Ваши активные записи**\n\n"
                "У вас пока нет активных записей.\n\n"
                "💡 Чтобы записаться, используйте команду /book"
            )
            return
        
        # Обновляем данные в контексте
        context.user_data['user_bookings'] = bookings
        context.user_data['current_booking_page'] = 0
        
        await show_booking_page(update, context, 0)
        
    except Exception as e:
        await query.edit_message_text("❌ Ошибка при обновлении списка")
        logger.error(f"Error in handle_refresh_bookings: {e}")

    """Обновление списка записей"""
    query = update.callback_query
    await query.answer()
    
    # Загружаем актуальные данные из базы
    user = query.from_user
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT b.id, b.booking_date, s.name as service_name, 
               m.name as master_name, sl.name as salon_name, 
               b.status, b.client_name, b.confirmed
        FROM bookings b
        JOIN services s ON b.service_id = s.id
        JOIN masters m ON b.master_id = m.id
        JOIN salons sl ON b.salon_id = sl.id
        WHERE b.user_id = ? AND b.status = 'confirmed'
        AND b.booking_date > datetime('now')
        ORDER BY b.booking_date ASC
    ''', (user.id,))
    
    bookings = cursor.fetchall()
    conn.close()
    
    if not bookings:
        await query.edit_message_text(
            "📋 **Ваши активные записи**\n\n"
            "У вас пока нет активных записей.\n\n"
            "💡 Чтобы записаться, используйте команду /book"
        )
        return
    
    # Обновляем данные в контексте
    context.user_data['user_bookings'] = bookings
    context.user_data['current_booking_page'] = 0
    
    await show_booking_page(update, context, 0)
async def handle_cancel_deletion_from_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена удаления записи"""
    query = update.callback_query
    await query.answer()
    
    current_page = context.user_data.get('current_booking_page', 0)
    await show_booking_page(update, context, current_page)
    """Обработчик навигации по записям"""
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split('_')
    action = data_parts[1]  # prev или next
    page_number = int(data_parts[2])
    
    await show_booking_page(update, context, page_number)
    """Обработчик удаления записи из просмотра"""
    query = update.callback_query
    await query.answer()
    
    booking_id = int(query.data.split('_')[2])
    user_id = query.from_user.id
    
    # Получаем информацию о записи
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT b.booking_date, s.name, m.name, sl.name, b.client_name, b.status
        FROM bookings b
        JOIN services s ON b.service_id = s.id
        JOIN masters m ON b.master_id = m.id
        JOIN salons sl ON b.salon_id = sl.id
        WHERE b.id = ? AND b.user_id = ?
    ''', (booking_id, user_id))
    
    booking = cursor.fetchone()
    conn.close()
    
    if not booking:
        await query.edit_message_text("❌ Запись не найдена или у вас нет прав для ее удаления")
        return
    
    booking_date, service_name, master_name, salon_name, client_name, status = booking
    
    if status == 'cancelled':
        await query.edit_message_text("❌ Эта запись уже отменена")
        return
    
    # 🔧 ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ
    try:
        if isinstance(booking_date, str):
            booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
        else:
            booking_datetime = booking_date
        
        formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
        time_until = (booking_datetime - datetime.now()).total_seconds() / 3600
        
    except Exception as e:
        formatted_date = "дата не определена"
        time_until = 999
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_from_page_{booking_id}"),
            InlineKeyboardButton("❌ Нет, оставить", callback_data="cancel_deletion_from_page")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    warning_text = ""
    if time_until < 2:
        warning_text = "\n\n⚠️ <b>Внимание!</b> Поздняя отмена (менее 2 часов до записи)."
    
    await query.edit_message_text(
        f"❓ **Подтверждение удаления**\n\n"
        f"Вы действительно хотите удалить запись?\n\n"
        f"🆔 Запись #{booking_id}\n"
        f"🏪 Салон: {salon_name}\n"
        f"💅 Услуга: {service_name}\n"
        f"👨‍💼 Мастер: {master_name}\n"
        f"📅 Дата: {formatted_date}\n"
        f"{warning_text}",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

    """Отмена удаления записи"""
    query = update.callback_query
    await query.answer()
    
    current_page = context.user_data.get('current_booking_page', 0)
    await show_booking_page(update, context, current_page)
async def send_cancellation_notification(booking_id, client_name):
    """Уведомляет салон об отмене записи"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT b.booking_date, s.name as service_name, m.name as master_name,
                   sl.name as salon_name, sl.telegram_chat_id
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            JOIN salons sl ON b.salon_id = sl.id
            WHERE b.id = ?
        ''', (booking_id,))
        
        booking = cursor.fetchone()
        conn.close()
        
        if booking and booking[4]:  # telegram_chat_id
            booking_date, service_name, master_name, salon_name, salon_chat_id = booking
            formatted_date = booking_date.strftime('%d.%m.%Y в %H:%M')
            
            notification_text = (
                f"🚫 **ОТМЕНА ЗАПИСИ**\n\n"
                f"Клиент отменил запись:\n\n"
                f"👤 Клиент: {client_name}\n"
                f"💅 Услуга: {service_name}\n"
                f"👨‍💼 Мастер: {master_name}\n"
                f"📅 Дата: {formatted_date}\n\n"
                f"🆔 ID записи: {booking_id}"
            )
            
            app = Application.builder().token(BOT_TOKEN).build()
            await app.initialize()
            await app.bot.send_message(chat_id=salon_chat_id, text=notification_text)
            await app.shutdown()
            
    except Exception as e:
        print(f"❌ Ошибка при отправке уведомления об отмене: {e}")
async def fix_booking_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Исправляет формат дат в существующих записях"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Получаем все записи
        cursor.execute('SELECT id, booking_date FROM bookings')
        bookings = cursor.fetchall()
        
        fixed_count = 0
        for booking_id, booking_date in bookings:
            try:
                # Если дата уже в правильном формате, пропускаем
                if isinstance(booking_date, str) and ':' in booking_date:
                    continue
                    
                # Преобразуем в правильный формат
                if isinstance(booking_date, str):
                    # Пробуем разные форматы
                    try:
                        dt = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        try:
                            dt = datetime.strptime(booking_date, '%Y-%m-%d %H:%M')
                        except ValueError:
                            print(f"⚠️ Не удалось распарсить дату: {booking_date}")
                            continue
                else:
                    dt = booking_date
                
                # Сохраняем в правильном формате
                fixed_date = dt.strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute('UPDATE bookings SET booking_date = ? WHERE id = ?', (fixed_date, booking_id))
                fixed_count += 1
                
            except Exception as e:
                print(f"❌ Ошибка исправления записи {booking_id}: {e}")
        
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Исправлено {fixed_count} записей")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
async def send_instant_reminder(booking_id, minutes_until):
    """Отправляет мгновенное напоминание клиенту о скорой записи"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Получаем информацию о записи
        cursor.execute('''
            SELECT b.client_name, b.booking_date, s.name as service_name, 
                   m.name as master_name, sl.name as salon_name, b.user_id
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            JOIN salons sl ON b.salon_id = sl.id
            WHERE b.id = ?
        ''', (booking_id,))
        
        booking = cursor.fetchone()
        conn.close()
        
        if not booking:
            print(f"❌ Запись {booking_id} не найдена для мгновенного напоминания")
            return
        
        client_name, booking_date, service_name, master_name, salon_name, user_id = booking
        
        # 🔧 ОБРАБАТЫВАЕМ ДАТУ
        try:
            if isinstance(booking_date, str):
                booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
            else:
                booking_datetime = booking_date
            
            formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
        except Exception as e:
            print(f"❌ Ошибка обработки даты: {e}")
            formatted_date = "скоро"
        
        # 🔧 ФОРМИРУЕМ ТЕКСТ В ЗАВИСИМОСТИ ОТ ВРЕМЕНИ ДО ЗАПИСИ
        if minutes_until <= 5:
            time_text = "очень скоро"
            urgency_emoji = "🚨"
        elif minutes_until <= 15:
            time_text = f"через {int(minutes_until)} минут"
            urgency_emoji = "⚠️"
        else:
            time_text = f"через {int(minutes_until)} минут"
            urgency_emoji = "🔔"
        
        # 🔧 СООБЩЕНИЕ ДЛЯ КЛИЕНТА
        client_reminder_text = (
            f"{urgency_emoji} **СКОРАЯ ЗАПИСЬ!**\n\n"
            f"У вас запись {time_text}:\n\n"
            f"🏪 Салон: {salon_name}\n"
            f"💅 Услуга: {service_name}\n"
            f"👨‍💼 Мастер: {master_name}\n"
            f"📅 Время: {formatted_date}\n\n"
            f"📍 Пожалуйста, не опаздывайте!\n"
            f"📞 Телефон салона: уточните у администратора\n\n"
            f"❌ Если не можете прийти: /mybookings"
        )
        
        # 🔧 ОТПРАВЛЯЕМ ТОЛЬКО КЛИЕНТУ
        if user_id:
            app = Application.builder().token(BOT_TOKEN).build()
            await app.initialize()
            
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text=client_reminder_text
                )
                print(f"✅ Мгновенное напоминание отправлено клиенту {client_name}")
            except Exception as e:
                print(f"❌ Не удалось отправить мгновенное напоминание клиенту: {e}")
            
            await app.shutdown()
        
    except Exception as e:
        print(f"❌ Ошибка при отправке мгновенного напоминания: {e}")
# ==================== СИСТЕМА ОПЕРАТОРА ====================
async def handle_salon_toggle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик изменения статуса салона"""
    query = update.callback_query
    await query.answer()
    
    salon_id = query.data.split('_')[2]
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Получаем текущий статус салона
    cursor.execute('SELECT name, is_active FROM salons WHERE id = ?', (salon_id,))
    salon_info = cursor.fetchone()
    
    if not salon_info:
        await query.edit_message_text("❌ Салон не найден")
        conn.close()
        return
    
    salon_name, current_status = salon_info
    new_status = not current_status
    
    # Обновляем статус салона
    cursor.execute('UPDATE salons SET is_active = ? WHERE id = ?', (new_status, salon_id))
    conn.commit()
    conn.close()
    
    status_text = "активирован" if new_status else "отключен"
    status_emoji = "🟢" if new_status else "🔴"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Управление салонами", callback_data="operator_toggle_salon")],
        [InlineKeyboardButton("👑 В панель оператора", callback_data="operator_panel_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✅ **Салон {status_text}!**\n\n"
        f"{status_emoji} Салон: {salon_name}\n"
        f"📊 Новый статус: {'Активен' if new_status else 'Отключен'}\n\n"
        f"💡 Салон {'теперь доступен' if new_status else 'больше не доступен'} для клиентов",
        reply_markup=reply_markup
    )
async def operator_toggle_salon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик отключения/включения салонов"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_operator(user_id):
        await query.edit_message_text("❌ Доступ запрещен")
        return
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, is_active FROM salons ORDER BY is_active DESC, name')
    salons = cursor.fetchall()
    conn.close()
    
    if not salons:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="operator_panel_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("❌ Салонов пока нет", reply_markup=reply_markup)
        return
    
    keyboard = []
    for salon in salons:
        salon_id, salon_name, is_active = salon
        status_icon = "🟢" if is_active else "🔴"
        button_text = f"{status_icon} {salon_name}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"toggle_salon_{salon_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="operator_panel_main")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🔄 **Управление активностью салонов**\n\n"
        "🟢 - Активный салон\n"
        "🔴 - Отключенный салон\n\n"
        "Выберите салон для изменения статуса:",
        reply_markup=reply_markup
    )
async def get_my_salon_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Адаптированная функция для callback"""
    query = update.callback_query
    await query.answer()
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, unique_token FROM salons WHERE is_active = 1')
    salons = cursor.fetchall()
    conn.close()
    
    if not salons:
        await query.edit_message_text("❌ Салонов пока нет")
        return
    
    links_text = "🔗 **Уникальные ссылки салонов:**\n\n"
    for salon in salons:
        salon_link = generate_salon_link(salon[2])
        links_text += f"🏪 **{salon[1]}**\n🔗 `{salon_link}`\n\n"
    
    keyboard = [[InlineKeyboardButton("👑 Назад в панель", callback_data="operator_panel_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(links_text, reply_markup=reply_markup)
async def delete_database_command_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Адаптированная функция удаления БД для callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_operator(user_id):
        await query.edit_message_text("❌ Доступ запрещен")
        return
    
    # Генерируем сложный код подтверждения
    confirmation_code = secrets.token_hex(8).upper()
    context.user_data['delete_confirmation_code'] = confirmation_code
    context.user_data['waiting_for_confirmation'] = True
    
    keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="operator_panel_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"⚠️ **ОПАСНОЕ ДЕЙСТВИЕ - УДАЛЕНИЕ БАЗЫ ДАННЫХ** ⚠️\n\n"
        f"Для подтверждения удаления ВСЕХ данных введите следующий код:\n\n"
        f"🔐 `{confirmation_code}`\n\n"
        f"❌ **ЭТО ДЕЙСТВИЕ НЕОБРАТИМО!**\n"
        f"• Будут удалены ВСЕ салоны\n"
        f"• Будут удалены ВСЕ мастера\n"
        f"• Будут удалены ВСЕ услуги\n"
        f"• Будут удалены ВСЕ записи\n\n"
        f"Для подтверждения введите код выше в чат:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
async def cleanup_duplicates_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Адаптированная функция очистки дубликатов для callback"""
    query = update.callback_query
    await query.answer()
    
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Находим дубликаты
        cursor.execute('''
            SELECT telegram_user_id, COUNT(*) as count 
            FROM bot_users 
            GROUP BY telegram_user_id 
            HAVING COUNT(*) > 1
        ''')
        duplicates = cursor.fetchall()
        
        response = f"🔧 **Очистка дубликатов**\n\nНайдено дубликатов: {len(duplicates)}\n"
        
        for tg_id, count in duplicates:
            # Оставляем только последнюю запись для каждого пользователя
            cursor.execute('''
                DELETE FROM bot_users 
                WHERE telegram_user_id = ? 
                AND id NOT IN (
                    SELECT id FROM bot_users 
                    WHERE telegram_user_id = ? 
                    ORDER BY last_activity DESC 
                    LIMIT 1
                )
            ''', (tg_id, tg_id))
            response += f"• Пользователь {tg_id}: удалено {cursor.rowcount} дубликатов\n"
        
        conn.commit()
        conn.close()
        
        keyboard = [[InlineKeyboardButton("👑 Назад в панель", callback_data="operator_panel_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(response, reply_markup=reply_markup)
        
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка очистки: {e}")
async def owner_login_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Адаптированная функция входа для callback"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    print(f"🔍 owner_login_callback: начало авторизации для пользователя {user.id}")
    
    # 🔧 СБРАСЫВАЕМ КОНФЛИКТУЮЩИЕ ФЛАГИ
    context.user_data.clear()  # Полная очистка контекста
    
    # 🔧 ПРОПУСКАЕМ КАПЧУ ДЛЯ ВЛАДЕЛЬЦЕВ
    context.user_data['captcha_passed'] = True
    
    # 🔧 НАЧИНАЕМ ПРОЦЕСС АВТОРИЗАЦИИ
    context.user_data['waiting_for_owner_login'] = True
    
    keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu_return")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🔐 **Вход для владельцев салонов**\n\n"
        "Введите ваш логин:\n\n"
        "💡 <i>Логин выдается оператором при создании салона</i>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
async def resend_salon_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Адаптированная функция отправки ссылки для callback"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT unique_token FROM salons WHERE id = ?', (salon_id,))
    salon = cursor.fetchone()
    conn.close()
    
    if salon:
        await query.edit_message_text("📌 Отправляю ссылку вашего салона...")
        success = await send_and_pin_salon_link(
            chat_id=query.message.chat_id,
            salon_name=salon_name,
            unique_token=salon[0]
        )
        
        keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="owner_main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if success:
            await query.message.reply_text("✅ Ссылка отправлена и закреплена!", reply_markup=reply_markup)
        else:
            await query.message.reply_text("❌ Не удалось отправить ссылку. Попробуйте позже.", reply_markup=reply_markup)
    else:
        await query.edit_message_text("❌ Ошибка: салон не найден")
async def operator_panel_main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главная панель оператора"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_operator(user_id):
        await query.edit_message_text("❌ Доступ запрещен")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить салон", callback_data="operator_add_salon")],
        [InlineKeyboardButton("📊 Список салонов", callback_data="operator_list_salons")],
        [InlineKeyboardButton("🔄 Управление активностью", callback_data="operator_toggle_salon")],
        [InlineKeyboardButton("🔧 Техническое обслуживание", callback_data="operator_maintenance")],  # 🔧 ДОБАВЛЕНО
        [InlineKeyboardButton("🗑️ Удаление базы данных", callback_data="operator_delete_db")],
        [InlineKeyboardButton("🔄 Очистка дубликатов", callback_data="operator_cleanup")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu_return")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "👑 **Панель оператора**\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )
async def operator_list_salons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список салонов оператора с кнопкой назад"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_operator(user_id):
        await query.edit_message_text("❌ Доступ запрещен")
        return
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, unique_token, is_active FROM salons ORDER BY is_active DESC, name')
    salons = cursor.fetchall()
    conn.close()
    
    if not salons:
        # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ НАЗАД
        keyboard = [
            [InlineKeyboardButton("➕ Добавить салон", callback_data="operator_add_salon")],
            [InlineKeyboardButton("🔙 Назад", callback_data="operator_panel_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("❌ Салонов пока нет", reply_markup=reply_markup)
        return
    
    links_text = "🔗 **Уникальные ссылки салонов:**\n\n"
    for salon in salons:
        salon_id, salon_name, unique_token, is_active = salon
        salon_link = generate_salon_link(unique_token)
        status_icon = "🟢" if is_active else "🔴"
        status_text = "Активен" if is_active else "Неактивен"
        links_text += f"{status_icon} **{salon_name}**\n🔗 `{salon_link}`\n📊 Статус: {status_text}\n\n"
    
    # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКАМИ УПРАВЛЕНИЯ И НАЗАД
    keyboard = [
        [InlineKeyboardButton("🔄 Управление активностью", callback_data="operator_toggle_salon")],
        [InlineKeyboardButton("➕ Добавить салон", callback_data="operator_add_salon")],
        [InlineKeyboardButton("🔙 Назад в панель", callback_data="operator_panel_main")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu_return")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(links_text, reply_markup=reply_markup)
async def operator_all_links_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ всех ссылок салонов"""
    query = update.callback_query
    await query.answer()
    
    await get_my_salon_link_callback(update, context)
async def operator_delete_db_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление базы данных через инлайн-кнопку"""
    query = update.callback_query
    await query.answer()
    
    await delete_database_command_callback(update, context)
async def operator_cleanup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистка дубликатов через инлайн-кнопку"""
    query = update.callback_query
    await query.answer()
    
    await cleanup_duplicates_callback(update, context)
async def operator_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_operator(user_id):
        await update.message.reply_text("❌ Доступ запрещен")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить салон", callback_data="operator_add_salon")],
        [InlineKeyboardButton("📊 Список салонов", callback_data="operator_list_salons")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👨‍💼 **Панель оператора**\n\nВыберите действие:", reply_markup=reply_markup)
async def cleanup_duplicates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очищает дублирующиеся записи пользователей"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Находим дубликаты
        cursor.execute('''
            SELECT telegram_user_id, COUNT(*) as count 
            FROM bot_users 
            GROUP BY telegram_user_id 
            HAVING COUNT(*) > 1
        ''')
        duplicates = cursor.fetchall()
        
        response = f"🔧 Найдено дубликатов: {len(duplicates)}\n"
        
        for tg_id, count in duplicates:
            # Оставляем только последнюю запись для каждого пользователя
            cursor.execute('''
                DELETE FROM bot_users 
                WHERE telegram_user_id = ? 
                AND id NOT IN (
                    SELECT id FROM bot_users 
                    WHERE telegram_user_id = ? 
                    ORDER BY last_activity DESC 
                    LIMIT 1
                )
            ''', (tg_id, tg_id))
            response += f"• Пользователь {tg_id}: удалено {cursor.rowcount} дубликатов\n"
        
        conn.commit()
        conn.close()
        
        await update.message.reply_text(response)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка очистки: {e}")
async def operator_add_salon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик добавления салона с очисткой контекста"""
    query = update.callback_query
    await query.answer()
    
    # 🔧 ПОЛНАЯ ОЧИСТКА КОНТЕКСТА ПЕРЕД НАЧАЛОМ НОВОГО ПРОЦЕССА
    context.user_data.clear()
    
    # Устанавливаем флаг для ожидания названия салона
    context.user_data['waiting_for_salon_name'] = True
    
    keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="operator_panel_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🏪 **Добавление нового салона**\n\n"
        "Введите название салона:",
        reply_markup=reply_markup
    )
async def handle_salon_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода названия салона с проверкой состояния"""
    if not context.user_data.get('waiting_for_salon_name'):
        print(f"❌ handle_salon_name_input: флаг waiting_for_salon_name не установлен")
        await update.message.reply_text("❌ Неверный контекст. Начните заново через панель оператора.")
        return
    
    salon_name = update.message.text
    context.user_data['new_salon_name'] = salon_name
    context.user_data['waiting_for_salon_name'] = False
    context.user_data['waiting_for_salon_chat_id'] = True
    
    keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="operator_panel_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ Название салона: **{salon_name}**\n\n"
        "Введите Telegram Chat ID салона:\n"
        "(владелец может узнать через @userinfobot)\n\n"
        "💡 <i>Chat ID должен быть числом, может быть отрицательным для групп</i>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
async def handle_salon_chat_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода chat_id салона с отладкой"""
    if not context.user_data.get('waiting_for_salon_chat_id'):
        print(f"❌ handle_salon_chat_id_input: флаг waiting_for_salon_chat_id не установлен")
        await update.message.reply_text("❌ Неверный контекст. Начните заново через панель оператора.")
        return
    
    try:
        salon_chat_id = update.message.text
        
        # 🔒 ПРОВЕРКА CHAT ID
        try:
            chat_id_int = int(salon_chat_id)
        except ValueError:
            await update.message.reply_text(
                "❌ **Неверный формат Chat ID!**\n\n"
                "Chat ID должен быть числом.\n"
                "Пожалуйста, введите корректный Telegram Chat ID:"
            )
            return
        
        # Проверяем длину
        if len(salon_chat_id) < 6:
            await update.message.reply_text(
                "❌ **Неверная длина Chat ID!**\n\n"
                "Chat ID слишком короткий.\n"
                "Пожалуйста, введите корректный Telegram Chat ID:"
            )
            return
        
        salon_name = context.user_data['new_salon_name']
        unique_token = generate_unique_token()
        owner_login, owner_password = generate_credentials()
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO salons (name, telegram_chat_id, unique_token, owner_login, owner_password) 
            VALUES (?, ?, ?, ?, ?)
        ''', (salon_name, salon_chat_id, unique_token, owner_login, hash_password(owner_password)))
        
        salon_id = cursor.lastrowid
        
        # Стандартное время работы
        default_hours = [
            (salon_id, 0, '09:00', '20:00'), (salon_id, 1, '09:00', '20:00'),
            (salon_id, 2, '09:00', '20:00'), (salon_id, 3, '09:00', '20:00'),
            (salon_id, 4, '09:00', '20:00'), (salon_id, 5, '10:00', '18:00'),
            (salon_id, 6, '10:00', '16:00')
        ]
        
        for hours in default_hours:
            cursor.execute('INSERT INTO working_hours (salon_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)', hours)
        
        conn.commit()
        conn.close()
        
        salon_link = generate_salon_link(unique_token)
        
        # 🔧 ПОЛНАЯ ОЧИСТКА КОНТЕКСТА ПОСЛЕ УСПЕШНОГО СОЗДАНИЯ
        context.user_data.clear()
        
        keyboard = [[InlineKeyboardButton("👑 В панель оператора", callback_data="operator_panel_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ **Салон успешно добавлен!**\n\n"
            f"🏪 Название: {salon_name}\n🆔 ID: {salon_id}\n📞 Chat ID: {salon_chat_id}\n"
            f"🔗 Ссылка:\n`{salon_link}`\n\n"
            f"🔐 **Данные для входа владельца:**\n\n"
            f"Логин: `{owner_login}`\nПароль: `{owner_password}`\n\n"
            f"⚠️ <i>Сохраните эти данные!</i>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при добавлении салона: {e}")
async def operator_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Панель оператора для callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_operator(user_id):
        await query.edit_message_text("❌ Доступ запрещен")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить салон", callback_data="operator_add_salon")],
        [InlineKeyboardButton("📊 Список салонов", callback_data="operator_list_salons")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("👨‍💼 **Панель оператора**\n\nВыберите действие:", reply_markup=reply_markup)
async def owner_manage_services_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню управления услугами"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM services WHERE salon_id = ? AND is_active = 1', (salon_id,))
    active_services = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM services WHERE salon_id = ? AND is_active = 0', (salon_id,))
    inactive_services = cursor.fetchone()[0]
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить услугу", callback_data="owner_add_service")],
        [InlineKeyboardButton("📋 Список услуг", callback_data="owner_list_services")],
        [InlineKeyboardButton("✏️ Редактировать услугу", callback_data="owner_edit_service")],
        [InlineKeyboardButton("🔙 Назад", callback_data="owner_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"💅 **Управление услугами**\n🏪 Салон: {salon_name}\n\n"
        f"📊 Статистика:\n"
        f"• Активных услуг: {active_services}\n"
        f"• Неактивных услуг: {inactive_services}\n"
        f"• Всего: {active_services + inactive_services}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )
async def owner_list_services_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список услуг с навигацией"""
    query = update.callback_query
    await query.answer()
    
    salon_id = context.user_data.get('current_salon_id')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, price, duration, is_active 
        FROM services 
        WHERE salon_id = ? 
        ORDER BY is_active DESC, name
    ''', (salon_id,))
    services = cursor.fetchall()
    conn.close()
    
    if not services:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="owner_manage_services")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("❌ В вашем салоне пока нет услуг", reply_markup=reply_markup)
        return
    
    services_text = "💅 **Список услуг:**\n\n"
    
    active_services = [s for s in services if s[4]]
    inactive_services = [s for s in services if not s[4]]
    
    if active_services:
        services_text += "✅ **Активные услуги:**\n"
        for service in active_services:
            hours = service[3] // 60
            minutes = service[3] % 60
            duration_text = f"{hours}ч {minutes}м" if hours > 0 else f"{minutes}м"
            services_text += f"• {service[1]} - {service[2]} руб. ({duration_text})\n"
        services_text += "\n"
    
    if inactive_services:
        services_text += "❌ **Неактивные услуги:**\n"
        for service in inactive_services:
            services_text += f"• {service[1]} - {service[2]} руб.\n"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить список", callback_data="owner_list_services")],
        [InlineKeyboardButton("🔙 Назад", callback_data="owner_manage_services")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(services_text, reply_markup=reply_markup)
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Универсальная функция показа главного меню"""
    # Определяем пользователя и тип обновления
    if hasattr(update, 'callback_query') and update.callback_query:
        user = update.callback_query.from_user
        message_func = update.callback_query.edit_message_text
    else:
        user = update.message.from_user
        message_func = update.message.reply_text
    
    # 🔧 РЕГИСТРИРУЕМ/ОБНОВЛЯЕМ ПОЛЬЗОВАТЕЛЯ
    register_bot_user(user.id, user.username, user.first_name)
    update_user_activity(user.id)
    
    # 🔧 ЕСЛИ ЭТО ОПЕРАТОР
    if is_operator(user.id):
        keyboard = [
            [InlineKeyboardButton("👑 Панель оператора", callback_data="operator_panel_main")],
            [InlineKeyboardButton("🔐 Войти как владелец", callback_data="owner_login_start")],
            [InlineKeyboardButton("🔗 Все ссылки салонов", callback_data="operator_all_links")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message_func(
            "👑 **Панель оператора**\n\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )
        return
    
    # 🔧 ЕСЛИ ПОЛЬЗОВАТЕЛЬ АВТОРИЗОВАН КАК ВЛАДЕЛЕЦ
    if context.user_data.get('owner_authenticated'):
        salon_name = context.user_data.get('current_salon_name', 'ваш салон')
        
        keyboard = [
            [InlineKeyboardButton("📋 Записи", callback_data="owner_bookings")],
            [InlineKeyboardButton("👨‍💼 Управление мастерами", callback_data="owner_manage_masters")],
            [InlineKeyboardButton("💅 Управление услугами", callback_data="owner_manage_services")],
            [InlineKeyboardButton("⚙️ Настройки салона", callback_data="owner_salon_settings")],
            [InlineKeyboardButton("📊 Статистика", callback_data="owner_stats")],
            [InlineKeyboardButton("🔗 Получить ссылку салона", callback_data="owner_get_link")],
            [InlineKeyboardButton("🚪 Выйти из системы", callback_data="owner_logout_handler")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message_func(
            f"🏪 **Панель управления {salon_name}**\n\n"
            f"Выберите раздел управления:",
            reply_markup=reply_markup
        )
        return
    
    # 🔧 ПРОВЕРЯЕМ СТАТУС КАПЧИ
    user_captcha_passed = get_user_captcha_status(user.id)
    
    # 🔧 ЕСЛИ КАПЧА УЖЕ ПРОЙДЕНА
    if user_captcha_passed:
        # 🔒 СТРОГАЯ ПРОВЕРКА: ЕСТЬ ЛИ ДЕЙСТВИТЕЛЬНО САЛОН В КОНТЕКСТЕ
        salon_id = context.user_data.get('current_salon_id')
        salon_name = context.user_data.get('current_salon_name')
        
        if salon_id and salon_name:
            # Пользователь действительно в салоне - показываем меню салона
            keyboard = [
                [InlineKeyboardButton("💅 Записаться на услугу", callback_data="book_service_main")],
                [InlineKeyboardButton("👨‍💼 Наши мастера", callback_data="show_masters_main")],
                [InlineKeyboardButton("💎 Наши услуги", callback_data="show_services_main")],
                [InlineKeyboardButton("📋 Мои записи", callback_data="my_bookings_main")],
                [InlineKeyboardButton("📚 История записей", callback_data="client_booking_history")],
                [InlineKeyboardButton("❓ Помощь", callback_data="show_faq")],
                [InlineKeyboardButton("🔐 Вход для владельцев", callback_data="owner_login_start")],
                [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu_return")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message_func(
                f"🏪 **{salon_name}**\n\n"
                f"Выберите действие:",
                reply_markup=reply_markup
            )
            return
        
        # 🔧 ЕСЛИ САЛОНА НЕТ - ОБЫЧНОЕ ПРИВЕТСТВИЕ БЕЗ ДОСТУПА К ФУНКЦИЯМ САЛОНА
        keyboard = [
            [InlineKeyboardButton("🔐 Вход для владельцев", callback_data="owner_login_start")],
            [InlineKeyboardButton("❓ Помощь", callback_data="show_faq")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message_func(
            f"Привет {user.first_name}! 🎉\n"
            f"Добро пожаловать в систему записи!\n\n"
            f"🔒 **Для доступа к функциям салона:**\n"
            f"• Используйте уникальную ссылку салона\n\n"
            f"🏪 **Для владельцев салонов:**\n"
            f"• Войдите в систему управления\n\n",
            reply_markup=reply_markup
        )
        return
    
    # 🔧 ЕСЛИ КАПЧА НЕ ПРОЙДЕНА - ЗАПРАШИВАЕМ КАПЧУ
    if hasattr(update, 'callback_query') and update.callback_query:
        await ask_captcha_callback(update, context)
    else:
        await ask_captcha(update, context)
async def back_to_previous_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Универсальный обработчик возврата назад"""
    query = update.callback_query
    await query.answer()
    
    # Определяем откуда пришли и возвращаемся
    if context.user_data.get('owner_authenticated'):
        await owner_main_menu_handler(update, context)
    elif context.user_data.get('current_salon_id'):
        await show_client_main_menu(update, context)
    else:
        await show_main_menu(update, context)
async def ask_captcha_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрос капчи для callback"""
    query = update.callback_query
    
    question, answer = generate_captcha()
    context.user_data['captcha_answer'] = answer
    context.user_data['waiting_for_captcha'] = True
    
    await query.edit_message_text(
        f"🤖 **Добро пожаловать!**\n\n"
        f"Пройдите простую проверку:\n"
        f"**{question}** = ?\n\n"
        f"Введите ответ цифрами в чат:"
    )
async def main_menu_return_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Универсальный возврат в главное меню"""
    query = update.callback_query
    await query.answer()
    
    # Очищаем контекст
    context.user_data.clear()
    
    # Показываем главное меню напрямую
    user = query.from_user
    
    # 🔧 РЕГИСТРИРУЕМ/ОБНОВЛЯЕМ ПОЛЬЗОВАТЕЛЯ
    register_bot_user(user.id, user.username, user.first_name)
    update_user_activity(user.id)
    
    # 🔧 ЕСЛИ ЭТО ОПЕРАТОР
    if is_operator(user.id):
        keyboard = [
            [InlineKeyboardButton("👑 Панель оператора", callback_data="operator_panel_main")],
            [InlineKeyboardButton("🔐 Войти как владелец", callback_data="owner_login_start")],
            [InlineKeyboardButton("🔗 Все ссылки салонов", callback_data="operator_all_links")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "👑 **Панель оператора**\n\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )
        return
    
    # 🔧 ЕСЛИ ПОЛЬЗОВАТЕЛЬ АВТОРИЗОВАН КАК ВЛАДЕЛЕЦ
    if context.user_data.get('owner_authenticated'):
        salon_name = context.user_data.get('current_salon_name', 'ваш салон')
        
        keyboard = [
            [InlineKeyboardButton("📋 Записи", callback_data="owner_bookings")],
            [InlineKeyboardButton("👨‍💼 Управление мастерами", callback_data="owner_manage_masters")],
            [InlineKeyboardButton("💅 Управление услугами", callback_data="owner_manage_services")],
            [InlineKeyboardButton("⚙️ Настройки салона", callback_data="owner_salon_settings")],
            [InlineKeyboardButton("📊 Статистика", callback_data="owner_stats")],
            [InlineKeyboardButton("🔗 Моя ссылка салона", callback_data="owner_get_link")],
            [InlineKeyboardButton("❓ Помощь", callback_data="show_faq")],
            [InlineKeyboardButton("🚪 Выйти", callback_data="owner_logout_handler")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🏪 **Панель управления {salon_name}**\n\n"
            f"Выберите раздел управления:",
            reply_markup=reply_markup
        )
        return
    
    # 🔧 ПРОВЕРЯЕМ СТАТУС КАПЧИ
    user_captcha_passed = get_user_captcha_status(user.id)
    
    # 🔧 ЕСЛИ КАПЧА УЖЕ ПРОЙДЕНА
    if user_captcha_passed:
        # Проверяем, находится ли пользователь в салоне
        if context.user_data.get('current_salon_id'):
            salon_name = context.user_data.get('current_salon_name', 'салон')
            
            keyboard = [
                [InlineKeyboardButton("💅 Записаться на услугу", callback_data="book_service_main")]
                [InlineKeyboardButton("👨‍💼 Наши мастера", callback_data="show_masters_main")],
                [InlineKeyboardButton("💎 Наши услуги", callback_data="show_services_main")],
                [InlineKeyboardButton("📋 Мои записи", callback_data="my_bookings_main")],
                [InlineKeyboardButton("📚 История записей", callback_data="client_booking_history")]
                [InlineKeyboardButton("❓ Помощь", callback_data="show_faq")],
                [InlineKeyboardButton("🔐 Вход для владельцев", callback_data="owner_login_start")],
                [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu_return")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"🏪 **{salon_name}**\n\n"
                f"Выберите действие:",
                reply_markup=reply_markup
            )
            return
        
        # 🔧 ОБЫЧНОЕ ПРИВЕТСТВИЕ
        keyboard = [
            [InlineKeyboardButton("🔐 Вход для владельцев", callback_data="owner_login_start")],
            [InlineKeyboardButton("❓ Помощь", callback_data="show_faq")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Привет {user.first_name}! 🎉\n"
            f"Добро пожаловать в систему записи!\n\n"
            f"👥 **Для клиентов:**\n"
            f"• Используйте уникальную ссылку салона\n\n"
            f"🏪 **Для владельцев салонов:**\n"
            f"• Войдите в систему управления\n\n",
            reply_markup=reply_markup
        )
        return
    
    # 🔧 ЕСЛИ КАПЧА НЕ ПРОЙДЕНА - ЗАПРАШИВАЕМ КАПЧУ
    await ask_captcha_callback(update, context)
async def owner_login_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса авторизации владельца"""
    query = update.callback_query
    await query.answer()
    
    # 🔧 ОЧИЩАЕМ КОНТЕКСТ
    context.user_data.clear()
    context.user_data['waiting_for_owner_login'] = True
    
    # 🔧 СОЗДАЕМ СООБЩЕНИЕ ДЛЯ РЕДАКТИРОВАНИЯ
    message = await query.edit_message_text(
        "🔐 **Вход для владельцев салонов**\n\n"
        "Введите ваш логин:\n\n"
        "💡 Логин выдается оператором при создании салона"
    )
    
    # 🔧 СОХРАНЯЕМ ID СООБЩЕНИЯ ДЛЯ РЕДАКТИРОВАНИЯ
    context.user_data['login_message_id'] = message.message_id
    context.user_data['login_chat_id'] = message.chat_id
async def handle_owner_login_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода логина владельца с редактированием сообщения"""
    if not context.user_data.get('waiting_for_owner_login'):
        return
    
    try:
        login = update.message.text.strip()
        user = update.message.from_user
        
        # 🔒 ПРОВЕРКА ЛОГИНА
        if not login:
            # 🔧 РЕДАКТИРУЕМ СУЩЕСТВУЮЩЕЕ СООБЩЕНИЕ
            await context.bot.edit_message_text(
                chat_id=context.user_data.get('login_chat_id'),
                message_id=context.user_data.get('login_message_id'),
                text="❌ **Логин не может быть пустым!**\n\n"
                     "Введите ваш логин:\n\n"
                     "💡 Логин выдается оператором при создании салона"
            )
            return
        
        if len(login) < 3:
            await context.bot.edit_message_text(
                chat_id=context.user_data.get('login_chat_id'),
                message_id=context.user_data.get('login_message_id'),
                text="❌ **Слишком короткий логин!**\n\n"
                     "Логин должен содержать минимум 3 символа.\n\n"
                     "Введите ваш логин:"
            )
            return
        
        # 🔧 СОХРАНЯЕМ ЛОГИН И ПЕРЕХОДИМ К ПАРОЛЮ
        context.user_data['owner_login'] = login
        context.user_data['waiting_for_owner_login'] = False
        context.user_data['waiting_for_owner_password'] = True
        
        # 🔧 РЕДАКТИРУЕМ СООБЩЕНИЕ ДЛЯ ПАРОЛЯ
        await context.bot.edit_message_text(
            chat_id=context.user_data.get('login_chat_id'),
            message_id=context.user_data.get('login_message_id'),
            text=f"👤 **Логин принят:** {login}\n\n"
                 f"🔐 Введите ваш пароль:\n\n"
                 f"💡 Пароль чувствителен к регистру"
        )
        
        # 🔧 УДАЛЯЕМ СООБЩЕНИЕ С ЛОГИНОМ ПОЛЬЗОВАТЕЛЯ
        try:
            await update.message.delete()
        except:
            pass
        
    except Exception as e:
        print(f"❌ Ошибка в handle_owner_login_input: {e}")
async def handle_owner_password_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода пароля владельца с редактированием сообщения"""
    if not context.user_data.get('waiting_for_owner_password'):
        return
    
    try:
        password = update.message.text.strip()
        login = context.user_data.get('owner_login')
        
        if not login:
            await context.bot.edit_message_text(
                chat_id=context.user_data.get('login_chat_id'),
                message_id=context.user_data.get('login_message_id'),
                text="❌ Ошибка сессии. Логин не найден.\n\n"
                     "Пожалуйста, начните заново."
            )
            context.user_data.clear()
            return
        
        # 🔒 ПРОВЕРКА ПАРОЛЯ
        if not password:
            await context.bot.edit_message_text(
                chat_id=context.user_data.get('login_chat_id'),
                message_id=context.user_data.get('login_message_id'),
                text=f"👤 **Логин:** {login}\n\n"
                     f"❌ Пароль не может быть пустым!\n\n"
                     f"🔐 Введите ваш пароль:"
            )
            return
        
        # 🔧 ПРОВЕРЯЕМ АВТОРИЗАЦИЮ
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, name, owner_password, unique_token FROM salons WHERE owner_login = ? AND is_active = 1', 
            (login,)
        )
        salon = cursor.fetchone()
        conn.close()
        
        if salon and salon[2] == hash_password(password):
            # ✅ УСПЕШНАЯ АВТОРИЗАЦИЯ
            salon_id, salon_name, owner_password, unique_token = salon
            
            # 🔧 СОХРАНЯЕМ ДАННЫЕ СЕССИИ
            context.user_data.update({
                'current_salon_id': salon_id,
                'current_salon_name': salon_name,
                'owner_authenticated': True,
                'waiting_for_owner_password': False
            })
            context.user_data.pop('owner_login', None)
            context.user_data.pop('login_message_id', None)
            context.user_data.pop('login_chat_id', None)
            
            # 🔧 СОЗДАЕМ КЛАВИАТУРУ ДЛЯ ВЛАДЕЛЬЦА
            keyboard = [
                [InlineKeyboardButton("📋 Записи", callback_data="owner_bookings")],
                [InlineKeyboardButton("👨‍💼 Управление мастерами", callback_data="owner_manage_masters")],
                [InlineKeyboardButton("💅 Управление услугами", callback_data="owner_manage_services")],
                [InlineKeyboardButton("⚙️ Настройки салона", callback_data="owner_salon_settings")],
                [InlineKeyboardButton("📊 Статистика", callback_data="owner_stats")],
                [InlineKeyboardButton("🔗 Получить ссылку салона", callback_data="owner_get_link")],
                [InlineKeyboardButton("🚪 Выйти из системы", callback_data="owner_logout_handler")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # 🔧 РЕДАКТИРУЕМ СООБЩЕНИЕ С УСПЕШНЫМ ВХОДОМ
            await context.bot.edit_message_text(
                chat_id=update.message.chat_id,
                message_id=context.user_data.get('login_message_id'),
                text=f"✅ **Успешный вход!**\n\n"
                     f"🏪 Добро пожаловать в {salon_name}!\n\n"
                     f"Выберите раздел для управления:",
                reply_markup=reply_markup
            )
            
            # 🔧 УДАЛЯЕМ СООБЩЕНИЕ С ПАРОЛЕМ ПОЛЬЗОВАТЕЛЯ
            try:
                await update.message.delete()
            except:
                pass
            
        else:
            # ❌ НЕВЕРНЫЙ ЛОГИН ИЛИ ПАРОЛЬ
            await context.bot.edit_message_text(
                chat_id=context.user_data.get('login_chat_id'),
                message_id=context.user_data.get('login_message_id'),
                text="❌ **Неверный логин или пароль!**\n\n"
                     "Проверьте правильность введенных данных.\n\n"
                     "💡 Если вы забыли данные, обратитесь к оператору системы"
            )
            context.user_data.clear()
            
    except Exception as e:
        print(f"❌ Ошибка в handle_owner_password_input: {e}")
        await context.bot.edit_message_text(
            chat_id=context.user_data.get('login_chat_id'),
            message_id=context.user_data.get('login_message_id'),
            text="❌ Ошибка при авторизации. Попробуйте еще раз."
        )
        context.user_data.clear()
async def owner_get_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение ссылки салона"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT unique_token FROM salons WHERE id = ?', (salon_id,))
    salon = cursor.fetchone()
    conn.close()
    
    if salon:
        salon_link = generate_salon_link(salon[0])
        
        keyboard = [
            [InlineKeyboardButton("📌 Отправить и закрепить", callback_data="owner_pin_link")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🔗 **Ссылка вашего салона**\n\n"
            f"🏪 Салон: {salon_name}\n"
            f"🔗 Ссылка для клиентов:\n`{salon_link}`\n\n"
            f"📋 **Как использовать:**\n"
            f"• Отправьте эту ссылку клиентам\n"
            f"• Клиенты могут записываться через нее\n"
            f"• Все записи будут приходить в настроенный чат\n\n"
            f"💡 <i>Вы можете отправить и закрепить ссылку в этом чате</i>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    else:
        await query.edit_message_text("❌ Ошибка: салон не найден")
async def resend_salon_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Повторная отправка ссылки салона"""
    if not context.user_data.get('owner_authenticated'):
        await update.message.reply_text("❌ Сначала войдите в систему: /login")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT unique_token FROM salons WHERE id = ?', (salon_id,))
    salon = cursor.fetchone()
    conn.close()
    
    if salon:
        await update.message.reply_text("📌 Отправляю ссылку вашего салона...")
        success = await send_and_pin_salon_link(
            chat_id=update.message.chat_id,
            salon_name=salon_name,
            unique_token=salon[0]
        )
        
        if success:
            await update.message.reply_text("✅ Ссылка отправлена и закреплена!")
        else:
            await update.message.reply_text("❌ Не удалось отправить ссылку. Попробуйте позже.")
    else:
        await update.message.reply_text("❌ Ошибка: салон не найден")
async def owner_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса авторизации владельца"""
    try:
        user = update.message.from_user
        print(f"🔍 owner_login: начало авторизации для пользователя {user.id}")
        
        # 🔧 СБРАСЫВАЕМ КОНФЛИКТУЮЩИЕ ФЛАГИ
        context.user_data.pop('waiting_for_contact', None)
        context.user_data.pop('waiting_for_captcha', None)
        context.user_data.pop('first_time_user', None)
        
        # 🔧 ПРОПУСКАЕМ КАПЧУ ДЛЯ ВЛАДЕЛЬЦЕВ
        context.user_data['captcha_passed'] = True
        
        # 🔧 НАЧИНАЕМ ПРОЦЕСС АВТОРИЗАЦИИ
        context.user_data['waiting_for_owner_login'] = True
        context.user_data.pop('owner_login', None)
        context.user_data.pop('owner_authenticated', None)
        
        print(f"✅ Установлен waiting_for_owner_login = True для пользователя {user.id}")
        
        await update.message.reply_text(
            "🔐 **Вход для владельцев салонов**\n\n"
            "Введите ваш логин:\n\n"
            "💡 <i>Логин выдается оператором при создании салона</i>",
            parse_mode='HTML'
        )
        
    except Exception as e:
        print(f"❌ Ошибка в owner_login: {e}")
        await update.message.reply_text("❌ Ошибка при начале авторизации. Попробуйте еще раз.")
async def owner_logout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выхода из системы через кнопку"""
    query = update.callback_query
    await query.answer()
    
    # 🔧 ПОДТВЕРЖДЕНИЕ ВЫХОДА
    keyboard = [
        [InlineKeyboardButton("✅ Да, выйти", callback_data="confirm_logout")],
        [InlineKeyboardButton("❌ Отмена", callback_data="owner_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🚪 <b>Подтверждение выхода</b>\n\n"
        "Вы уверены, что хотите выйти из системы?\n\n"
        "⚠️ <b>После выхода:</b>\n"
        "• Сессия будет завершена\n"
        "• Потребуется повторный вход\n"
        "• Данные авторизации будут удалены",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
async def confirm_logout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтвержденный выход из системы"""
    query = update.callback_query
    await query.answer()
    
    # 🔧 СОХРАНЯЕМ ДАННЫЕ ДЛЯ СООБЩЕНИЯ
    salon_name = context.user_data.get('current_salon_name', 'салон')
    
    # 🔧 ПОЛНАЯ ОЧИСТКА КОНТЕКСТА
    context.user_data.clear()
    
    await query.edit_message_text(
        f"✅ <b>Выход выполнен!</b>\n\n"
        f"Вы вышли из системы управления {salon_name}.\n\n"
        f"🔒 <b>Безопасность:</b>\n"
        f"• Сессия завершена\n"
        f"• Данные удалены\n"
        f"• Требуется повторная авторизация\n\n"
        f"Для входа используйте: /login",
        parse_mode='HTML'
    )
async def owner_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Строгий выход из системы - только по команде"""
    # 🔧 ПРОВЕРЯЕМ, ЧТО ЭТО КОМАНДА, А НЕ СООБЩЕНИЕ
    if not update.message:
        return
    
    # 🔧 ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА АВТОРИЗАЦИИ
    if not context.user_data.get('owner_authenticated'):
        await update.message.reply_text("❌ Вы не авторизованы")
        return
    
    # 🔧 СОХРАНЯЕМ ДАННЫЕ ДЛЯ СООБЩЕНИЯ
    salon_name = context.user_data.get('current_salon_name', 'салон')
    
    # 🔧 ПОЛНАЯ ОЧИСТКА КОНТЕКСТА (только при явном выходе)
    # Очищаем ВСЕ данные, включая капчу
    context.user_data.clear()
    
    await update.message.reply_text(
        f"✅ Вы успешно вышли из системы управления {salon_name}.\n\n"
        f"Для входа используйте: /login\n\n"
        f"⚠️ <b>Безопасность:</b> сессия завершена, данные удалены.",
        parse_mode='HTML'
    )
async def owner_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 🔧 ПРОВЕРЯЕМ ТИП UPDATE - сообщение или callback query
    if hasattr(update, 'callback_query') and update.callback_query:
        query = update.callback_query
        await query.answer()
        update = query  # Используем query для редактирования сообщения
    elif hasattr(update, 'message') and update.message:
        # Это обычное сообщение, а не callback
        pass
    
    salon_name = context.user_data.get('current_salon_name', 'ваш салон')
    
    keyboard = [
        [InlineKeyboardButton("📋 Записи", callback_data="owner_bookings")],
        [InlineKeyboardButton("👨‍💼 Управление мастерами", callback_data="owner_manage_masters")],
        [InlineKeyboardButton("💅 Управление услугами", callback_data="owner_manage_services")],
        [InlineKeyboardButton("⚙️ Настройки салона", callback_data="owner_salon_settings")],
        [InlineKeyboardButton("📊 Статистика", callback_data="owner_stats")],
        [InlineKeyboardButton("🚪 Выйти из системы", callback_data="owner_logout_handler")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # 🔧 ПРОВЕРЯЕМ, МОЖЕМ ЛИ РЕДАКТИРОВАТЬ СООБЩЕНИЕ ИЛИ НУЖНО ОТПРАВИТЬ НОВОЕ
    if hasattr(update, 'edit_message_text'):
        # Это callback query - редактируем существующее сообщение
        await update.edit_message_text(
            f"🏪 **Панель управления {salon_name}**\n\nВыберите раздел:",
            reply_markup=reply_markup
        )
    else:
        # Это обычное сообщение - отправляем новое
        await update.message.reply_text(
            f"🏪 **Панель управления {salon_name}**\n\nВыберите раздел:",
            reply_markup=reply_markup
        )
async def fix_existing_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Исправляет существующие напоминания с неправильным форматом даты"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Получаем все напоминания
        cursor.execute('SELECT id, reminder_time FROM booking_reminders')
        reminders = cursor.fetchall()
        
        fixed_count = 0
        for reminder_id, reminder_time in reminders:
            try:
                # Если время уже в правильном формате, пропускаем
                if isinstance(reminder_time, str) and ':' in reminder_time:
                    continue
                    
                # Преобразуем в правильный формат
                if isinstance(reminder_time, str):
                    # Пробуем разные форматы
                    try:
                        dt = datetime.strptime(reminder_time, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        try:
                            dt = datetime.strptime(reminder_time, '%Y-%m-%d %H:%M')
                        except ValueError:
                            print(f"⚠️ Не удалось распарсить время: {reminder_time}")
                            continue
                else:
                    dt = reminder_time
                
                # Сохраняем в правильном формате
                fixed_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute('UPDATE booking_reminders SET reminder_time = ? WHERE id = ?', (fixed_time, reminder_id))
                fixed_count += 1
                
            except Exception as e:
                print(f"❌ Ошибка исправления напоминания {reminder_id}: {e}")
        
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Исправлено {fixed_count} напоминаний")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
# ==================== УПРАВЛЕНИЕ МАСТЕРАМИ ====================
async def owner_confirmed_bookings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает подтвержденные клиентом записи"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT b.id, b.booking_date, s.name as service_name, 
               m.name as master_name, b.client_name, b.client_phone,
               b.status, b.confirmed
        FROM bookings b
        JOIN services s ON b.service_id = s.id
        JOIN masters m ON b.master_id = m.id
        WHERE b.salon_id = ? AND b.status = 'confirmed' AND b.confirmed = 1
        AND b.booking_date > datetime('now')
        ORDER BY b.booking_date ASC
    ''', (salon_id,))
    
    bookings = cursor.fetchall()
    conn.close()
    
    if not bookings:
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к записям", callback_data="owner_bookings")],
            [InlineKeyboardButton("📋 Все записи", callback_data="owner_all_bookings")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ **Подтвержденные записи**\n🏪 {salon_name}\n\n"
            "📭 Подтвержденных записей пока нет",
            reply_markup=reply_markup
        )
        return
    
    confirmed_text = f"✅ **Подтвержденные записи**\n🏪 {salon_name}\n\n"
    
    for booking in bookings:
        booking_id, booking_date, service_name, master_name, client_name, client_phone, status, confirmed = booking
        
        try:
            if isinstance(booking_date, str):
                booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
            else:
                booking_datetime = booking_date
            
            formatted_date = booking_datetime.strftime('%d.%m в %H:%M')
            time_until = (booking_datetime - datetime.now()).total_seconds() / 3600
            
        except Exception as e:
            formatted_date = "дата не определена"
            time_until = 999
        
        time_info = ""
        if time_until > 0:
            if time_until < 1:
                time_info = " (менее часа)"
            elif time_until < 2:
                time_info = f" (через {int(time_until)} час)"
            elif time_until < 5:
                time_info = f" (через {int(time_until)} часа)"
            else:
                time_info = f" (через {int(time_until)} часов)"
        
        confirmed_text += (
            f"✅ **{formatted_date}**{time_info}\n"
            f"   👤 {client_name} | 📞 {client_phone}\n"
            f"   💅 {service_name} | 👨‍💼 {master_name}\n\n"
        )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад к записям", callback_data="owner_bookings")],
        [InlineKeyboardButton("📋 Все записи", callback_data="owner_all_bookings")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(confirmed_text, reply_markup=reply_markup)
async def owner_pending_bookings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает записи, ожидающие подтверждения клиентом"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT b.id, b.booking_date, s.name as service_name, 
               m.name as master_name, b.client_name, b.client_phone,
               b.status, b.confirmed
        FROM bookings b
        JOIN services s ON b.service_id = s.id
        JOIN masters m ON b.master_id = m.id
        WHERE b.salon_id = ? AND b.status = 'confirmed' AND b.confirmed = 0
        AND b.booking_date > datetime('now')
        ORDER BY b.booking_date ASC
    ''', (salon_id,))
    
    bookings = cursor.fetchall()
    conn.close()
    
    if not bookings:
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к записям", callback_data="owner_bookings")],
            [InlineKeyboardButton("📋 Все записи", callback_data="owner_all_bookings")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"⏳ **Записи, ожидающие подтверждения**\n🏪 {salon_name}\n\n"
            "✅ Все записи подтверждены клиентами",
            reply_markup=reply_markup
        )
        return
    
    # Сохраняем записи в контексте для постраничного просмотра
    context.user_data['owner_pending_bookings'] = bookings
    context.user_data['current_owner_booking_page'] = 0
    
    await show_owner_pending_booking_page(update, context, 0)
async def show_owner_pending_booking_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page_number):
    """Показывает страницу с записями, ожидающими подтверждения"""
    bookings = context.user_data.get('owner_pending_bookings', [])
    
    if not bookings:
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к записям", callback_data="owner_bookings")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text("❌ Записи не найдены", reply_markup=reply_markup)
        return
    
    # Проверяем валидность номера страницы
    if page_number < 0:
        page_number = 0
    if page_number >= len(bookings):
        page_number = len(bookings) - 1
    
    context.user_data['current_owner_booking_page'] = page_number
    
    # Получаем запись для текущей страницы
    booking = bookings[page_number]
    booking_id, booking_date, service_name, master_name, client_name, client_phone, status, confirmed = booking
    
    # 🔧 ОБРАБАТЫВАЕМ ДАТУ
    try:
        if isinstance(booking_date, str):
            booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
        else:
            booking_datetime = booking_date
        
        formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
        time_until = (booking_datetime - datetime.now()).total_seconds() / 3600
        
    except Exception as e:
        formatted_date = "дата не определена"
        time_until = 999
    
    booking_text = (
        f"⏳ **Запись ожидает подтверждения** #{booking_id}\n\n"
        f"👤 **Клиент:** {client_name}\n"
        f"📞 **Телефон:** `{client_phone}`\n"
        f"💅 **Услуга:** {service_name}\n"
        f"👨‍💼 **Мастер:** {master_name}\n"
        f"📅 **Дата и время:** {formatted_date}\n"
        f"📄 **Страница:** {page_number + 1} из {len(bookings)}\n"
    )
    
    # Информация о времени до записи
    if time_until > 0:
        if time_until < 1:
            time_info = "⏰ Менее чем через 1 час"
        elif time_until < 2:
            time_info = f"⏰ Через {int(time_until)} час"
        elif time_until < 5:
            time_info = f"⏰ Через {int(time_until)} часа"
        else:
            time_info = f"⏰ Через {int(time_until)} часов"
        booking_text += f"\n{time_info}\n"
    
    # Создаем клавиатуру
    keyboard = []
    
    # Кнопка напоминания
    keyboard.append([InlineKeyboardButton("📞 Напомнить клиенту", callback_data=f"remind_booking_{booking_id}")])
    
    # Кнопки навигации
    nav_buttons = []
    
    if page_number > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"owner_pending_prev_{page_number-1}"))
    
    if page_number < len(bookings) - 1:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"owner_pending_next_{page_number+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔄 Обновить список", callback_data="owner_pending_bookings")])
    keyboard.append([InlineKeyboardButton("🔙 Назад к записям", callback_data="owner_bookings")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(
            booking_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
async def handle_remind_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик напоминания клиенту о записи"""
    query = update.callback_query
    await query.answer()
    
    try:
        booking_id = int(query.data.split('_')[2])
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Получаем информацию о записи
        cursor.execute('''
            SELECT b.client_name, b.booking_date, s.name as service_name, 
                   m.name as master_name, sl.name as salon_name, b.user_id, b.confirmed
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            JOIN salons sl ON b.salon_id = sl.id
            WHERE b.id = ?
        ''', (booking_id,))
        
        booking = cursor.fetchone()
        
        if not booking:
            await query.edit_message_text("❌ Запись не найдена")
            conn.close()
            return
        
        client_name, booking_date, service_name, master_name, salon_name, user_id, confirmed = booking
        
        # 🔧 ОБРАБАТЫВАЕМ ДАТУ
        try:
            if isinstance(booking_date, str):
                booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
            else:
                booking_datetime = booking_date
            
            formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
            time_until = (booking_datetime - datetime.now()).total_seconds() / 3600
            
        except Exception as e:
            formatted_date = "дата не определена"
            time_until = 999
        
        # Отправляем напоминание клиенту
        if user_id:
            reminder_text = (
                f"🔔 **НАПОМИНАНИЕ ОТ САЛОНА**\n\n"
                f"Салон {salon_name} напоминает о вашей записи:\n\n"
                f"💅 Услуга: {service_name}\n"
                f"👨‍💼 Мастер: {master_name}\n"
                f"📅 Время: {formatted_date}\n\n"
            )
            
            if not confirmed:
                reminder_text += (
                    f"⏳ <b>Запись ожидает подтверждения</b>\n\n"
                    f"📍 Пожалуйста, подтвердите, что придете:"
                )
                keyboard = [
                    [InlineKeyboardButton("✅ Подтвердить запись", callback_data=f"confirm_booking_{booking_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            else:
                reminder_text += "📍 Ждем вас в салоне! Не опаздывайте! ⏰"
                reply_markup = None
            
            app = Application.builder().token(BOT_TOKEN).build()
            await app.initialize()
            
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text=reminder_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                await query.edit_message_text(f"✅ Напоминание отправлено клиенту {client_name}")
            except Exception as e:
                await query.edit_message_text(f"❌ Не удалось отправить напоминание клиенту")
            
            await app.shutdown()
        else:
            await query.edit_message_text("❌ Не удалось отправить напоминание (клиент не найден)")
        
        conn.close()
        
    except Exception as e:
        await query.edit_message_text("❌ Ошибка при отправке напоминания")
        logger.error(f"Error in handle_remind_booking: {e}")
async def owner_pin_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка и закрепление ссылки салона"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT unique_token FROM salons WHERE id = ?', (salon_id,))
    salon = cursor.fetchone()
    conn.close()
    
    if salon:
        await query.edit_message_text("📌 Отправляю ссылку вашего салона...")
        success = await send_and_pin_salon_link(
            chat_id=query.message.chat_id,
            salon_name=salon_name,
            unique_token=salon[0]
        )
        
        keyboard = [[InlineKeyboardButton("🏠 В главное меню", callback_data="owner_main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if success:
            await query.message.reply_text("✅ Ссылка отправлена и закреплена!", reply_markup=reply_markup)
        else:
            await query.message.reply_text("❌ Не удалось отправить ссылку. Попробуйте позже.", reply_markup=reply_markup)
    else:
        await query.edit_message_text("❌ Ошибка: салон не найден")
async def owner_manage_masters_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню управления мастерами"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM masters WHERE salon_id = ? AND is_active = 1', (salon_id,))
    active_masters = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM masters WHERE salon_id = ? AND is_active = 0', (salon_id,))
    inactive_masters = cursor.fetchone()[0]
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить мастера", callback_data="owner_add_master")],
        [InlineKeyboardButton("📋 Список мастеров", callback_data="owner_list_masters")],
        [InlineKeyboardButton("🔧 Специализации", callback_data="owner_manage_specializations")],
        [InlineKeyboardButton("🔄 Активность мастеров", callback_data="owner_toggle_master")],
        [InlineKeyboardButton("🗑️ Удалить мастера", callback_data="owner_delete_master")],
        [InlineKeyboardButton("🔙 Назад", callback_data="owner_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"👨‍💼 **Управление мастерами**\n🏪 Салон: {salon_name}\n\n"
        f"📊 Статистика:\n"
        f"• Активных мастеров: {active_masters}\n"
        f"• Неактивных мастеров: {inactive_masters}\n"
        f"• Всего: {active_masters + inactive_masters}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )
async def owner_list_masters_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список мастеров с навигацией"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT m.id, m.name, m.specialization, m.is_active, 
               COUNT(ms.service_id) as services_count
        FROM masters m
        LEFT JOIN master_services ms ON m.id = ms.master_id
        WHERE m.salon_id = ?
        GROUP BY m.id
        ORDER BY m.is_active DESC, m.name
    ''', (salon_id,))
    
    masters = cursor.fetchall()
    conn.close()
    
    if not masters:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="owner_manage_masters")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"👨‍💼 **Мастера салона {salon_name}**\n\n"
            "❌ Мастера пока не добавлены",
            reply_markup=reply_markup
        )
        return
    
    masters_text = f"👨‍💼 **Мастера салона {salon_name}**\n\n"
    
    active_masters = [m for m in masters if m[3]]
    inactive_masters = [m for m in masters if not m[3]]
    
    if active_masters:
        masters_text += "✅ **Активные мастера:**\n"
        for master in active_masters:
            status_icon = "🟢" if master[3] else "🔴"
            services_info = f"({master[4]} услуг)" if master[4] > 0 else "(нет услуг)"
            masters_text += f"{status_icon} {master[1]} - {master[2]} {services_info}\n"
        masters_text += "\n"
    
    if inactive_masters:
        masters_text += "❌ **Неактивные мастера:**\n"
        for master in inactive_masters:
            services_info = f"({master[4]} услуг)" if master[4] > 0 else "(нет услуг)"
            masters_text += f"🔴 {master[1]} - {master[2]} {services_info}\n"
    
    # Статистика
    total_masters = len(masters)
    active_count = len(active_masters)
    inactive_count = len(inactive_masters)
    
    stats_text = f"\n📊 **Статистика:** {total_masters} мастеров ({active_count} активных, {inactive_count} неактивных)"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить список", callback_data="owner_list_masters")],
        [InlineKeyboardButton("🔙 Назад", callback_data="owner_manage_masters")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        masters_text + stats_text,
        reply_markup=reply_markup
    )
async def owner_manage_masters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('owner_authenticated'):
        await update.message.reply_text("❌ Сначала войдите в систему: /login")
        return
    
    query = update.callback_query
    await query.answer()
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM masters WHERE salon_id = ? AND is_active = 1', (salon_id,))
    active_masters = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM masters WHERE salon_id = ? AND is_active = 0', (salon_id,))
    inactive_masters = cursor.fetchone()[0]
    conn.close()
    
    # 🔧 ОБНОВЛЕННОЕ МЕНЮ С НОВЫМИ ФУНКЦИЯМИ
    keyboard = [
        [InlineKeyboardButton("➕ Добавить мастера", callback_data="owner_add_master")],
        [InlineKeyboardButton("📋 Список мастеров", callback_data="owner_list_masters")],
        [InlineKeyboardButton("🔧 Управление специализациями", callback_data="owner_manage_specializations")],
        [InlineKeyboardButton("🔄 Активировать/Деактивировать", callback_data="owner_toggle_master")],  # 🔧 НОВАЯ КНОПКА
        [InlineKeyboardButton("🗑️ Удалить мастера", callback_data="owner_delete_master")],  # 🔧 НОВАЯ КНОПКА
        [InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"👨‍💼 **Управление мастерами**\n🏪 Салон: {salon_name}\n\n"
        f"📊 Статистика:\n"
        f"• Активных мастеров: {active_masters}\n"
        f"• Неактивных мастеров: {inactive_masters}\n"
        f"• Всего: {active_masters + inactive_masters}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )
async def owner_manage_specializations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление специализациями мастеров"""
    query = update.callback_query
    await query.answer()
    
    salon_id = context.user_data.get('current_salon_id')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Получаем список мастеров
    cursor.execute('SELECT id, name, specialization FROM masters WHERE salon_id = ? AND is_active = 1', (salon_id,))
    masters = cursor.fetchall()
    
    # Получаем список услуг
    cursor.execute('SELECT id, name FROM services WHERE salon_id = ? AND is_active = 1', (salon_id,))
    services = cursor.fetchall()
    
    conn.close()
    
    if not masters or not services:
        await query.edit_message_text(
            "❌ **Недостаточно данных**\n\n"
            "Для настройки специализаций нужно:\n"
            "• Добавить мастеров\n• Добавить услуги\n\n"
            "Вернитесь, когда добавите необходимые данные."
        )
        return
    
    keyboard = []
    for master in masters:
        button_text = f"👨‍💼 {master[1]} ({master[2]})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"edit_specializations_{master[0]}")])
    
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🔧 **Управление специализациями мастеров**\n\n"
        "Выберите мастера для настройки доступных услуг:",
        reply_markup=reply_markup
    )
async def owner_add_master_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания мастера с одним сообщением"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    message = await query.edit_message_text(
        "👨‍💼 **Добавление нового мастера**\n\n"
        "Введите имя мастера:"
    )
    
    context.user_data['master_message_id'] = message.message_id
    context.user_data['master_chat_id'] = message.chat_id
    context.user_data['waiting_for_master_name'] = True
async def handle_master_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода имени мастера с редактированием"""
    if not context.user_data.get('waiting_for_master_name'):
        return
    
    try:
        master_name = update.message.text.strip()
        
        if not master_name:
            await context.bot.edit_message_text(
                chat_id=context.user_data.get('master_chat_id'),
                message_id=context.user_data.get('master_message_id'),
                text="❌ **Имя не может быть пустым!**\n\n"
                     "Введите имя мастера:"
            )
            return
        
        context.user_data['new_master_name'] = master_name
        context.user_data['waiting_for_master_name'] = False
        context.user_data['waiting_for_master_specialization'] = True
        
        await context.bot.edit_message_text(
            chat_id=context.user_data.get('master_chat_id'),
            message_id=context.user_data.get('master_message_id'),
            text=f"👨‍💼 **Имя мастера:** {master_name}\n\n"
                 f"🎯 Введите специализацию мастера:\n\n"
                 f"💡 Например: Парикмахер, Барбер, Маникюр"
        )
        
        try:
            await update.message.delete()
        except:
            pass
        
    except Exception as e:
        print(f"❌ Ошибка при вводе имени мастера: {e}")
async def handle_master_specialization_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода специализации мастера с редактированием"""
    if not context.user_data.get('waiting_for_master_specialization'):
        return
    
    try:
        specialization = update.message.text.strip()
        master_name = context.user_data.get('new_master_name')
        
        if not specialization:
            await context.bot.edit_message_text(
                chat_id=context.user_data.get('master_chat_id'),
                message_id=context.user_data.get('master_message_id'),
                text=f"👨‍💼 **Имя мастера:** {master_name}\n\n"
                     f"❌ **Специализация не может быть пустой!**\n\n"
                     f"🎯 Введите специализацию мастера:"
            )
            return
        
        # 🔧 СОЗДАЕМ МАСТЕРА В БАЗЕ ДАННЫХ
        salon_id = context.user_data.get('current_salon_id')
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO masters (salon_id, name, specialization, is_active)
            VALUES (?, ?, ?, 1)
        ''', (salon_id, master_name, specialization))
        
        master_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # 🔧 РЕДАКТИРУЕМ СООБЩЕНИЕ С УСПЕШНЫМ СОЗДАНИЕМ
        keyboard = [
            [InlineKeyboardButton("👨‍💼 К управлению мастерами", callback_data="owner_manage_masters")],
            [InlineKeyboardButton("➕ Добавить еще мастера", callback_data="owner_add_master")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.edit_message_text(
            chat_id=context.user_data.get('master_chat_id'),
            message_id=context.user_data.get('master_message_id'),
            text=f"✅ **Мастер успешно добавлен!**\n\n"
                 f"👨‍💼 **Имя:** {master_name}\n"
                 f"🎯 **Специализация:** {specialization}\n"
                 f"🆔 **ID мастера:** {master_id}",
            reply_markup=reply_markup
        )
        
        try:
            await update.message.delete()
        except:
            pass
        
        # 🔧 ОЧИЩАЕМ КОНТЕКСТ
        context.user_data.pop('new_master_name', None)
        context.user_data.pop('master_message_id', None)
        context.user_data.pop('master_chat_id', None)
        
    except Exception as e:
        print(f"❌ Ошибка при создании мастера: {e}")
        await context.bot.edit_message_text(
            chat_id=context.user_data.get('master_chat_id'),
            message_id=context.user_data.get('master_message_id'),
            text="❌ Ошибка при создании мастера. Попробуйте еще раз."
        )
        context.user_data.clear()
async def owner_delete_master_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик удаления мастера"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему: /login")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Получаем всех мастеров салона
    cursor.execute('''
        SELECT m.id, m.name, m.specialization, m.is_active,
               COUNT(ms.service_id) as services_count
        FROM masters m
        LEFT JOIN master_services ms ON m.id = ms.master_id
        WHERE m.salon_id = ?
        GROUP BY m.id
        ORDER BY m.is_active DESC, m.name
    ''', (salon_id,))
    
    masters = cursor.fetchall()
    conn.close()
    
    if not masters:
        await query.edit_message_text(
            f"👨‍💼 **Управление мастерами**\n🏪 {salon_name}\n\n"
            "❌ Мастера пока не добавлены\n\n"
            "Добавьте первого мастера, чтобы начать работу!"
        )
        return
    
    keyboard = []
    for master in masters:
        master_id, master_name, specialization, is_active, services_count = master
        status_icon = "🟢" if is_active else "🔴"
        services_info = f"({services_count} услуг)" if services_count > 0 else ""
        button_text = f"{status_icon} {master_name} - {specialization} {services_info}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"select_master_delete_{master_id}")])
    
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")])
    keyboard.append([InlineKeyboardButton("« Назад к мастерам", callback_data="owner_manage_masters")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🗑️ **Удаление мастера**\n🏪 {salon_name}\n\n"
        f"Выберите мастера для удаления:\n\n"
        f"🟢 - Активный мастер\n"
        f"🔴 - Неактивный мастер\n\n"
        f"⚠️ <b>Внимание:</b> Удаление мастера также удалит все его связи с услугами!",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
async def handle_master_delete_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора мастера для удаления"""
    query = update.callback_query
    await query.answer()
    
    master_id = query.data.split('_')[3]
    context.user_data['deleting_master_id'] = master_id
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Получаем информацию о мастере
    cursor.execute('''
        SELECT m.name, m.specialization, m.is_active,
               COUNT(ms.service_id) as services_count,
               COUNT(b.id) as active_bookings
        FROM masters m
        LEFT JOIN master_services ms ON m.id = ms.master_id
        LEFT JOIN bookings b ON m.id = b.master_id AND b.status = 'confirmed'
        WHERE m.id = ?
        GROUP BY m.id
    ''', (master_id,))
    
    master_info = cursor.fetchone()
    conn.close()
    
    if not master_info:
        await query.edit_message_text("❌ Мастер не найден")
        return
    
    master_name, specialization, is_active, services_count, active_bookings = master_info
    status_text = "Активен 🟢" if is_active else "Неактивен 🔴"
    
    # Проверяем, есть ли активные записи
    if active_bookings > 0:
        keyboard = [
            [InlineKeyboardButton("« Назад к выбору", callback_data="owner_delete_master")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"❌ **Невозможно удалить мастера!**\n\n"
            f"👨‍💼 Мастер: {master_name}\n"
            f"🎯 Специализация: {specialization}\n"
            f"📊 Статус: {status_text}\n\n"
            f"⚠️ <b>У мастера есть активные записи:</b> {active_bookings}\n\n"
            f"Сначала нужно:\n"
            f"• Переназначить или отменить активные записи\n"
            f"• Или деактивировать мастера\n\n"
            f"💡 <i>Деактивированный мастер останется в системе, но не будет доступен для новых записей</i>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        return
    
    # Показываем подтверждение удаления
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_master_{master_id}"),
            InlineKeyboardButton("❌ Нет, отменить", callback_data="owner_delete_master")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🗑️ **Подтверждение удаления мастера**\n\n"
        f"Вы действительно хотите удалить мастера?\n\n"
        f"👨‍💼 Имя: {master_name}\n"
        f"🎯 Специализация: {specialization}\n"
        f"📊 Статус: {status_text}\n"
        f"🔗 Связанных услуг: {services_count}\n\n"
        f"⚠️ <b>Это действие нельзя отменить!</b>\n"
        f"• Мастер будет полностью удален из системы\n"
        f"• Все связи с услугами будут удалены\n"
        f"• Данные будут утеряны безвозвратно",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
async def handle_confirm_master_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик подтверждения удаления мастера с инлайн-кнопками"""
    query = update.callback_query
    await query.answer()
    
    master_id = query.data.split('_')[3]
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    try:
        # Получаем информацию о мастере для сообщения
        cursor.execute('SELECT name, specialization FROM masters WHERE id = ?', (master_id,))
        master_info = cursor.fetchone()
        
        if not master_info:
            await query.edit_message_text("❌ Мастер не найден")
            conn.close()
            return
        
        master_name, specialization = master_info
        
        # Удаляем связи мастера с услугами
        cursor.execute('DELETE FROM master_services WHERE master_id = ?', (master_id,))
        
        # Удаляем мастера
        cursor.execute('DELETE FROM masters WHERE id = ?', (master_id,))
        
        conn.commit()
        conn.close()
        
        # 🔧 СОЗДАЕМ ИНЛАЙН-КЛАВИАТУРУ
        keyboard = [
            [InlineKeyboardButton("👨‍💼 К управлению мастерами", callback_data="owner_manage_masters")],
            [InlineKeyboardButton("📋 Список мастеров", callback_data="owner_list_masters")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ **Мастер успешно удален!**\n\n"
            f"👨‍💼 Имя: {master_name}\n"
            f"🎯 Специализация: {specialization}\n\n"
            f"💫 Все данные мастера были удалены из системы.",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        conn.rollback()
        conn.close()
        await query.edit_message_text(f"❌ Ошибка при удалении мастера: {e}")
async def owner_toggle_master_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик активации/деактивации мастера"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему: /login")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Получаем всех мастеров салона
    cursor.execute('''
        SELECT m.id, m.name, m.specialization, m.is_active,
               COUNT(ms.service_id) as services_count
        FROM masters m
        LEFT JOIN master_services ms ON m.id = ms.master_id
        WHERE m.salon_id = ?
        GROUP BY m.id
        ORDER BY m.is_active DESC, m.name
    ''', (salon_id,))
    
    masters = cursor.fetchall()
    conn.close()
    
    if not masters:
        await query.edit_message_text(
            f"👨‍💼 **Управление мастерами**\n🏪 {salon_name}\n\n"
            "❌ Мастера пока не добавлены"
        )
        return
    
    keyboard = []
    for master in masters:
        master_id, master_name, specialization, is_active, services_count = master
        status_icon = "🟢" if is_active else "🔴"
        services_info = f"({services_count} услуг)" if services_count > 0 else ""
        button_text = f"{status_icon} {master_name} - {specialization} {services_info}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"select_master_toggle_{master_id}")])
    
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")])
    keyboard.append([InlineKeyboardButton("« Назад к мастерам", callback_data="owner_manage_masters")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🔄 **Активация/Деактивация мастера**\n🏪 {salon_name}\n\n"
        f"Выберите мастера для изменения статуса:\n\n"
        f"🟢 - Активный мастер (доступен для записи)\n"
        f"🔴 - Неактивный мастер (недоступен для записи)\n\n"
        f"💡 <i>Деактивированные мастера остаются в системе, но клиенты не могут на них записываться</i>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
async def handle_master_toggle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик изменения статуса мастера с инлайн-кнопками"""
    query = update.callback_query
    await query.answer()
    
    master_id = query.data.split('_')[3]
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Получаем текущий статус мастера
    cursor.execute('SELECT name, specialization, is_active FROM masters WHERE id = ?', (master_id,))
    master_info = cursor.fetchone()
    
    if not master_info:
        await query.edit_message_text("❌ Мастер не найден")
        conn.close()
        return
    
    master_name, specialization, current_status = master_info
    new_status = not current_status
    
    # Обновляем статус мастера
    cursor.execute('UPDATE masters SET is_active = ? WHERE id = ?', (new_status, master_id))
    conn.commit()
    conn.close()
    
    status_text = "активирован" if new_status else "деактивирован"
    status_emoji = "🟢" if new_status else "🔴"
    
    # 🔧 СОЗДАЕМ ИНЛАЙН-КЛАВИАТУРУ
    keyboard = [
        [InlineKeyboardButton("👨‍💼 К управлению мастерами", callback_data="owner_manage_masters")],
        [InlineKeyboardButton("📋 Список мастеров", callback_data="owner_list_masters")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="owner_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✅ **Мастер {status_text}!**\n\n"
        f"{status_emoji} Мастер: {master_name}\n"
        f"🎯 Специализация: {specialization}\n"
        f"📊 Новый статус: {'Активен' if new_status else 'Неактивен'}\n\n"
        f"💡 Мастер {'теперь доступен' if new_status else 'больше не доступен'} для записи клиентов",
        reply_markup=reply_markup
    )
async def show_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает FAQ для пользователей"""
    faq_text = (
        "❓ <b>Часто задаваемые вопросы</b>\n\n"
        
        "🏪 <b>Для клиентов:</b>\n"
        "• <b>Как записаться?</b> - Используйте уникальную ссылку салона или команду /book\n"
        "• <b>Где найти ссылку салона?</b> - Спросите у администратора салона\n"
        "• <b>Как отменить запись?</b> - Используйте /mybookings для просмотра записей и /cancelbooking для отмены\n"
        "• <b>Приходят ли напоминания?</b> - Да, за 30 минут до записи\n\n"
        
        "💼 <b>Для владельцев салонов:</b>\n"
        "• <b>Как войти в систему?</b> - Используйте /login с вашими данными\n"
        "• <b>Как добавить мастера?</b> - Войдите и используйте раздел 'Мастера'\n"
        "• <b>Как настроить услуги?</b> - Войдите и используйте раздел 'Услуги'\n"
        "• <b>Как изменить время работы?</b> - Войдите и используйте /settings\n\n"
        
        "🔧 <b>Общие вопросы:</b>\n"
        "• <b>Технические проблемы?</b> - Обратитесь к администратору системы\n"
        "• <b>Не приходят уведомления?</b> - Проверьте настройки уведомлений в Telegram\n"
        "• <b>Забыли данные для входа?</b> - Обратитесь к оператору системы\n\n"
        
        "📞 <b>Поддержка:</b>\n"
        "По всем вопросам обращайтесь к администратору вашего салона"
    )
    
    # Создаем клавиатуру с кнопкой "Назад"
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="faq_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(faq_text, reply_markup=reply_markup, parse_mode='HTML')
async def handle_faq_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки FAQ"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "faq_back":
        # Возвращаемся к предыдущему меню в зависимости от роли пользователя
        user_id = query.from_user.id
        
        if is_operator(user_id):
            # Для оператора показываем панель оператора
            keyboard = [
                [InlineKeyboardButton("👑 Панель оператора", callback_data="operator_panel_main")],
                [InlineKeyboardButton("🔐 Войти как владелец", callback_data="owner_login_start")],
                [InlineKeyboardButton("🔗 Все ссылки салонов", callback_data="operator_all_links")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "👑 **Панель оператора**\n\n"
                "Выберите действие:",
                reply_markup=reply_markup
            )
        elif context.user_data.get('owner_authenticated'):
            # Для владельца показываем главное меню
            salon_name = context.user_data.get('current_salon_name', 'ваш салон')
            
            keyboard = [
                [InlineKeyboardButton("📋 Записи", callback_data="owner_bookings")],
                [InlineKeyboardButton("👨‍💼 Управление мастерами", callback_data="owner_manage_masters")],
                [InlineKeyboardButton("💅 Управление услугами", callback_data="owner_manage_services")],
                [InlineKeyboardButton("⚙️ Настройки салона", callback_data="owner_salon_settings")],
                [InlineKeyboardButton("📊 Статистика", callback_data="owner_stats")],
                [InlineKeyboardButton("🚪 Выйти из системы", callback_data="owner_logout_handler")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"🏪 **Панель управления {salon_name}**\n\nВыберите раздел:",
                reply_markup=reply_markup
            )
        else:
            # 🔧 ИСПРАВЛЕНИЕ: СТРОГО ПРОВЕРЯЕМ, ЧТО ПОЛЬЗОВАТЕЛЬ ДЕЙСТВИТЕЛЬНО В САЛОНЕ
            user = query.from_user
            
            # 🔒 СТРОГАЯ ПРОВЕРКА: ЕСТЬ ЛИ ДЕЙСТВИТЕЛЬНО САЛОН В КОНТЕКСТЕ
            salon_id = context.user_data.get('current_salon_id')
            salon_name = context.user_data.get('current_salon_name')
            
            if salon_id and salon_name:
                # Пользователь действительно в салоне - показываем меню салона
                keyboard = [
                    [InlineKeyboardButton("💅 Записаться на услугу", callback_data="book_service_main")],
                    [InlineKeyboardButton("👨‍💼 Наши мастера", callback_data="show_masters_main")],
                    [InlineKeyboardButton("💎 Наши услуги", callback_data="show_services_main")],
                    [InlineKeyboardButton("📋 Мои записи", callback_data="my_bookings_main")],
                    [InlineKeyboardButton("📚 История записей", callback_data="client_booking_history")],
                    [InlineKeyboardButton("❓ Помощь", callback_data="show_faq")],
                    [InlineKeyboardButton("🔐 Вход для владельцев", callback_data="owner_login_start")],
                    [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu_return")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"🏪 **{salon_name}**\n\n"
                    f"Выберите действие:",
                    reply_markup=reply_markup
                )
            else:
                # 🔧 ЕСЛИ САЛОНА НЕТ - ПОКАЗЫВАЕМ ОБЩЕЕ МЕНЮ БЕЗ ДОСТУПА К ФУНКЦИЯМ САЛОНА
                keyboard = [
                    [InlineKeyboardButton("🔐 Вход для владельцев", callback_data="owner_login_start")],
                    [InlineKeyboardButton("❓ Помощь", callback_data="show_faq")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"Привет {user.first_name}! 🎉\n"
                    f"Добро пожаловать в систему записи!\n\n"
                    f"🔒 **Для доступа к функциям салона:**\n"
                    f"• Используйте уникальную ссылку салона\n\n"
                    f"🏪 **Для владельцев салонов:**\n"
                    f"• Войдите в систему управления\n\n",
                    reply_markup=reply_markup
                )
        return
async def handle_faq_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главный обработчик для FAQ"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "show_faq":
        await show_faq_callback(update, context)
    elif query.data == "book_service_from_faq":
        await book_service_from_faq(update, context)
    elif query.data == "owner_login_from_faq":
        await owner_login_from_faq(update, context)
async def show_faq_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает FAQ через callback"""
    query = update.callback_query
    await query.answer()
    
    faq_text = (
        "❓ <b>Часто задаваемые вопросы</b>\n\n"
        
        "🏪 <b>Для клиентов:</b>\n"
        "• <b>Как записаться?</b> - Используйте уникальную ссылку салона или команду /book\n"
        "• <b>Где найти ссылку салона?</b> - Спросите у администратора салона\n"
        "• <b>Как отменить запись?</b> - Используйте /mybookings для просмотра записей и /cancelbooking для отмены\n"
        "• <b>Приходят ли напоминания?</b> - Да, за 30 минут до записи\n\n"
        
        "💼 <b>Для владельцев салонов:</b>\n"
        "• <b>Как войти в систему?</b> - Используйте /login с вашими данными\n"
        "• <b>Как добавить мастера?</b> - Войдите и используйте раздел 'Мастера'\n"
        "• <b>Как настроить услуги?</b> - Войдите и используйте раздел 'Услуги'\n"
        "• <b>Как изменить время работы?</b> - Войдите и используйте /settings\n\n"
        
        "🔧 <b>Общие вопросы:</b>\n"
        "• <b>Технические проблемы?</b> - Обратитесь к администратору системы\n"
        "• <b>Не приходят уведомления?</b> - Проверьте настройки уведомлений в Telegram\n"
        "• <b>Забыли данные для входа?</b> - Обратитесь к оператору системы\n\n"
        
        "📞 <b>Поддержка:</b>\n"
        "По всем вопросам обращайтесь к администратору вашего салона"
    )
    
    # Создаем клавиатуру с кнопкой "Назад"
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="faq_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(faq_text, reply_markup=reply_markup, parse_mode='HTML')
async def book_service_from_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переход к записи из FAQ"""
    query = update.callback_query
    await query.answer()
    
    # Проверяем, что пользователь находится в салоне
    if not context.user_data.get('current_salon_id'):
        await query.edit_message_text(
            "❌ **Не выбран салон!**\n\n"
            "Пожалуйста, используйте уникальную ссылку салона для записи.\n"
            "Если у вас нет ссылки, обратитесь к администратору салона."
        )
        return
    
    # Показываем сообщение о начале процесса записи
    await query.edit_message_text("🔄 Переходим к процессу записи...")
    
    # 🔧 ВЫЗЫВАЕМ ФУНКЦИЮ ЗАПИСИ ЧЕРЕЗ CALLBACK
    await book_service_callback(update, context)
async def owner_login_from_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переход к входу для владельцев из FAQ"""
    query = update.callback_query
    await query.answer()
    
    # Сбрасываем капчу для владельцев
    context.user_data.pop('waiting_for_captcha', None)
    context.user_data.pop('first_time_user', None)
    context.user_data['captcha_passed'] = True  # Пропускаем капчу для владельцев
    
    context.user_data['waiting_for_owner_login'] = True
    
    await query.edit_message_text("🔐 **Вход для владельцев салонов**\n\nВведите ваш логин:")
async def book_service_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback версия функции записи на услугу"""
    query = update.callback_query
    await query.answer()
    
    # 🔧 ПРОВЕРЯЕМ, ЧТО ПОЛЬЗОВАТЕЛЬ ДЕЙСТВИТЕЛЬНО В КОНКРЕТНОМ САЛОНЕ
    salon_id = context.user_data.get('current_salon_id')
    if not salon_id:
        await query.edit_message_text(
            "❌ **Не выбран салон!**\n\n"
            "Пожалуйста, используйте уникальную ссылку салона для записи.\n"
            "Если у вас нет ссылки, обратитесь к администратору салона."
        )
        return
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM services WHERE salon_id = ? AND is_active = 1', (salon_id,))
    services = cursor.fetchall()
    conn.close()
    
    if not services:
        await query.edit_message_text("❌ Услуги пока не доступны")
        return
    
    salon_name = context.user_data.get('current_salon_name', 'салон')
    
    keyboard = [[InlineKeyboardButton(service[1], callback_data=f"service_{service[0]}")] for service in services]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"💅 **Выберите услугу в {salon_name}:**",
        reply_markup=reply_markup
    )
async def show_masters_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback версия показа мастеров"""
    # 🔧 ОПРЕДЕЛЯЕМ ТИП ОТПРАВКИ СООБЩЕНИЯ
    if hasattr(update, 'callback_query') and update.callback_query:
        query = update.callback_query
        message_func = query.edit_message_text
        await query.answer()
    else:
        message_func = update.message.reply_text
    
    # Если пользователь авторизован как владелец, показываем расширенную информацию
    if context.user_data.get('owner_authenticated'):
        salon_id = context.user_data.get('current_salon_id')
        salon_name = context.user_data.get('current_salon_name', 'ваш салон')
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        cursor.execute('SELECT name, specialization FROM masters WHERE salon_id = ? AND is_active = 1', (salon_id,))
        masters = cursor.fetchall()
        conn.close()
        
        if masters:
            masters_text = f"👨‍💼 Мастера {salon_name}:\n\n"
            for master in masters:
                masters_text += f"• {master[0]} - {master[1]}\n"
            
            # Добавляем кнопки для владельцев
            keyboard = [[InlineKeyboardButton("⚙️ Управление мастерами", callback_data="owner_manage_masters")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message_func(masters_text, reply_markup=reply_markup)
        else:
            await message_func("Мастера пока не добавлены")
    else:
        # Обычный показ для клиентов
        salon_id = context.user_data.get('current_salon_id', 1)
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        cursor.execute('SELECT name, specialization FROM masters WHERE salon_id = ? AND is_active = 1', (salon_id,))
        masters = cursor.fetchall()
        conn.close()
        
        salon_name = context.user_data.get('current_salon_name', 'Тестовый салон красоты')
        
        if masters:
            masters_text = f"👨‍💼 Мастера {salon_name}:\n\n"
            for master in masters:
                masters_text += f"• {master[0]} - {master[1]}\n"
            
            # 🔧 ДОБАВЛЯЕМ КНОПКУ НАЗАД ДЛЯ КЛИЕНТОВ
            keyboard = [
                [InlineKeyboardButton("💅 Записаться на услугу", callback_data="book_service_main")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="client_main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message_func(masters_text, reply_markup=reply_markup)
        else:
            await message_func("Мастера пока не добавлены")
async def show_services_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback версия показа услуг"""
    # 🔧 ОПРЕДЕЛЯЕМ ТИП ОТПРАВКИ СООБЩЕНИЯ
    if hasattr(update, 'callback_query') and update.callback_query:
        query = update.callback_query
        message_func = query.edit_message_text
        await query.answer()
    else:
        message_func = update.message.reply_text
    
    salon_id = context.user_data.get('current_salon_id', 1)
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name, price, duration, is_range_price FROM services WHERE salon_id = ? AND is_active = 1', (salon_id,))
    services = cursor.fetchall()
    conn.close()
    
    salon_name = context.user_data.get('current_salon_name', 'Тестовый салон красоты')
    
    if services:
        services_text = f"💅 Услуги {salon_name}:\n\n"
        for service in services:
            name, price, duration, is_range_price = service
            if is_range_price:
                # Диапазон цен
                price_text = f"{price} руб."
            else:
                # Фиксированная цена
                price_text = f"{price} руб."
            services_text += f"• {name} - {price_text} ({duration} мин.)\n"
        
        # 🔧 ДОБАВЛЯЕМ КНОПКУ НАЗАД ДЛЯ КЛИЕНТОВ
        keyboard = [
            [InlineKeyboardButton("💅 Записаться на услугу", callback_data="book_service_main")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="client_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message_func(services_text, reply_markup=reply_markup)
    else:
        await message_func("Услуги пока не добавлены")
# ==================== УПРАВЛЕНИЕ УСЛУГАМИ ====================
async def owner_today_bookings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает записи на сегодня"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT b.id, b.booking_date, s.name as service_name, 
               m.name as master_name, b.client_name, b.client_phone,
               b.status, b.confirmed
        FROM bookings b
        JOIN services s ON b.service_id = s.id
        JOIN masters m ON b.master_id = m.id
        WHERE b.salon_id = ? AND b.status = 'confirmed'
        AND DATE(b.booking_date) = DATE('now')
        ORDER BY b.booking_date ASC
    ''', (salon_id,))
    
    bookings = cursor.fetchall()
    conn.close()
    
    if not bookings:
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к записям", callback_data="owner_bookings")],
            [InlineKeyboardButton("📋 Все записи", callback_data="owner_all_bookings")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📅 **Записи на сегодня**\n🏪 {salon_name}\n\n"
            "✅ На сегодня записей нет",
            reply_markup=reply_markup
        )
        return
    
    today_text = f"📅 **Записи на сегодня**\n🏪 {salon_name}\n\n"
    
    for booking in bookings:
        booking_id, booking_date, service_name, master_name, client_name, client_phone, status, confirmed = booking
        
        try:
            if isinstance(booking_date, str):
                booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
            else:
                booking_datetime = booking_date
            
            formatted_time = booking_datetime.strftime('%H:%M')
            status_icon = "✅" if confirmed else "⏳"
            
        except Exception as e:
            formatted_time = "время не определено"
            status_icon = "⏳"
        
        today_text += (
            f"{status_icon} **{formatted_time}** - {client_name}\n"
            f"   💅 {service_name} | 👨‍💼 {master_name}\n"
            f"   📞 {client_phone}\n"
            f"   {'✅ Подтверждена' if confirmed else '⏳ Ожидает'}\n\n"
        )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад к записям", callback_data="owner_bookings")],
        [InlineKeyboardButton("📋 Все записи", callback_data="owner_all_bookings")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(today_text, reply_markup=reply_markup)
async def handle_owner_booking_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик навигации по записям для владельца"""
    query = update.callback_query
    
    try:
        await query.answer()
        
        data = query.data
        print(f"🔍 Owner booking navigation: {data}")
        
        # Парсим номер страницы
        if data.startswith('owner_prev_'):
            parts = data.split('_')
            page_number = int(parts[2])
        elif data.startswith('owner_next_'):
            parts = data.split('_')
            page_number = int(parts[2])
        else:
            await query.edit_message_text("❌ Неизвестная команда навигации")
            return
        
        # Проверяем, есть ли записи в контексте
        if 'owner_bookings' not in context.user_data:
            keyboard = [
                [InlineKeyboardButton("🔙 Назад к записям", callback_data="owner_bookings")],
                [InlineKeyboardButton("📋 Все записи", callback_data="owner_all_bookings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "❌ Данные записей устарели. Используйте кнопку ниже для обновления",
                reply_markup=reply_markup
            )
            return
        
        bookings = context.user_data['owner_bookings']
        
        # Проверяем валидность номера страницы
        if page_number < 0:
            page_number = 0
        if page_number >= len(bookings):
            page_number = len(bookings) - 1
        
        await show_owner_booking_page(update, context, page_number)
        
    except Exception as e:
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к записям", callback_data="owner_bookings")],
            [InlineKeyboardButton("📋 Все записи", callback_data="owner_all_bookings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text("❌ Ошибка при навигации", reply_markup=reply_markup)
        logger.error(f"Error in handle_owner_booking_navigation: {e}")
async def show_owner_booking_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page_number):
    """Показывает одну запись на странице для владельца"""
    bookings = context.user_data.get('owner_bookings', [])
    
    if not bookings:
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к записям", callback_data="owner_bookings")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text("❌ Записи не найдены", reply_markup=reply_markup)
        else:
            await update.message.reply_text("❌ Записи не найдены", reply_markup=reply_markup)
        return
    
    # Проверяем валидность номера страницы
    if page_number < 0:
        page_number = 0
    if page_number >= len(bookings):
        page_number = len(bookings) - 1
    
    # Сохраняем текущую страницу в контексте
    context.user_data['current_owner_booking_page'] = page_number
    
    # Получаем запись для текущей страницы
    booking = bookings[page_number]
    booking_id, booking_date, service_name, master_name, client_name, client_phone, status, confirmed, created_at = booking
    
    # 🔧 ОБРАБАТЫВАЕМ ДАТУ
    try:
        if isinstance(booking_date, str):
            booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
        else:
            booking_datetime = booking_date
        
        formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
        time_until = (booking_datetime - datetime.now()).total_seconds() / 3600  # часов до записи
        
    except Exception as e:
        formatted_date = "дата не определена"
        time_until = 999
    
    # Формируем текст записи
    status_icon = "✅" if confirmed else "⏳"
    status_text = "Подтверждена клиентом" if confirmed else "Ожидает подтверждения"
    status_color = "🟢" if confirmed else "🟡"
    
    booking_text = (
        f"📋 **Запись #{booking_id}** {status_color}\n\n"
        f"👤 **Клиент:** {client_name}\n"
        f"📞 **Телефон:** `{client_phone}`\n"
        f"💅 **Услуга:** {service_name}\n"
        f"👨‍💼 **Мастер:** {master_name}\n"
        f"📅 **Дата и время:** {formatted_date}\n"
        f"📊 **Статус записи:** {status}\n"
        f"✅ **Подтверждение:** {status_text}\n"
        f"📄 **Страница:** {page_number + 1} из {len(bookings)}\n"
    )
    
    # 🔧 ИНФОРМАЦИЯ О ВРЕМЕНИ ДО ЗАПИСИ
    if time_until > 0:
        if time_until < 1:
            time_info = "⏰ Менее чем через 1 час"
        elif time_until < 2:
            time_info = f"⏰ Через {int(time_until)} час"
        elif time_until < 5:
            time_info = f"⏰ Через {int(time_until)} часа"
        else:
            time_info = f"⏰ Через {int(time_until)} часов"
        booking_text += f"\n{time_info}\n"
    
    # Создаем клавиатуру
    keyboard = []
    
    # Кнопки действий с записью
    if not confirmed and time_until > 0:
        keyboard.append([InlineKeyboardButton("📞 Напомнить клиенту", callback_data=f"remind_booking_{booking_id}")])
    
    # Кнопки навигации
    nav_buttons = []
    
    if page_number > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"owner_prev_{page_number-1}"))
    
    if page_number < len(bookings) - 1:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"owner_next_{page_number+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # 🔧 ДОБАВЛЯЕМ КНОПКИ ОБНОВЛЕНИЯ И НАЗАД
    keyboard.append([InlineKeyboardButton("🔄 Обновить список", callback_data="owner_all_bookings")])
    keyboard.append([InlineKeyboardButton("🔙 Назад к записям", callback_data="owner_bookings")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # 🔧 ОПРЕДЕЛЯЕМ ТИП ОТПРАВКИ СООБЩЕНИЯ
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(
            booking_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    elif hasattr(update, 'message') and update.message:
        await update.message.reply_text(
            booking_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
async def owner_all_bookings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает все активные записи салона"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT b.id, b.booking_date, s.name as service_name, 
               m.name as master_name, b.client_name, b.client_phone,
               b.status, b.confirmed, b.created_at
        FROM bookings b
        JOIN services s ON b.service_id = s.id
        JOIN masters m ON b.master_id = m.id
        WHERE b.salon_id = ? AND b.status = 'confirmed'
        ORDER BY b.booking_date ASC
    ''', (salon_id,))
    
    bookings = cursor.fetchall()
    conn.close()
    
    if not bookings:
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к записям", callback_data="owner_bookings")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📋 **Активные записи**\n🏪 {salon_name}\n\n"
            "❌ Активных записей пока нет",
            reply_markup=reply_markup
        )
        return
    
    # Сохраняем записи в контексте для постраничного просмотра
    context.user_data['owner_bookings'] = bookings
    context.user_data['current_owner_booking_page'] = 0
    
    await show_owner_booking_page(update, context, 0)
async def owner_bookings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню управления записями для владельца"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    # Получаем статистику записей
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Общая статистика
    cursor.execute('SELECT COUNT(*) FROM bookings WHERE salon_id = ?', (salon_id,))
    total_bookings = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM bookings WHERE salon_id = ? AND status = "confirmed"', (salon_id,))
    confirmed_bookings = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM bookings WHERE salon_id = ? AND confirmed = 1', (salon_id,))
    client_confirmed = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM bookings WHERE salon_id = ? AND status = "cancelled"', (salon_id,))
    cancelled_bookings = cursor.fetchone()[0]
    
    # Ожидают подтверждения
    cursor.execute('''
        SELECT COUNT(*) FROM bookings 
        WHERE salon_id = ? AND status = 'confirmed' AND confirmed = 0
        AND booking_date > datetime('now')
    ''', (salon_id,))
    pending_confirmation = cursor.fetchone()[0]
    
    # Сегодняшние записи
    cursor.execute('''
        SELECT COUNT(*) FROM bookings 
        WHERE salon_id = ? AND status = 'confirmed' 
        AND DATE(booking_date) = DATE('now')
    ''', (salon_id,))
    today_bookings = cursor.fetchone()[0]
    
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("📋 Все активные записи", callback_data="owner_all_bookings")],
        [InlineKeyboardButton("📅 Записи на сегодня", callback_data="owner_today_bookings")],
        [InlineKeyboardButton("⏳ Ожидают подтверждения", callback_data="owner_pending_bookings")],
        [InlineKeyboardButton("✅ Подтвержденные записи", callback_data="owner_confirmed_bookings")],
        # 🔧 УДАЛЕНА КНОПКА ПОИСКА
        [InlineKeyboardButton("🔙 Назад", callback_data="owner_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    stats_text = (
        f"📊 **Статистика записей**\n🏪 Салон: {salon_name}\n\n"
        f"• Всего записей: {total_bookings}\n"
        f"• Активных записей: {confirmed_bookings}\n"
        f"• Подтвержденных клиентом: {client_confirmed}\n"
        f"• Ожидают подтверждения: {pending_confirmation}\n"
        f"• Отмененных записей: {cancelled_bookings}\n"
        f"• Записей на сегодня: {today_bookings}\n\n"
        f"Выберите раздел для просмотра:"
    )
    
    await query.edit_message_text(stats_text, reply_markup=reply_markup)
async def handle_cancel_service_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик отмены создания услуги"""
    query = update.callback_query
    await query.answer()
    
    # 🔧 ПОЛНАЯ ОЧИСТКА КОНТЕКСТА ПРОЦЕССА СОЗДАНИЯ УСЛУГИ
    keys_to_remove = [
        'waiting_for_service_name', 'waiting_for_service_price', 'waiting_for_service_duration',
        'waiting_for_approximate_price', 'new_service_name', 'new_service_price', 
        'new_service_duration', 'selected_masters', 'price_is_range'
    ]
    
    for key in keys_to_remove:
        context.user_data.pop(key, None)
    
    # 🔧 СОЗДАЕМ КЛАВИАТУРУ ДЛЯ ВОЗВРАТА
    keyboard = [
        [InlineKeyboardButton("💅 К управлению услугами", callback_data="owner_manage_services")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="owner_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "❌ **Создание услуги отменено**\n\n"
        "Все введенные данные были удалены.\n"
        "Вы можете начать заново в любое время.",
        reply_markup=reply_markup
    )
async def handle_booking_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик подтверждения записи клиентом"""
    query = update.callback_query
    await query.answer()
    
    try:
        booking_id = int(query.data.split('_')[2])
        user_id = query.from_user.id
        
        print(f"🔍 Подтверждение записи {booking_id} от пользователя {user_id}")
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Проверяем, что запись существует и принадлежит пользователю
        cursor.execute('''
            SELECT b.id, b.client_name, b.booking_date, s.name, m.name, sl.name, sl.telegram_chat_id, b.confirmed
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            JOIN salons sl ON b.salon_id = sl.id
            WHERE b.id = ? AND b.user_id = ?
        ''', (booking_id, user_id))
        
        booking = cursor.fetchone()
        
        if not booking:
            await query.edit_message_text("❌ Запись не найдена или у вас нет прав для ее подтверждения")
            conn.close()
            return
        
        booking_id, client_name, booking_date, service_name, master_name, salon_name, salon_chat_id, already_confirmed = booking
        
        if already_confirmed:
            await query.edit_message_text("✅ Эта запись уже подтверждена ранее!")
            conn.close()
            return
        
        # 🔧 ПОДТВЕРЖДАЕМ ЗАПИСЬ
        cursor.execute('UPDATE bookings SET confirmed = 1 WHERE id = ?', (booking_id,))
        conn.commit()
        
        # 🔧 ОБРАБАТЫВАЕМ ДАТУ ДЛЯ СООБЩЕНИЯ
        try:
            if isinstance(booking_date, str):
                booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
            else:
                booking_datetime = booking_date
            
            formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
        except:
            formatted_date = "дата не определена"
        
        # 🔧 ОБНОВЛЯЕМ СООБЩЕНИЕ КЛИЕНТУ
        await query.edit_message_text(
            f"✅ **Запись подтверждена!**\n\n"
            f"🏪 Салон: {salon_name}\n"
            f"💅 Услуга: {service_name}\n"
            f"👨‍💼 Мастер: {master_name}\n"
            f"📅 Время: {formatted_date}\n\n"
            f"📍 Спасибо за подтверждение!\n"
            f"⏰ Ждем вас в салоне!",
            parse_mode='HTML'
        )
        
        # 🔧 ОТПРАВЛЯЕМ УВЕДОМЛЕНИЕ САЛОНУ О ПОДТВЕРЖДЕНИИ
        if salon_chat_id:
            try:
                confirmation_text = (
                    f"✅ **ЗАПИСЬ ПОДТВЕРЖДЕНА!**\n\n"
                    f"Клиент подтвердил запись:\n\n"
                    f"👤 Клиент: {client_name}\n"
                    f"💅 Услуга: {service_name}\n"
                    f"👨‍💼 Мастер: {master_name}\n"
                    f"📅 Время: {formatted_date}\n\n"
                    f"🆔 ID записи: {booking_id}"
                )
                
                app = Application.builder().token(BOT_TOKEN).build()
                await app.initialize()
                await app.bot.send_message(chat_id=salon_chat_id, text=confirmation_text)
                await app.shutdown()
                
                print(f"✅ Уведомление о подтверждении отправлено салону {salon_name}")
            except Exception as e:
                print(f"❌ Ошибка отправки уведомления салону: {e}")
        
        conn.close()
        print(f"✅ Запись {booking_id} подтверждена клиентом")
        
    except Exception as e:
        print(f"❌ Ошибка при подтверждении записи: {e}")
        await query.edit_message_text("❌ Ошибка при подтверждении записи. Попробуйте позже.")
async def handle_cancel_booking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия на кнопку отмены записи"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_cancellation":
        await query.edit_message_text("✅ Отмена записи отменена")
        return
    
    if query.data.startswith("cancel_booking_"):
        booking_id = int(query.data.split('_')[2])
        user_id = query.from_user.id
        await process_booking_cancellation_callback(query, context, booking_id, user_id)
    
    elif query.data.startswith("confirm_cancel_"):
        booking_id = int(query.data.split('_')[2])
        await execute_booking_cancellation(query, context, booking_id)
async def process_booking_cancellation_callback(query, context, booking_id, user_id):
    """Обработка отмены через callback"""
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT b.booking_date, s.name, m.name, sl.name, b.client_name, b.status
        FROM bookings b
        JOIN services s ON b.service_id = s.id
        JOIN masters m ON b.master_id = m.id
        JOIN salons sl ON b.salon_id = sl.id
        WHERE b.id = ? AND b.user_id = ?
    ''', (booking_id, user_id))
    
    booking = cursor.fetchone()
    conn.close()
    
    if not booking:
        await query.edit_message_text("❌ Запись не найдена или у вас нет прав для ее отмены")
        return
    
    booking_date, service_name, master_name, salon_name, client_name, status = booking
    
    if status == 'cancelled':
        await query.edit_message_text("❌ Эта запись уже отменена")
        return
    
    # 🔧 ПОДТВЕРЖДЕНИЕ ОТМЕНЫ
    try:
        if isinstance(booking_date, str):
            booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
        else:
            booking_datetime = booking_date
        
        formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
        time_until = (booking_datetime - datetime.now()).total_seconds() / 3600
        
    except Exception as e:
        formatted_date = "дата не определена"
        time_until = 999
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, отменить", callback_data=f"confirm_cancel_{booking_id}"),
            InlineKeyboardButton("❌ Нет, оставить", callback_data="cancel_cancellation")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    warning_text = ""
    if time_until < 2:
        warning_text = "\n\n⚠️ <b>Внимание!</b> Поздняя отмена (менее 2 часов до записи)."
    
    await query.edit_message_text(
        f"❓ **Подтверждение отмены**\n\n"
        f"Вы действительно хотите отменить запись?\n\n"
        f"🆔 Запись #{booking_id}\n"
        f"🏪 Салон: {salon_name}\n"
        f"💅 Услуга: {service_name}\n"
        f"👨‍💼 Мастер: {master_name}\n"
        f"📅 Дата: {formatted_date}\n"
        f"{warning_text}",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
async def execute_booking_cancellation(query, context, booking_id):
    """Выполняет отмену записи"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Получаем информацию о записи перед отменой
        cursor.execute('''
            SELECT b.booking_date, s.name, m.name, sl.name, b.client_name, 
                   sl.telegram_chat_id, b.client_phone
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            JOIN masters m ON b.master_id = m.id
            JOIN salons sl ON b.salon_id = sl.id
            WHERE b.id = ?
        ''', (booking_id,))
        
        booking_info = cursor.fetchone()
        
        if not booking_info:
            await query.edit_message_text("❌ Запись не найдена")
            conn.close()
            return
        
        booking_date, service_name, master_name, salon_name, client_name, salon_chat_id, client_phone = booking_info
        
        # Отменяем запись
        cursor.execute('UPDATE bookings SET status = "cancelled" WHERE id = ?', (booking_id,))
        
        # Удаляем связанные напоминания
        cursor.execute('DELETE FROM booking_reminders WHERE booking_id = ?', (booking_id,))
        
        conn.commit()
        conn.close()
        
        # 🔧 ФОРМАТИРУЕМ ДАТУ ДЛЯ СООБЩЕНИЯ
        try:
            if isinstance(booking_date, str):
                booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
            else:
                booking_datetime = booking_date
            
            formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
        except:
            formatted_date = "дата не определена"
        
        # Сообщение клиенту
        await query.edit_message_text(
            f"✅ **Запись отменена!**\n\n"
            f"🆔 Запись #{booking_id}\n"
            f"🏪 Салон: {salon_name}\n"
            f"💅 Услуга: {service_name}\n"
            f"👨‍💼 Мастер: {master_name}\n"
            f"📅 Дата: {formatted_date}\n\n"
            f"💫 Ждем вас снова!\n\n"
            f"📋 Посмотреть записи: /mybookings"
        )
        
        # 🔔 УВЕДОМЛЯЕМ САЛОН ОБ ОТМЕНЕ
        await send_cancellation_notification(booking_id, client_name, client_phone, service_name, master_name, formatted_date, salon_chat_id)
        
    except Exception as e:
        await query.edit_message_text("❌ Ошибка при отмене записи")
        logger.error(f"Error executing cancellation: {e}")
async def send_cancellation_notification(booking_id, client_name, client_phone, service_name, master_name, formatted_date, salon_chat_id):
    """Уведомляет салон об отмене записи"""
    try:
        if not salon_chat_id:
            return
        
        cancellation_text = (
            f"🚫 **ОТМЕНА ЗАПИСИ**\n\n"
            f"Клиент отменил запись:\n\n"
            f"👤 Клиент: {client_name}\n"
            f"📞 Телефон: {client_phone}\n"
            f"💅 Услуга: {service_name}\n"
            f"👨‍💼 Мастер: {master_name}\n"
            f"📅 Дата: {formatted_date}\n\n"
            f"🆔 ID записи: {booking_id}"
        )
        
        app = Application.builder().token(BOT_TOKEN).build()
        await app.initialize()
        await app.bot.send_message(chat_id=salon_chat_id, text=cancellation_text)
        await app.shutdown()
        
        print(f"✅ Уведомление об отмене отправлено салону")
        
    except Exception as e:
        print(f"❌ Ошибка при отправке уведомления об отмене: {e}")
async def cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена записи клиентом"""
    try:
        user = update.message.from_user
        
        # Если указан ID записи в команде
        if context.args:
            booking_id = int(context.args[0])
            await process_booking_cancellation(update, context, booking_id, user.id)
            return
        
        # Если ID не указан - показываем список записей для отмены
        await show_bookings_for_cancellation(update, context, user.id)
        
    except ValueError:
        await update.message.reply_text(
            "❌ **Неверный формат номера записи!**\n\n"
            "Используйте: /cancelbooking <номер_записи>\n"
            "Например: /cancelbooking 5\n\n"
            "📋 Или просто /cancelbooking чтобы увидеть ваши записи"
        )
    except Exception as e:
        await update.message.reply_text("❌ Ошибка при отмене записи")
        logger.error(f"Error in cancel_booking: {e}")
async def show_bookings_for_cancellation(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    """Показывает записи клиента для отмены"""
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Получаем активные записи пользователя
    cursor.execute('''
        SELECT b.id, b.booking_date, s.name as service_name, 
               m.name as master_name, sl.name as salon_name,
               b.client_name, b.status
        FROM bookings b
        JOIN services s ON b.service_id = s.id
        JOIN masters m ON b.master_id = m.id
        JOIN salons sl ON b.salon_id = sl.id
        WHERE b.user_id = ? AND b.status = 'confirmed'
        AND b.booking_date > datetime('now')
        ORDER BY b.booking_date ASC
    ''', (user_id,))
    
    bookings = cursor.fetchall()
    conn.close()
    
    if not bookings:
        await update.message.reply_text(
            "📋 **Ваши записи для отмены**\n\n"
            "У вас нет активных записей, которые можно отменить.\n\n"
            "💡 Активные записи - это подтвержденные записи на будущее время."
        )
        return
    
    bookings_text = "📋 **Ваши активные записи:**\n\n"
    keyboard = []
    
    for booking in bookings:
        booking_id, booking_date, service_name, master_name, salon_name, client_name, status = booking
        
        # 🔧 ОБРАБАТЫВАЕМ ДАТУ
        try:
            if isinstance(booking_date, str):
                booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
            else:
                booking_datetime = booking_date
            
            formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
            time_until = (booking_datetime - datetime.now()).total_seconds() / 3600  # часов до записи
            
        except Exception as e:
            formatted_date = "дата не определена"
            time_until = 999
        
        bookings_text += (
            f"🆔 **Запись #{booking_id}**\n"
            f"🏪 Салон: {salon_name}\n"
            f"💅 Услуга: {service_name}\n"
            f"👨‍💼 Мастер: {master_name}\n"
            f"📅 Дата: {formatted_date}\n"
        )
        
        # 🔧 ПРЕДУПРЕЖДЕНИЕ О ПОЗДНЕЙ ОТМЕНЕ
        if time_until < 2:  # менее 2 часов до записи
            bookings_text += f"⚠️ <b>Поздняя отмена!</b>\n"
        
        bookings_text += f"────────────────────\n"
        
        # Добавляем кнопку для отмены
        button_text = f"❌ Отменить запись #{booking_id}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"cancel_booking_{booking_id}")])
    
    bookings_text += "\n💡 <b>Выберите запись для отмены:</b>"
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        bookings_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
async def process_booking_cancellation(update: Update, context: ContextTypes.DEFAULT_TYPE, booking_id, user_id):
    """Обрабатывает отмену конкретной записи"""
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Проверяем существование записи и права пользователя
    cursor.execute('''
        SELECT b.booking_date, s.name, m.name, sl.name, b.client_name, b.status, b.user_id
        FROM bookings b
        JOIN services s ON b.service_id = s.id
        JOIN masters m ON b.master_id = m.id
        JOIN salons sl ON b.salon_id = sl.id
        WHERE b.id = ?
    ''', (booking_id,))
    
    booking = cursor.fetchone()
    
    if not booking:
        await update.message.reply_text("❌ Запись не найдена")
        conn.close()
        return
    
    booking_date, service_name, master_name, salon_name, client_name, status, booking_user_id = booking
    
    # 🔒 ПРОВЕРКА ПРАВ
    if booking_user_id != user_id:
        await update.message.reply_text("❌ Вы можете отменять только свои записи")
        conn.close()
        return
    
    if status == 'cancelled':
        await update.message.reply_text("❌ Эта запись уже отменена")
        conn.close()
        return
        
    # 🔧 ПРОВЕРКА ВРЕМЕНИ
    try:
        if isinstance(booking_date, str):
            booking_datetime = datetime.strptime(booking_date, '%Y-%m-%d %H:%M:%S')
        else:
            booking_datetime = booking_date
        
        # Проверяем, не прошла ли уже запись
        if booking_datetime < datetime.now():
            await update.message.reply_text("❌ Нельзя отменить прошедшую запись")
            conn.close()
            return
        
        time_until = (booking_datetime - datetime.now()).total_seconds() / 3600  # часов до записи
        
    except Exception as e:
        print(f"❌ Ошибка обработки даты: {e}")
        time_until = 999
    
    # 🔧 ПОДТВЕРЖДЕНИЕ ОТМЕНЫ
    formatted_date = booking_datetime.strftime('%d.%m.%Y в %H:%M')
    
    # Создаем клавиатуру подтверждения
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, отменить", callback_data=f"confirm_cancel_{booking_id}"),
            InlineKeyboardButton("❌ Нет, оставить", callback_data="cancel_cancellation")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    warning_text = ""
    if time_until < 2:
        warning_text = "\n\n⚠️ <b>Внимание!</b> Поздняя отмена (менее 2 часов до записи) может повлиять на вашу репутацию."
    
    await update.message.reply_text(
        f"❓ **Подтверждение отмены**\n\n"
        f"Вы действительно хотите отменить запись?\n\n"
        f"🆔 Запись #{booking_id}\n"
        f"🏪 Салон: {salon_name}\n"
        f"💅 Услуга: {service_name}\n"
        f"👨‍💼 Мастер: {master_name}\n"
        f"📅 Дата: {formatted_date}\n"
        f"{warning_text}",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    
    conn.close()
async def owner_manage_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('owner_authenticated'):
        await update.message.reply_text("❌ Сначала войдите в систему: /login")
        return
    
    query = update.callback_query
    await query.answer()
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM services WHERE salon_id = ? AND is_active = 1', (salon_id,))
    active_services = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM services WHERE salon_id = ? AND is_active = 0', (salon_id,))
    inactive_services = cursor.fetchone()[0]
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить услугу", callback_data="owner_add_service")],
        [InlineKeyboardButton("📋 Список услуг", callback_data="owner_list_services")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"💅 **Управление услугами**\n🏪 Салон: {salon_name}\n\n"
        f"📊 Статистика:\n• Активных услуг: {active_services}\n• Неактивных: {inactive_services}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup   
    )
async def delete_database_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для инициализации удаления базы данных"""
    user_id = update.message.from_user.id
    if not is_operator(user_id):
        await update.message.reply_text("❌ Доступ запрещен")
        return
    
    # Генерируем сложный код подтверждения
    confirmation_code = secrets.token_hex(8).upper()
    context.user_data['delete_confirmation_code'] = confirmation_code
    context.user_data['waiting_for_confirmation'] = True
    
    await update.message.reply_text(
        f"⚠️ **ОПАСНОЕ ДЕЙСТВИЕ - УДАЛЕНИЕ БАЗЫ ДАННЫХ** ⚠️\n\n"
        f"Для подтверждения удаления ВСЕХ данных введите следующий код:\n\n"
        f"🔐 `{confirmation_code}`\n\n"
        f"❌ **ЭТО ДЕЙСТВИЕ НЕОБРАТИМО!**\n"
        f"• Будут удалены ВСЕ салоны\n"
        f"• Будут удалены ВСЕ мастера\n"
        f"• Будут удалены ВСЕ услуги\n"
        f"• Будут удалены ВСЕ записи\n\n"
        f"Для отмены введите /cancel\n"
        f"Для подтверждения введите код выше:",
        parse_mode='HTML'
    )
async def handle_confirmation_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ввода кода подтверждения"""
    if not context.user_data.get('waiting_for_confirmation'):
        return
    
    user_input = update.message.text.strip()
    correct_code = context.user_data.get('delete_confirmation_code')
    
    if user_input == correct_code:
        # Код верный - удаляем базу
        try:
            if os.path.exists('salons.db'):
                os.remove('salons.db')
                context.user_data.clear()
                
                await update.message.reply_text(
                    "✅ **База данных успешно удалена!**\n\n"
                    "Все данные были полностью очищены.\n"
                    "Для создания новой базы перезапустите бота."
                )
                print("🗑️ База данных удалена по команде оператора")
            else:
                await update.message.reply_text("❌ База данных не найдена")
                
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при удалении базы: {e}")
            
    elif user_input == '/cancel':
        context.user_data.clear()
        await update.message.reply_text("✅ Удаление базы отменено")
        
    else:
        await update.message.reply_text(
            "❌ Неверный код подтверждения!\n\n"
            "Проверьте код и попробуйте еще раз.\n"
            "Для отмены введите /cancel"
        )
async def cancel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена удаления базы"""
    if context.user_data.get('waiting_for_confirmation'):
        context.user_data.clear()
        await update.message.reply_text("✅ Удаление базы отменено")
    else:
        await update.message.reply_text("❌ Нет активного процесса удаления")
async def owner_add_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания услуги с одним сообщением"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    # 🔧 СОХРАНЯЕМ СООБЩЕНИЕ ДЛЯ РЕДАКТИРОВАНИЯ
    message = await query.edit_message_text(
        "💅 **Добавление новой услуги**\n\n"
        "Введите название услуги:"
    )
    
    context.user_data['service_message_id'] = message.message_id
    context.user_data['service_chat_id'] = message.chat_id
    context.user_data['waiting_for_service_name'] = True
async def handle_service_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода цены услуги с редактированием"""
    if not context.user_data.get('waiting_for_service_price'):
        return
    
    try:
        price_text = update.message.text.strip()
        service_name = context.user_data.get('new_service_name')
        
        if not price_text:
            await context.bot.edit_message_text(
                chat_id=context.user_data.get('service_chat_id'),
                message_id=context.user_data.get('service_message_id'),
                text=f"💅 **Название услуги:** {service_name}\n\n"
                     f"❌ **Цена не может быть пустой!**\n\n"
                     f"💰 Введите цену услуги (в рублях):"
            )
            return
        
        # 🔧 ПРОВЕРЯЕМ ФОРМАТ ЦЕНЫ
        is_range_price = '-' in price_text
        
        if is_range_price:
            # Проверяем диапазон цен
            parts = price_text.split('-')
            if len(parts) != 2:
                await context.bot.edit_message_text(
                    chat_id=context.user_data.get('service_chat_id'),
                    message_id=context.user_data.get('service_message_id'),
                    text=f"💅 **Название услуги:** {service_name}\n\n"
                         f"❌ **Неверный формат диапазона!**\n\n"
                         f"💰 Введите цену в формате: 1000-1500"
                )
                return
        
        context.user_data['new_service_price'] = price_text
        context.user_data['new_service_is_range'] = is_range_price
        context.user_data['waiting_for_service_price'] = False
        context.user_data['waiting_for_service_duration'] = True
        
        # 🔧 РЕДАКТИРУЕМ СООБЩЕНИЕ
        await context.bot.edit_message_text(
            chat_id=context.user_data.get('service_chat_id'),
            message_id=context.user_data.get('service_message_id'),
            text=f"💅 **Название услуги:** {service_name}\n"
                 f"💰 **Цена:** {price_text} руб.\n\n"
                 f"⏱️ Введите длительность услуги (в минутах):\n\n"
                 f"💡 Например: 60 (для 1 часа)"
        )
        
        # 🔧 УДАЛЯЕМ СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ
        try:
            await update.message.delete()
        except:
            pass
        
    except Exception as e:
        print(f"❌ Ошибка при вводе цены услуги: {e}")
async def handle_service_duration_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода длительности услуги с редактированием"""
    if not context.user_data.get('waiting_for_service_duration'):
        return
    
    try:
        duration_text = update.message.text.strip()
        service_name = context.user_data.get('new_service_name')
        service_price = context.user_data.get('new_service_price')
        
        if not duration_text or not duration_text.isdigit():
            await context.bot.edit_message_text(
                chat_id=context.user_data.get('service_chat_id'),
                message_id=context.user_data.get('service_message_id'),
                text=f"💅 **Название услуги:** {service_name}\n"
                     f"💰 **Цена:** {service_price} руб.\n\n"
                     f"❌ **Неверная длительность!**\n\n"
                     f"⏱️ Введите длительность в минутах (только цифры):"
            )
            return
        
        duration = int(duration_text)
        
        if duration <= 0:
            await context.bot.edit_message_text(
                chat_id=context.user_data.get('service_chat_id'),
                message_id=context.user_data.get('service_message_id'),
                text=f"💅 **Название услуги:** {service_name}\n"
                     f"💰 **Цена:** {service_price} руб.\n\n"
                     f"❌ **Длительность должна быть больше 0!**\n\n"
                     f"⏱️ Введите длительность в минутах:"
            )
            return
        
        context.user_data['new_service_duration'] = duration
        context.user_data['waiting_for_service_duration'] = False
        
        # 🔧 СОЗДАЕМ УСЛУГУ В БАЗЕ ДАННЫХ
        salon_id = context.user_data.get('current_salon_id')
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO services (salon_id, name, price, duration, is_range_price, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (salon_id, service_name, service_price, duration, 
              context.user_data.get('new_service_is_range', False)))
        
        service_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # 🔧 ФОРМИРУЕМ ТЕКСТ ПОДТВЕРЖДЕНИЯ
        hours = duration // 60
        minutes = duration % 60
        duration_formatted = f"{hours}ч {minutes}м" if hours > 0 else f"{minutes}м"
        
        # 🔧 РЕДАКТИРУЕМ СООБЩЕНИЕ С УСПЕШНЫМ СОЗДАНИЕМ
        keyboard = [
            [InlineKeyboardButton("💅 К управлению услугами", callback_data="owner_manage_services")],
            [InlineKeyboardButton("➕ Добавить еще услугу", callback_data="owner_add_service")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.edit_message_text(
            chat_id=context.user_data.get('service_chat_id'),
            message_id=context.user_data.get('service_message_id'),
            text=f"✅ **Услуга успешно создана!**\n\n"
                 f"💅 **Название:** {service_name}\n"
                 f"💰 **Цена:** {service_price} руб.\n"
                 f"⏱️ **Длительность:** {duration_formatted}\n"
                 f"🆔 **ID услуги:** {service_id}",
            reply_markup=reply_markup
        )
        
        # 🔧 УДАЛЯЕМ СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ
        try:
            await update.message.delete()
        except:
            pass
        
        # 🔧 ОЧИЩАЕМ КОНТЕКСТ
        context.user_data.pop('new_service_name', None)
        context.user_data.pop('new_service_price', None)
        context.user_data.pop('new_service_duration', None)
        context.user_data.pop('new_service_is_range', None)
        context.user_data.pop('service_message_id', None)
        context.user_data.pop('service_chat_id', None)
        
    except Exception as e:
        print(f"❌ Ошибка при создании услуги: {e}")
        await context.bot.edit_message_text(
            chat_id=context.user_data.get('service_chat_id'),
            message_id=context.user_data.get('service_message_id'),
            text="❌ Ошибка при создании услуги. Попробуйте еще раз."
        )
        context.user_data.clear()
async def send_and_pin_salon_link(chat_id, salon_name, unique_token):
    """Отправляет и закрепляет ссылку салона в чате"""
    try:
        salon_link = generate_salon_link(unique_token)
        
        message_text = (
            f"🏪 **Ссылка вашего салона**\n\n"
            f"Название: {salon_name}\n"
            f"🔗 Ссылка для клиентов:\n`{salon_link}`\n\n"
            f"📋 **Как использовать:**\n"
            f"• Отправьте эту ссылку клиентам\n"
            f"• Клиенты могут записываться через нее\n"
            f"• Все записи будут приходить в этот чат\n\n"
            f"⚠️ **Не удаляйте это сообщение!**"
        )
        
        # Отправляем сообщение через бота
        app = Application.builder().token(BOT_TOKEN).build()
        await app.initialize()
        
        message = await app.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode='HTML'
        )
        
        # Пытаемся закрепить сообщение (может не работать в некоторых чатах)
        try:
            await app.bot.pin_chat_message(
                chat_id=chat_id,
                message_id=message.message_id
            )
            print(f"📌 Ссылка салона отправлена и закреплена в чате {chat_id}")
        except Exception as pin_error:
            print(f"⚠️ Не удалось закрепить сообщение: {pin_error}")
        
        await app.shutdown()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при отправке/закреплении ссылки: {e}")
        return False
async def owner_edit_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    salon_id = context.user_data.get('current_salon_id')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, price, duration, is_active 
        FROM services 
        WHERE salon_id = ? 
        ORDER BY name
    ''', (salon_id,))
    services = cursor.fetchall()
    conn.close()
    
    if not services:
        await query.edit_message_text("❌ В вашем салоне пока нет услуг для редактирования")
        return
    
    keyboard = []
    for service in services:
        status = "✅" if service[4] else "❌"
        button_text = f"{status} {service[1]} - {service[2]} руб."
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"edit_service_{service[0]}")])
    
    keyboard.append([InlineKeyboardButton("« Назад", callback_data="owner_manage_services")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "💅 **Выберите услугу для редактирования:**",
        reply_markup=reply_markup
    )
async def handle_edit_service_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    service_id = query.data.split('_')[2]
    context.user_data['editing_service_id'] = service_id
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name, price, duration, is_active FROM services WHERE id = ?', (service_id,))
    service = cursor.fetchone()
    conn.close()
    
    status = "Активна ✅" if service[3] else "Неактивна ❌"
    hours = service[2] // 60
    minutes = service[2] % 60
    duration_text = f"{hours}ч {minutes}м" if hours > 0 else f"{minutes}м"
    
    keyboard = [
        [InlineKeyboardButton("✏️ Изменить название", callback_data=f"change_service_name_{service_id}")],
        [InlineKeyboardButton("💰 Изменить цену", callback_data=f"change_service_price_{service_id}")],
        [InlineKeyboardButton("⏱️ Изменить длительность", callback_data=f"change_service_duration_{service_id}")],
        [InlineKeyboardButton("🔄 Активировать/Деактивировать", callback_data=f"toggle_service_{service_id}")],
        [InlineKeyboardButton("🗑️ Удалить услугу", callback_data=f"delete_service_{service_id}")],
        [InlineKeyboardButton("« Назад", callback_data="owner_edit_service")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"💅 **Редактирование услуги**\n\n"
        f"Название: {service[0]}\n"
        f"Цена: {service[1]} руб.\n"
        f"Длительность: {duration_text}\n"
        f"Статус: {status}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )
async def handle_change_service_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    service_id = query.data.split('_')[3]
    context.user_data['changing_service_name'] = service_id
    context.user_data['waiting_for_new_service_name'] = True
    
    await query.edit_message_text(
        "✏️ **Изменение названия услуги**\n\n"
        "Введите новое название услуги:"
    )
async def handle_change_service_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    service_id = query.data.split('_')[3]
    context.user_data['changing_service_price'] = service_id
    context.user_data['waiting_for_new_service_price'] = True
    
    await query.edit_message_text(
        "💰 **Изменение цены услуги**\n\n"
        "Введите новую цену услуги (в рублях):"
    )
async def handle_change_service_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    service_id = query.data.split('_')[3]
    context.user_data['changing_service_duration'] = service_id
    context.user_data['waiting_for_new_service_duration'] = True
    
    await query.edit_message_text(
        "⏱️ **Изменение длительности услуги**\n\n"
        "Введите новую длительность услуги (в минутах):"
    )
async def handle_toggle_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    service_id = query.data.split('_')[2]
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Получаем текущий статус
    cursor.execute('SELECT is_active, name FROM services WHERE id = ?', (service_id,))
    service_data = cursor.fetchone()
    current_status = service_data[0]
    service_name = service_data[1]
    
    # Меняем статус
    new_status = not current_status
    cursor.execute('UPDATE services SET is_active = ? WHERE id = ?', (new_status, service_id))
    
    conn.commit()
    conn.close()
    
    status_text = "активирована" if new_status else "деактивирована"
    status_emoji = "✅" if new_status else "❌"
    
    # 🔧 СОЗДАЕМ ИНЛАЙН-КЛАВИАТУРУ ВМЕСТО КОМАНДЫ /services
    keyboard = [
        [InlineKeyboardButton("💅 К управлению услугами", callback_data="owner_manage_services")],
        [InlineKeyboardButton("📋 Список услуг", callback_data="owner_list_services")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="owner_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"{status_emoji} **Услуга '{service_name}' {status_text}!**\n\n"
        f"Клиенты {'теперь могут' if new_status else 'больше не могут'} "
        f"записываться на эту услугу.",
        reply_markup=reply_markup
    )
async def handle_approximate_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ввода примерной стоимости"""
    if not context.user_data.get('waiting_for_approximate_price'):
        return
    
    try:
        text = update.message.text.strip()
        original_text = text  # Сохраняем оригинальный текст для отображения
        
        # Парсим разные форматы ввода
        if '-' in text:
            # Формат: 1000-1500
            parts = text.split('-')
            min_price = int(parts[0].strip())
            max_price = int(parts[1].strip())
            display_price = f"{min_price}-{max_price}"
        elif 'от' in text.lower() and 'до' in text.lower():
            # Формат: от 1000 до 2000
            text_lower = text.lower()
            start_idx = text_lower.find('от') + 2
            end_idx = text_lower.find('до')
            min_price = int(text[start_idx:end_idx].strip())
            max_price = int(text[end_idx+2:].strip())
            display_price = f"{min_price}-{max_price}"
        else:
            # Пробуем извлечь числа из текста
            numbers = [int(s) for s in text.split() if s.isdigit()]
            if len(numbers) >= 2:
                min_price = min(numbers)
                max_price = max(numbers)
                display_price = f"{min_price}-{max_price}"
            else:
                raise ValueError("Не удалось распознать диапазон")
        
        # Проверяем валидность диапазона
        if min_price <= 0 or max_price <= 0:
            # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ ОТМЕНЫ ДЛЯ ОШИБКИ
            keyboard = [
                [InlineKeyboardButton("❌ Отменить создание", callback_data="cancel_service_creation")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "❌ Цены должны быть положительными числами. Введите еще раз:",
                reply_markup=reply_markup
            )
            return
        
        if min_price >= max_price:
            # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ ОТМЕНЫ ДЛЯ ОШИБКИ
            keyboard = [
                [InlineKeyboardButton("❌ Отменить создание", callback_data="cancel_service_creation")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "❌ Минимальная цена должна быть меньше максимальной. Введите еще раз:",
                reply_markup=reply_markup
            )
            return
        
        if max_price > 100000:
            # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ ОТМЕНЫ ДЛЯ ОШИБКИ
            keyboard = [
                [InlineKeyboardButton("❌ Отменить создание", callback_data="cancel_service_creation")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "❌ Слишком высокая цена. Введите реалистичный диапазон:",
                reply_markup=reply_markup
            )
            return
        
        # Сохраняем диапазон цен
        context.user_data['new_service_price'] = display_price  # Сохраняем как строку "1000-1500"
        context.user_data['price_is_range'] = True  # Флаг что цена это диапазон
        context.user_data['waiting_for_approximate_price'] = False
        context.user_data['waiting_for_service_duration'] = True
        
        service_name = context.user_data['new_service_name']
        
        # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ ОТМЕНЫ
        keyboard = [
            [InlineKeyboardButton("❌ Отменить создание", callback_data="cancel_service_creation")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ **Примерная стоимость установлена!**\n\n"
            f"💰 Диапазон цен: <b>{display_price} руб.</b>\n\n"
            f"⏱️ Теперь введите длительность услуги (в минутах):\n"
            f"Например: 60 (для 1 часа), 90 (для 1.5 часов)",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
    except (ValueError, IndexError) as e:
        # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ ОТМЕНЫ ДЛЯ ОШИБКИ
        keyboard = [
            [InlineKeyboardButton("❌ Отменить создание", callback_data="cancel_service_creation")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ Неверный формат диапазона!\n\n"
            "📝 **Правильные форматы:**\n"
            "• <code>1000-1500</code>\n"
            "• <code>500-2000</code>\n"
            "• <code>от 1000 до 2000</code>\n\n"
            "💡 <i>Введите диапазон еще раз:</i>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
async def handle_edit_specializations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирование специализаций мастера"""
    query = update.callback_query
    await query.answer()
    
    master_id = query.data.split('_')[2]
    context.user_data['editing_master_id'] = master_id
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Получаем информацию о мастере
    cursor.execute('SELECT name, specialization FROM masters WHERE id = ?', (master_id,))
    master = cursor.fetchone()
    
    # Получаем список всех услуг салона
    salon_id = context.user_data.get('current_salon_id')
    cursor.execute('SELECT id, name FROM services WHERE salon_id = ? AND is_active = 1', (salon_id,))
    services = cursor.fetchall()
    
    # Получаем текущие специализации мастера
    cursor.execute('SELECT service_id FROM master_services WHERE master_id = ?', (master_id,))
    current_services = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    
    keyboard = []
    for service in services:
        status = "✅" if service[0] in current_services else "❌"
        button_text = f"{status} {service[1]}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"toggle_master_service_{master_id}_{service[0]}")])
    
    keyboard.append([InlineKeyboardButton("« Назад", callback_data="owner_manage_specializations")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🔧 **Настройка специализаций для {master[0]}**\n"
        f"Текущая специализация: {master[1]}\n\n"
        f"Выберите услуги, которые может выполнять мастер:",
        reply_markup=reply_markup
    )
async def handle_service_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода названия услуги с редактированием"""
    if not context.user_data.get('waiting_for_service_name'):
        return
    
    try:
        service_name = update.message.text.strip()
        
        if not service_name:
            await context.bot.edit_message_text(
                chat_id=context.user_data.get('service_chat_id'),
                message_id=context.user_data.get('service_message_id'),
                text="❌ **Название не может быть пустым!**\n\n"
                     "Введите название услуги:"
            )
            return
        
        context.user_data['new_service_name'] = service_name
        context.user_data['waiting_for_service_name'] = False
        context.user_data['waiting_for_service_price'] = True
        
        # 🔧 РЕДАКТИРУЕМ СООБЩЕНИЕ
        await context.bot.edit_message_text(
            chat_id=context.user_data.get('service_chat_id'),
            message_id=context.user_data.get('service_message_id'),
            text=f"💅 **Название услуги:** {service_name}\n\n"
                 f"💰 Введите цену услуги (в рублях):\n\n"
                 f"💡 Можно указать диапазон: 1000-1500"
        )
        
        # 🔧 УДАЛЯЕМ СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ
        try:
            await update.message.delete()
        except:
            pass
        
    except Exception as e:
        print(f"❌ Ошибка при вводе названия услуги: {e}")
async def handle_toggle_master_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Включение/выключение услуги для мастера с инлайн-кнопками"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    master_id = parts[3]
    service_id = parts[4]
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Проверяем, есть ли уже такая связь
    cursor.execute('SELECT id FROM master_services WHERE master_id = ? AND service_id = ?', (master_id, service_id))
    existing = cursor.fetchone()
    
    if existing:
        # Удаляем связь
        cursor.execute('DELETE FROM master_services WHERE master_id = ? AND service_id = ?', (master_id, service_id))
        action = "удалена"
    else:
        # Добавляем связь
        cursor.execute('INSERT INTO master_services (master_id, service_id) VALUES (?, ?)', (master_id, service_id))
        action = "добавлена"
    
    conn.commit()
    
    # Получаем названия для сообщения
    cursor.execute('SELECT name FROM masters WHERE id = ?', (master_id,))
    master_name = cursor.fetchone()[0]
    cursor.execute('SELECT name FROM services WHERE id = ?', (service_id,))
    service_name = cursor.fetchone()[0]
    
    conn.close()
    
    # 🔧 СОЗДАЕМ ИНЛАЙН-КЛАВИАТУРУ ВМЕСТО КОМАНДЫ /masters
    keyboard = [
        [InlineKeyboardButton("👨‍💼 К управлению мастерами", callback_data="owner_manage_masters")],
        [InlineKeyboardButton("🔧 К специализациям", callback_data="owner_manage_specializations")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="owner_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✅ **Специализация обновлена!**\n\n"
        f"Мастер: {master_name}\n"
        f"Услуга: {service_name}\n"
        f"Статус: {action}\n\n"
        f"💫 Изменения сохранены в системе",
        reply_markup=reply_markup
    )
async def handle_delete_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление услуги с инлайн-кнопками"""
    query = update.callback_query
    await query.answer()
    
    service_id = query.data.split('_')[2]
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Получаем название услуги для сообщения
    cursor.execute('SELECT name FROM services WHERE id = ?', (service_id,))
    service_name = cursor.fetchone()[0]
    
    # Проверяем, есть ли активные записи на эту услугу
    cursor.execute('SELECT COUNT(*) FROM bookings WHERE service_id = ? AND status = "confirmed"', (service_id,))
    active_bookings = cursor.fetchone()[0]
    
    if active_bookings > 0:
        keyboard = [
            [InlineKeyboardButton("💅 К управлению услугами", callback_data="owner_manage_services")],
            [InlineKeyboardButton("🔙 Назад", callback_data="owner_edit_service")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"❌ **Нельзя удалить услугу '{service_name}'!**\n\n"
            f"На эту услугу есть {active_bookings} активных записей.\n"
            f"Сначала деактивируйте услугу или переназначьте записи.",
            reply_markup=reply_markup
        )
        conn.close()
        return
    
    # Удаляем услугу
    cursor.execute('DELETE FROM services WHERE id = ?', (service_id,))
    conn.commit()
    conn.close()
    
    # 🔧 СОЗДАЕМ ИНЛАЙН-КЛАВИАТУРУ
    keyboard = [
        [InlineKeyboardButton("💅 К управлению услугами", callback_data="owner_manage_services")],
        [InlineKeyboardButton("📋 Список услуг", callback_data="owner_list_services")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="owner_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✅ **Услуга '{service_name}' удалена!**",
        reply_markup=reply_markup
    )
async def handle_new_service_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_new_service_name'):
        return
    
    try:
        new_name = update.message.text
        service_id = context.user_data['changing_service_name']
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE services SET name = ? WHERE id = ?', (new_name, service_id))
        conn.commit()
        conn.close()
        
        context.user_data['waiting_for_new_service_name'] = False
        context.user_data['changing_service_name'] = None
        
        # 🔧 СОЗДАЕМ ИНЛАЙН-КЛАВИАТУРУ ВМЕСТО КОМАНДЫ /services
        keyboard = [
            [InlineKeyboardButton("💅 К управлению услугами", callback_data="owner_manage_services")],
            [InlineKeyboardButton("📋 Список услуг", callback_data="owner_list_services")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ **Название услуги изменено!**\n\n"
            f"Новое название: {new_name}",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при изменении названия: {e}")
async def handle_new_service_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода новой цены услуги с инлайн-кнопками"""
    if not context.user_data.get('waiting_for_new_service_price'):
        return
    
    try:
        new_price = int(update.message.text)
        service_id = context.user_data['changing_service_price']
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE services SET price = ? WHERE id = ?', (new_price, service_id))
        conn.commit()
        conn.close()
        
        context.user_data['waiting_for_new_service_price'] = False
        context.user_data['changing_service_price'] = None
        
        # 🔧 СОЗДАЕМ ИНЛАЙН-КЛАВИАТУРУ
        keyboard = [
            [InlineKeyboardButton("💅 К управлению услугами", callback_data="owner_manage_services")],
            [InlineKeyboardButton("📋 Список услуг", callback_data="owner_list_services")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ **Цена услуги изменена!**\n\n"
            f"Новая цена: {new_price} руб.",
            reply_markup=reply_markup
        )
        
    except ValueError:
        await update.message.reply_text("❌ Цена должна быть числом. Введите цену еще раз:")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при изменении цены: {e}")
async def handle_new_service_duration_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода новой длительности услуги с инлайн-кнопками"""
    if not context.user_data.get('waiting_for_new_service_duration'):
        return
    
    try:
        new_duration = int(update.message.text)
        service_id = context.user_data['changing_service_duration']
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE services SET duration = ? WHERE id = ?', (new_duration, service_id))
        conn.commit()
        conn.close()
        
        context.user_data['waiting_for_new_service_duration'] = False
        context.user_data['changing_service_duration'] = None
        
        hours = new_duration // 60
        minutes = new_duration % 60
        duration_text = f"{hours}ч {minutes}м" if hours > 0 else f"{minutes}м"
        
        # 🔧 СОЗДАЕМ ИНЛАЙН-КЛАВИАТУРУ
        keyboard = [
            [InlineKeyboardButton("💅 К управлению услугами", callback_data="owner_manage_services")],
            [InlineKeyboardButton("📋 Список услуг", callback_data="owner_list_services")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ **Длительность услуги изменена!**\n\n"
            f"Новая длительность: {duration_text}",
            reply_markup=reply_markup
        )
        
    except ValueError:
        await update.message.reply_text("❌ Длительность должна быть числом. Введите длительность еще раз:")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при изменении длительности: {e}")
async def owner_salon_settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню настроек салона"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT telegram_chat_id FROM salons WHERE id = ?', (salon_id,))
    salon_data = cursor.fetchone()
    conn.close()
    
    current_chat_id = salon_data[0] if salon_data else "Не установлен"
    
    keyboard = [
        [InlineKeyboardButton("📞 Изменить Chat ID", callback_data="owner_change_chat_id")],
        [InlineKeyboardButton("🕐 Время работы", callback_data="owner_working_hours")],
        [InlineKeyboardButton("🔙 Назад", callback_data="owner_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"⚙️ **Настройки салона**\n🏪 {salon_name}\n\n"
        f"📞 Текущий Chat ID: `{current_chat_id}`\n\n"
        f"💡 <i>Chat ID используется для уведомлений о новых записях</i>\n\n"
        f"Выберите настройку для изменения:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
async def owner_change_chat_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик изменения Chat ID"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['waiting_for_new_chat_id'] = True
    await query.edit_message_text(
        "📞 **Изменение Chat ID**\n\n"
        "Введите новый Telegram Chat ID для уведомлений:\n"
        "(владелец может узнать через @userinfobot)\n\n"
        "⚠️ <b>Требования к Chat ID:</b>\n"
        "• Должен быть числом\n"
        "• Минимум 6 символов\n"
        "• Может быть отрицательным для групп\n\n"
        "Текущий Chat ID используется для отправки уведомлений о новых записях.",
        parse_mode='HTML'
    )
async def handle_new_chat_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ввода нового Chat ID с проверкой"""
    if not context.user_data.get('waiting_for_new_chat_id'):
        return
    
    try:
        new_chat_id = update.message.text
        
        # 🔒 ПРОВЕРКА CHAT ID
        try:
            chat_id_int = int(new_chat_id)
        except ValueError:
            await update.message.reply_text(
                "❌ **Неверный формат Chat ID!**\n\n"
                "Chat ID должен быть числом.\n"
                "Пожалуйста, введите корректный Telegram Chat ID:"
            )
            return
        
        # Проверяем длину
        if len(new_chat_id) < 6:
            await update.message.reply_text(
                "❌ **Неверная длина Chat ID!**\n\n"
                "Chat ID слишком короткий.\n"
                "Пожалуйста, введите корректный Telegram Chat ID:"
            )
            return
        
        salon_id = context.user_data.get('current_salon_id')
        
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE salons SET telegram_chat_id = ? WHERE id = ?', (new_chat_id, salon_id))
        conn.commit()
        conn.close()
        
        context.user_data['waiting_for_new_chat_id'] = False
        
        # 🔧 СОЗДАЕМ ИНЛАЙН-КЛАВИАТУРУ ВМЕСТО КОМАНДЫ /settings
        keyboard = [
            [InlineKeyboardButton("⚙️ К настройкам салона", callback_data="owner_salon_settings")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ **Chat ID успешно обновлен!**\n\n"
            f"Новый Chat ID: `{new_chat_id}`\n\n"
            f"Теперь уведомления о новых записях будут приходить на этот чат.",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при обновлении Chat ID: {e}")
async def finish_service_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение создания услуги с инлайн-кнопками"""
    query = update.callback_query
    await query.answer()
    
    try:
        # 🔍 ПРОВЕРЯЕМ АВТОРИЗАЦИЮ ПЕРЕД ВЫПОЛНЕНИЕМ
        if not context.user_data.get('owner_authenticated'):
            await query.edit_message_text("❌ Сессия истекла. Войдите заново.")
            return
        
        service_name = context.user_data['new_service_name']
        price = context.user_data['new_service_price']
        price_is_range = context.user_data.get('price_is_range', False)
        duration = context.user_data['new_service_duration']
        selected_masters = context.user_data.get('selected_masters', [])
        salon_id = context.user_data.get('current_salon_id')
        salon_name = context.user_data.get('current_salon_name')
        
        # Сохраняем услугу в базу
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        
        # Если цена это диапазон, сохраняем как строку
        if price_is_range:
            cursor.execute('''
                INSERT INTO services (salon_id, name, price, duration, is_range_price) 
                VALUES (?, ?, ?, ?, ?)
            ''', (salon_id, service_name, str(price), duration, 1))
        else:
            cursor.execute('''
                INSERT INTO services (salon_id, name, price, duration, is_range_price) 
                VALUES (?, ?, ?, ?, ?)
            ''', (salon_id, service_name, str(price), duration, 0))
        
        service_id = cursor.lastrowid
        
        # 🔥 СОХРАНЯЕМ СВЯЗИ С МАСТЕРАМИ
        for master_id in selected_masters:
            cursor.execute('INSERT INTO master_services (master_id, service_id) VALUES (?, ?)', (master_id, service_id))
        
        conn.commit()
        conn.close()
        
        # 🔥 ФОРМИРУЕМ СООБЩЕНИЕ О РЕЗУЛЬТАТАХ
        if selected_masters:
            # Получаем имена мастеров для сообщения
            conn = sqlite3.connect('salons.db')
            cursor = conn.cursor()
            cursor.execute('SELECT name FROM masters WHERE id IN ({})'.format(','.join('?' * len(selected_masters))), selected_masters)
            master_names = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            masters_text = ", ".join(master_names)
            masters_count = len(selected_masters)
        else:
            masters_text = "не назначены"
            masters_count = 0
        
        # Формируем текст цены
        if price_is_range:
            price_text = f"{price} руб. (диапазон)"
        else:
            price_text = f"{price} руб."
        
        # 🔧 БЕЗОПАСНАЯ ОЧИСТКА - удаляем только данные процесса, сохраняем авторизацию
        keys_to_remove = [
            'waiting_for_service_name', 'waiting_for_service_price', 'waiting_for_service_duration',
            'waiting_for_approximate_price', 'new_service_name', 'new_service_price', 'new_service_duration', 
            'selected_masters', 'price_is_range'
        ]
        
        for key in keys_to_remove:
            context.user_data.pop(key, None)
        
        # 🔧 СОЗДАЕМ ИНЛАЙН-КЛАВИАТУРУ
        keyboard = [
            [InlineKeyboardButton("💅 К управлению услугами", callback_data="owner_manage_services")],
            [InlineKeyboardButton("➕ Добавить еще услугу", callback_data="owner_add_service")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ **Услуга успешно создана!**\n\n"
            f"💅 Услуга: {service_name}\n"
            f"💰 Цена: {price_text}\n"
            f"⏱️ Длительность: {duration} мин.\n"
            f"👨‍💼 Мастеров: {masters_count}\n"
            f"📋 Мастера: {masters_text}\n\n"
            f"Теперь клиенты могут записываться на эту услугу!",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка при создании услуги: {e}")
        logger.error(f"Error creating service: {e}")
async def owner_working_hours_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню времени работы"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT day_of_week, start_time, end_time, is_working 
        FROM working_hours 
        WHERE salon_id = ? 
        ORDER BY day_of_week
    ''', (salon_id,))
    working_hours = cursor.fetchall()
    conn.close()
    
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    
    hours_text = f"🕐 **Время работы салона**\n🏪 {salon_name}\n\n"
    
    for i, day_data in enumerate(working_hours):
        day_name = days[i]
        if day_data[3]:
            hours_text += f"✅ {day_name}: {day_data[1]} - {day_data[2]}\n"
        else:
            hours_text += f"❌ {day_name}: Выходной\n"
    
    keyboard = [
        [InlineKeyboardButton("✏️ Редактировать время", callback_data="owner_edit_working_hours")],
        [InlineKeyboardButton("🔙 Назад", callback_data="owner_salon_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(hours_text, reply_markup=reply_markup)
async def owner_working_hours_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для времени работы"""
    if not context.user_data.get('owner_authenticated'):
        # 🔧 ЗАМЕНЯЕМ КОМАНДУ /login НА КНОПКУ
        keyboard = [
            [InlineKeyboardButton("🔐 Войти как владелец", callback_data="owner_login_start")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu_return")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ Сначала войдите в систему",
            reply_markup=reply_markup
        )
        return
    await owner_working_hours_handler(update, context)
async def owner_edit_working_hours_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирование времени работы"""
    query = update.callback_query
    await query.answer()
    
    # Русские названия дней недели
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    
    keyboard = []
    for i, day in enumerate(days):
        keyboard.append([InlineKeyboardButton(f"📅 {day}", callback_data=f"edit_day_{i}")])
    
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "✏️ **Редактирование времени работы**\n\n"
        "Выберите день для редактирования:",
        reply_markup=reply_markup
    )
async def handle_edit_day_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора дня для редактирования"""
    query = update.callback_query
    await query.answer()
    
    day_index = int(query.data.split('_')[2])
    context.user_data['editing_day'] = day_index
    
    # Русские названия дней недели
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    day_name = days[day_index]
    
    salon_id = context.user_data.get('current_salon_id')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT start_time, end_time, is_working 
        FROM working_hours 
        WHERE salon_id = ? AND day_of_week = ?
    ''', (salon_id, day_index))
    day_data = cursor.fetchone()
    conn.close()
    
    current_status = "Рабочий день" if day_data[2] else "Выходной"
    current_hours = f"{day_data[0]} - {day_data[1]}" if day_data[2] else "Не работает"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Сделать рабочим/выходным", callback_data=f"set_working_{day_index}")],
    ]
    
    if day_data[2]:  # если рабочий день
        keyboard.append([InlineKeyboardButton("⏰ Изменить время работы", callback_data=f"change_hours_{day_index}")])
    
    keyboard.append([InlineKeyboardButton("« Назад к дням", callback_data="owner_edit_working_hours")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📅 **Редактирование {day_name}**\n\n"
        f"Текущий статус: {current_status}\n"
        f"Время работы: {current_hours}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )
async def handle_set_working_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение статуса рабочего дня"""
    query = update.callback_query
    await query.answer()
    
    day_index = int(query.data.split('_')[2])
    salon_id = context.user_data.get('current_salon_id')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Получаем текущий статус
    cursor.execute('SELECT is_working FROM working_hours WHERE salon_id = ? AND day_of_week = ?', (salon_id, day_index))
    current_status = cursor.fetchone()[0]
    
    # Меняем статус
    new_status = not current_status
    cursor.execute('UPDATE working_hours SET is_working = ? WHERE salon_id = ? AND day_of_week = ?', 
                  (new_status, salon_id, day_index))
    
    conn.commit()
    conn.close()
    
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    day_name = days[day_index]
    status_text = "рабочим" if new_status else "выходным"
    
    # 🔧 СОЗДАЕМ ИНЛАЙН-КЛАВИАТУРУ ВМЕСТО КОМАНДЫ /settings
    keyboard = [
        [InlineKeyboardButton("🕐 К расписанию", callback_data="owner_working_hours")],
        [InlineKeyboardButton("⚙️ К настройкам", callback_data="owner_salon_settings")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="owner_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✅ **{day_name} установлен как {status_text} день!**",
        reply_markup=reply_markup
    )
async def handle_change_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Изменение времени работы для дня"""
    query = update.callback_query
    await query.answer()
    
    day_index = int(query.data.split('_')[2])
    context.user_data['changing_hours_day'] = day_index
    context.user_data['waiting_for_start_time'] = True
    
    # Русские названия дней недели
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    day_name = days[day_index]
    
    # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ НАЗАД
    keyboard = [
        [InlineKeyboardButton("🔙 Назад ", callback_data="owner_edit_working_hours")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"⏰ **Изменение времени работы для {day_name}**\n\n"
        "Введите время начала работы в формате ЧЧ:ММ\n"
        "Например: 09:00 или 10:30\n\n"
        "⚠️ <b>Формат:</b> 24-часовой, от 00:00 до 23:30",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
async def handle_master_selection_for_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора мастеров для новой услуги"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "finish_masters_selection":
        await finish_service_creation(update, context)
        return
    
    if query.data == "cancel_service_creation":
        await handle_cancel_service_creation(update, context)
        return
    
    master_id = int(query.data.split('_')[2])
    
    # Инициализируем список, если его нет
    if 'selected_masters' not in context.user_data:
        context.user_data['selected_masters'] = []
    
    selected_masters = context.user_data['selected_masters']
    
    # Проверяем, выбран ли уже этот мастер
    if master_id in selected_masters:
        # Убираем мастера из выбранных
        selected_masters.remove(master_id)
        action = "❌ Удален"
    else:
        # Добавляем мастера в выбранные
        selected_masters.append(master_id)
        action = "✅ Добавлен"
    
    # Обновляем список мастеров
    salon_id = context.user_data.get('current_salon_id')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, specialization FROM masters WHERE salon_id = ? AND is_active = 1', (salon_id,))
    masters = cursor.fetchall()
    conn.close()
    
    # 🔥 ОБНОВЛЯЕМ СООБЩЕНИЕ С ТЕКУЩИМ СОСТОЯНИЕМ И КНОПКОЙ ОТМЕНЫ
    keyboard = []
    for master in masters:
        status = "✅" if master[0] in selected_masters else "⬜"
        button_text = f"{status} {master[1]} ({master[2]})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"select_master_{master[0]}")])
    
    keyboard.append([InlineKeyboardButton("💾 СОХРАНИТЬ УСЛУГУ", callback_data="finish_masters_selection")])
    keyboard.append([InlineKeyboardButton("❌ Отменить создание", callback_data="cancel_service_creation")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Формируем текст выбранных мастеров
    selected_masters_text = "пока нет"
    if selected_masters:
        selected_names = []
        for master_id in selected_masters:
            master_info = next((m for m in masters if m[0] == master_id), None)
            if master_info:
                selected_names.append(master_info[1])
        selected_masters_text = ", ".join(selected_names)
    
    service_name = context.user_data['new_service_name']
    price = context.user_data['new_service_price']
    duration = context.user_data['new_service_duration']
    
    await query.edit_message_text(
        f"💅 **Создание услуги:** {service_name}\n"
        f"💰 Цена: {price} руб.\n"
        f"⏱️ Длительность: {duration} мин.\n\n"
        f"👨‍💼 **Выберите мастеров для этой услуги:**\n"
        f"(нажмите на мастера, чтобы добавить/удалить)\n\n"
        f"✅ Выбранные мастера: {selected_masters_text}\n\n"
        f"Когда закончите, нажмите **СОХРАНИТЬ УСЛУГУ**",
        reply_markup=reply_markup
    )
async def handle_suggested_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для примерной стоимости"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "suggest_approximate_price":
        # Устанавливаем флаг, что ждем примерную стоимость
        context.user_data['waiting_for_approximate_price'] = True
        context.user_data['waiting_for_service_price'] = False
        
        # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ ОТМЕНЫ
        keyboard = [
            [InlineKeyboardButton("❌ Отменить создание", callback_data="cancel_service_creation")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "💰 **Укажите примерную стоимость услуги:**\n\n"
            "Введите диапазон цен в формате:\n"
            "• <code>1000-1500</code>\n"
            "• <code>500-2000</code>\n"
            "• <code>от 1000 до 2000</code>\n\n"
            "💡 <i>Клиентам будет показан именно этот диапазон</i>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
async def handle_confirm_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик подтверждения цены"""
    query = update.callback_query
    await query.answer()
    
    price = int(query.data.split('_')[2])
    
    # Сохраняем цену и переходим к следующему шагу
    context.user_data['new_service_price'] = price
    context.user_data['waiting_for_service_price'] = False
    context.user_data['waiting_for_service_duration'] = True
    
    service_name = context.user_data['new_service_name']
    
    await query.edit_message_text(
        f"✅ Цена услуги установлена: <b>{price} руб.</b>\n\n"
        "⏱️ Введите длительность услуги (в минутах):\n"
        "Например: 60 (для 1 часа), 90 (для 1.5 часов)\n\n"
        "💡 <i>Рекомендуемые длительности:</i>\n"
        "• Стрижка: 60-90 мин\n"
        "• Окрашивание: 120-180 мин\n"
        "• Маникюр: 60-90 мин\n"
        "• Массаж: 60-120 мин",
        parse_mode='HTML'
    )
async def handle_edit_day_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора дня для редактирования"""
    query = update.callback_query
    await query.answer()
    
    day_index = int(query.data.split('_')[2])
    context.user_data['editing_day'] = day_index
    
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    day_name = days[day_index]
    
    salon_id = context.user_data.get('current_salon_id')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT start_time, end_time, is_working 
        FROM working_hours 
        WHERE salon_id = ? AND day_of_week = ?
    ''', (salon_id, day_index))
    day_data = cursor.fetchone()
    conn.close()
    
    current_status = "Рабочий день" if day_data[2] else "Выходной"
    current_hours = f"{day_data[0]} - {day_data[1]}" if day_data[2] else "Не работает"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Сделать рабочим/выходным", callback_data=f"set_working_{day_index}")],
    ]
    
    if day_data[2]:  # если рабочий день
        keyboard.append([InlineKeyboardButton("⏰ Изменить время работы", callback_data=f"change_hours_{day_index}")])
    
    keyboard.append([InlineKeyboardButton("« Назад к дням", callback_data="owner_edit_working_hours")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📅 **Редактирование {day_name}**\n\n"
        f"Текущий статус: {current_status}\n"
        f"Время работы: {current_hours}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )
async def handle_start_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ввода времени начала"""
    if not context.user_data.get('waiting_for_start_time'):
        print("🔍 handle_start_time_input: флаг не установлен")
        return
    
    try:
        start_time = update.message.text.strip()
        print(f"🔍 handle_start_time_input: получено время {start_time}")
        
        # 🔧 ПРОВЕРЯЕМ ФОРМАТ ВРЕМЕНИ
        # Добавляем ведущий ноль если нужно (6:00 -> 06:00)
        if len(start_time) == 4 and start_time[1] == ':':
            start_time = '0' + start_time
        
        # Проверяем корректный формат
        datetime.strptime(start_time, '%H:%M')
        
        context.user_data['new_start_time'] = start_time
        context.user_data['waiting_for_start_time'] = False
        context.user_data['waiting_for_end_time'] = True
        
        print(f"🔍 handle_start_time_input: установлен waiting_for_end_time = True")
        
        days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        day_index = context.user_data['changing_hours_day']
        day_name = days[day_index]
        
        # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ НАЗАД
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data=f"change_hours_{day_index}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ Время начала: <b>{start_time}</b>\n\n"
            f"Теперь введите время окончания работы для {day_name}:\n"
            "Например: 18:00 или 20:30\n\n"
            "⚠️ <b>Время окончания должно быть позже времени начала</b>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
    except ValueError:
        # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ НАЗАД ДЛЯ ОШИБКИ
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к дням", callback_data="owner_edit_working_hours")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ Неверный формат времени!\n\n"
            "Введите время в формате ЧЧ:ММ\n"
            "Например: 09:00, 10:30, 18:00\n\n"
            "💡 <i>Можно вводить как 6:00 так и 06:00</i>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
async def handle_end_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ввода времени окончания"""
    if not context.user_data.get('waiting_for_end_time'):
        return
    
    try:
        end_time = update.message.text.strip()
        
        # Проверяем формат времени
        datetime.strptime(end_time, '%H:%M')
        
        # Проверяем, что время окончания позже времени начала
        start_time = context.user_data['new_start_time']
        start_dt = datetime.strptime(start_time, '%H:%M')
        end_dt = datetime.strptime(end_time, '%H:%M')
        
        if end_dt <= start_dt:
            # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ НАЗАД ДЛЯ ОШИБКИ
            keyboard = [
                [InlineKeyboardButton("🔙 Назад", callback_data=f"change_hours_{context.user_data['changing_hours_day']}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "❌ Время окончания должно быть позже времени начала!\n\n"
                f"Начало: {start_time}\n"
                f"Окончание: {end_time}\n\n"
                "Введите время окончания еще раз:",
                reply_markup=reply_markup
            )
            return
        
        day_index = context.user_data['changing_hours_day']
        salon_id = context.user_data.get('current_salon_id')
        
        # Обновляем время в базе
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE working_hours 
            SET start_time = ?, end_time = ?, is_working = 1 
            WHERE salon_id = ? AND day_of_week = ?
        ''', (start_time, end_time, salon_id, day_index))
        conn.commit()
        conn.close()
        
        # 🔧 ПОЛНАЯ ОЧИСТКА КОНТЕКСТА ДЛЯ ВРЕМЕНИ РАБОТЫ
        context.user_data.pop('waiting_for_end_time', None)
        context.user_data.pop('waiting_for_start_time', None)
        context.user_data.pop('changing_hours_day', None)
        context.user_data.pop('new_start_time', None)
        
        days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        day_name = days[day_index]
        
        # 🔧 СОЗДАЕМ ИНЛАЙН-КЛАВИАТУРУ С КНОПКОЙ НАЗАД
        keyboard = [
            [InlineKeyboardButton("🕐 К расписанию", callback_data="owner_working_hours")],
            [InlineKeyboardButton("⚙️ К настройкам", callback_data="owner_salon_settings")],
            [InlineKeyboardButton("🔙 Назад к дням", callback_data="owner_edit_working_hours")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="owner_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ **Время работы для {day_name} обновлено!**\n\n"
            f"🕐 Новое время: {start_time} - {end_time}",
            reply_markup=reply_markup
        )
        
    except ValueError:
        # 🔧 СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ НАЗАД ДЛЯ ОШИБКИ
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к началу", callback_data=f"change_hours_{context.user_data['changing_hours_day']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ Неверный формат времени!\n\n"
            "Введите время в формате ЧЧ:ММ\n"
            "Например: 18:00, 20:30, 22:00",
            reply_markup=reply_markup
        )
async def owner_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика салона"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Общая статистика
    cursor.execute('SELECT COUNT(*) FROM bookings WHERE salon_id = ?', (salon_id,))
    total_bookings = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM bookings WHERE salon_id = ? AND status = "confirmed"', (salon_id,))
    confirmed_bookings = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM masters WHERE salon_id = ? AND is_active = 1', (salon_id,))
    active_masters = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM services WHERE salon_id = ? AND is_active = 1', (salon_id,))
    active_services = cursor.fetchone()[0]
    
    # Статистика по услугам
    cursor.execute('''
        SELECT s.name, COUNT(b.id) 
        FROM bookings b 
        JOIN services s ON b.service_id = s.id 
        WHERE b.salon_id = ? 
        GROUP BY s.name 
        ORDER BY COUNT(b.id) DESC 
        LIMIT 5
    ''', (salon_id,))
    popular_services = cursor.fetchall()
    
    conn.close()
    
    stats_text = f"📊 **Статистика салона**\n🏪 {salon_name}\n\n"
    stats_text += f"📈 **Общая статистика:**\n"
    stats_text += f"• Всего записей: {total_bookings}\n"
    stats_text += f"• Подтвержденных записей: {confirmed_bookings}\n"
    stats_text += f"• Активных мастеров: {active_masters}\n"
    stats_text += f"• Активных услуг: {active_services}\n\n"
    
    if popular_services:
        stats_text += "🏆 **Популярные услуги:**\n"
        for service in popular_services:
            stats_text += f"• {service[0]}: {service[1]} записей\n"
    
    keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="owner_stats"), 
                InlineKeyboardButton("🏠 В главное меню", callback_data="owner_main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(stats_text, reply_markup=reply_markup)
async def owner_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для статистики"""
    if not context.user_data.get('owner_authenticated'):
        # 🔧 ЗАМЕНЯЕМ КОМАНДУ /login НА КНОПКУ
        keyboard = [
            [InlineKeyboardButton("🔐 Войти как владелец", callback_data="owner_login_start")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu_return")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ Сначала войдите в систему",
            reply_markup=reply_markup
        )
        return
    await owner_stats_handler(update, context)
async def owner_list_masters_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ списка мастеров для владельца"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему: /login")
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    
    # Получаем мастеров с количеством услуг
    cursor.execute('''
        SELECT m.id, m.name, m.specialization, m.is_active, 
               COUNT(ms.service_id) as services_count
        FROM masters m
        LEFT JOIN master_services ms ON m.id = ms.master_id
        WHERE m.salon_id = ?
        GROUP BY m.id
        ORDER BY m.is_active DESC, m.name
    ''', (salon_id,))
    
    masters = cursor.fetchall()
    conn.close()
    
    if not masters:
        await query.edit_message_text(
            f"👨‍💼 **Мастера салона {salon_name}**\n\n"
            "❌ Мастера пока не добавлены\n\n"
            "Добавьте первого мастера, чтобы начать работу!"
        )
        return
    
    masters_text = f"👨‍💼 **Мастера салона {salon_name}**\n\n"
    
    active_masters = [m for m in masters if m[3]]  # is_active = True
    inactive_masters = [m for m in masters if not m[3]]  # is_active = False
    
    if active_masters:
        masters_text += "✅ **Активные мастера:**\n"
        for master in active_masters:
            status_icon = "🟢" if master[3] else "🔴"
            services_info = f"({master[4]} услуг)" if master[4] > 0 else "(нет услуг)"
            masters_text += f"{status_icon} {master[1]} - {master[2]} {services_info}\n"
        masters_text += "\n"
    
    if inactive_masters:
        masters_text += "❌ **Неактивные мастера:**\n"
        for master in inactive_masters:
            services_info = f"({master[4]} услуг)" if master[4] > 0 else "(нет услуг)"
            masters_text += f"🔴 {master[1]} - {master[2]} {services_info}\n"
    
    # Статистика
    total_masters = len(masters)
    active_count = len(active_masters)
    inactive_count = len(inactive_masters)
    
    stats_text = f"\n📊 **Статистика:** {total_masters} мастеров ({active_count} активных, {inactive_count} неактивных)"
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить мастера", callback_data="owner_add_master")],
        [InlineKeyboardButton("🔧 Управление специализациями", callback_data="owner_manage_specializations")],
        [InlineKeyboardButton("🔄 Обновить список", callback_data="owner_list_masters")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        masters_text + stats_text,
        reply_markup=reply_markup
    )
async def owner_main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню владельца салона"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('owner_authenticated'):
        await query.edit_message_text("❌ Сначала войдите в систему")
        return
    
    salon_name = context.user_data.get('current_salon_name', 'ваш салон')
    
    keyboard = [
        [InlineKeyboardButton("📋 Записи", callback_data="owner_bookings")],  # 🔧 ДОБАВЛЕН РАЗДЕЛ ЗАПИСИ
        [InlineKeyboardButton("👨‍💼 Управление мастерами", callback_data="owner_manage_masters")],
        [InlineKeyboardButton("💅 Управление услугами", callback_data="owner_manage_services")],
        [InlineKeyboardButton("⚙️ Настройки салона", callback_data="owner_salon_settings")],
        [InlineKeyboardButton("📊 Статистика", callback_data="owner_stats")],
        [InlineKeyboardButton("🔗 Получить ссылку салона", callback_data="owner_get_link")],
        [InlineKeyboardButton("🚪 Выйти из системы", callback_data="owner_logout_handler")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🏪 **Панель управления {salon_name}**\n\n"
        f"Выберите раздел для управления:",
        reply_markup=reply_markup
    )
async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_data = context.user_data

    print(f"🔍 Сообщение от пользователя {user.id}: {update.message.text}")
    print(f"🔍 Текущие флаги в user_data: {[k for k in user_data.keys() if 'waiting' in k or k in ['captcha_answer', 'owner_login', 'owner_authenticated']]}")
    
    # 🔧 ОБНОВЛЯЕМ АКТИВНОСТЬ ПОЛЬЗОВАТЕЛЯ
    register_bot_user(user.id, user.username, user.first_name)
    update_user_activity(user.id)
    
    # 🔧 **ВЫСШИЙ ПРИОРИТЕТ: ПРОЦЕССЫ НАСТРОЙКИ ВРЕМЕНИ РАБОТЫ**
    if user_data.get('waiting_for_start_time'):
        print(f"🔍 Обрабатываем как время начала работы")
        await handle_start_time_input(update, context)
        return
    
    if user_data.get('waiting_for_end_time'):
        print(f"🔍 Обрабатываем как время окончания работы")
        await handle_end_time_input(update, context)
        return
    
    # 🔧 **ВТОРОЙ ПРИОРИТЕТ: ПРОЦЕССЫ ОПЕРАТОРА И ВЛАДЕЛЬЦЕВ**
    if user_data.get('waiting_for_salon_name'):
        print(f"🔍 Обрабатываем как название салона от оператора")
        await handle_salon_name_input(update, context)
        return
    
    if user_data.get('waiting_for_salon_chat_id'):
        print(f"🔍 Обрабатываем как chat_id салона от оператора")
        await handle_salon_chat_id_input(update, context)
        return
    
    if user_data.get('waiting_for_new_chat_id'):
        print(f"🔍 Обрабатываем как новый chat_id салона")
        await handle_new_chat_id_input(update, context)
        return
    
    # 🔧 **ТРЕТИЙ ПРИОРИТЕТ: ПРОЦЕСС АВТОРИЗАЦИИ ВЛАДЕЛЬЦА**
    if user_data.get('waiting_for_owner_login'):
        print(f"🔍 Обрабатываем как логин владельца")
        await handle_owner_login_input(update, context)
        return
    
    if user_data.get('waiting_for_owner_password'):
        print(f"🔍 Обрабатываем как пароль владельца")
        await handle_owner_password_input(update, context)
        return
    
    # 🔧 **ЧЕТВЕРТЫЙ ПРИОРИТЕТ: ПРОЦЕССЫ УПРАВЛЕНИЯ САЛОНОМ**
    if user_data.get('waiting_for_master_name'):
        print(f"🔍 Обрабатываем как имя мастера")
        await handle_master_name_input(update, context)
        return
    
    if user_data.get('waiting_for_master_specialization'):
        print(f"🔍 Обрабатываем как специализацию мастера")
        await handle_master_specialization_input(update, context)
        return
    
    if user_data.get('waiting_for_service_name'):
        print(f"🔍 Обрабатываем как название услуги")
        await handle_service_name_input(update, context)
        return
    
    if user_data.get('waiting_for_service_price'):
        print(f"🔍 Обрабатываем как цену услуги")
        await handle_service_price_input(update, context)
        return
    
    if user_data.get('waiting_for_approximate_price'):
        print(f"🔍 Обрабатываем как примерную стоимость")
        await handle_approximate_price_input(update, context)
        return
    
    if user_data.get('waiting_for_service_duration'):
        print(f"🔍 Обрабатываем как длительность услуги")
        await handle_service_duration_input(update, context)
        return
    
    if user_data.get('waiting_for_new_service_name'):
        print(f"🔍 Обрабатываем как новое название услуги")
        await handle_new_service_name_input(update, context)
        return
    
    if user_data.get('waiting_for_new_service_price'):
        print(f"🔍 Обрабатываем как новую цену услуги")
        await handle_new_service_price_input(update, context)
        return
    
    if user_data.get('waiting_for_new_service_duration'):
        print(f"🔍 Обрабатываем как новую длительность услуги")
        await handle_new_service_duration_input(update, context)
        return
    
    # 🔧 **ПЯТЫЙ ПРИОРИТЕТ: ПРОЦЕСС ЗАПИСИ КЛИЕНТА**
    if user_data.get('waiting_for_contact'):
        print(f"🔍 Обрабатываем как контакт для записи")
        await handle_contact_input(update, context)
        return
    
    # 🔧 **ШЕСТОЙ ПРИОРИТЕТ: ПРОЦЕСС КАПЧИ**
    user_captcha_passed = get_user_captcha_status(user.id)
    
    # Если пользователь оператор или владелец - пропускаем капчу
    is_operator_user = is_operator(user.id)
    is_owner_authenticated = user_data.get('owner_authenticated', False)
    
    if is_operator_user or is_owner_authenticated:
        print(f"🔍 Пользователь {user.id} - оператор или владелец, пропускаем капчу")
        user_captcha_passed = True
    
    if not user_captcha_passed and not user_data.get('waiting_for_captcha'):
        print(f"🔍 Капча не пройдена, запрашиваем капчу")
        await ask_captcha(update, context)
        return
    
    if user_data.get('waiting_for_captcha'):
        print(f"🔍 Обрабатываем как ответ на капчу")
        await verify_captcha(update, context)
        return
        
    # 🔧 **ЕСЛИ КАПЧА НЕ ПРОЙДЕНА - БЛОКИРУЕМ**
    if not user_captcha_passed:
        print(f"🔍 Капча не пройдена, блокируем")
        await update.message.reply_text("❌ Сначала пройдите проверку!")
        return
    
    # 🔧 **СЕДЬМОЙ ПРИОРИТЕТ: ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ БАЗЫ**
    if user_data.get('waiting_for_confirmation'):
        print(f"🔍 Обрабатываем как код подтверждения удаления БД")
        await handle_confirmation_code(update, context)
        return
    
    # 🔧 **ЕСЛИ НИ ОДИН ФЛАГ НЕ УСТАНОВЛЕН - ОБРАБОТКА ОБЫЧНЫХ СООБЩЕНИЙ**
    print(f"🔍 Обычное сообщение, обрабатываем через handle_regular_message")
    await handle_regular_message(update, context)
async def handle_regular_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка обычных сообщений после прохождения капчи"""
    user_data = context.user_data
    user = update.message.from_user
    message_text = update.message.text
    
    print(f"🔍 handle_regular_message: обычное сообщение от {user.id}: {message_text}")
    
    # 🔧 ПРОВЕРЯЕМ, ЕСЛИ ЭТО ССЫЛКА НА САЛОН
    if "t.me/" in message_text and "start=" in message_text:
        # Извлекаем токен из ссылки
        try:
            # Пример ссылки: https://t.me/GraphiteSystem_bot?start=5a8c7473ff310fba
            token_start = message_text.find("start=") + 6
            token_end = message_text.find(" ", token_start)
            if token_end == -1:
                token_end = len(message_text)
            
            salon_token = message_text[token_start:token_end]
            
            print(f"🔍 Найдена ссылка салона с токеном: {salon_token}")
            
            # Проверяем салон в базе
            conn = sqlite3.connect('salons.db')
            cursor = conn.cursor()
            cursor.execute('SELECT id, name, is_active FROM salons WHERE unique_token = ?', (salon_token,))
            salon = cursor.fetchone()
            conn.close()
            
            if salon:
                salon_id, salon_name, is_active = salon
                
                # 🔒 ПРОВЕРЯЕМ АКТИВНОСТЬ САЛОНА
                if not is_active:
                    await update.message.reply_text(
                        "❌ **Салон временно недоступен**\n\n"
                        "Этот салон временно отключен администратором.\n"
                        "Пожалуйста, обратитесь к администратору салона для уточнения информации."
                    )
                    return
                
                context.user_data['current_salon_id'] = salon_id
                context.user_data['current_salon_name'] = salon_name
                context.user_data['salon_token'] = salon_token
                
                # Показываем меню салона
                await show_client_main_menu(update, context)
                return
            else:
                await update.message.reply_text("❌ Ссылка недействительна или салон не найден")
                return
                
        except Exception as e:
            print(f"❌ Ошибка при обработке ссылки: {e}")
            await update.message.reply_text("❌ Неверный формат ссылки")
            return
    
    # 🔧 ЕСЛИ ЭТО ОПЕРАТОР - ПОКАЗЫВАЕМ ПАНЕЛЬ ОПЕРАТОРА
    if is_operator(user.id):
        keyboard = [
            [InlineKeyboardButton("👑 Панель оператора", callback_data="operator_panel_main")],
            [InlineKeyboardButton("🔐 Войти как владелец", callback_data="owner_login_start")],
            [InlineKeyboardButton("🔗 Все ссылки салонов", callback_data="operator_all_links")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "👑 Вы оператор системы\n\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )
        return
    
    # 🔧 ДЛЯ ВСЕХ ОСТАЛЬНЫХ - ПОКАЗЫВАЕМ ГЛАВНОЕ МЕНЮ
    await show_main_menu(update, context)
async def owner_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для настроек салона"""
    if not context.user_data.get('owner_authenticated'):
        # 🔧 ЗАМЕНЯЕМ КОМАНДУ /login НА КНОПКУ
        keyboard = [
            [InlineKeyboardButton("🔐 Войти как владелец", callback_data="owner_login_start")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu_return")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ Сначала войдите в систему",
            reply_markup=reply_markup
        )
        return
    
    salon_id = context.user_data.get('current_salon_id')
    salon_name = context.user_data.get('current_salon_name')
    
    conn = sqlite3.connect('salons.db')
    cursor = conn.cursor()
    cursor.execute('SELECT telegram_chat_id FROM salons WHERE id = ?', (salon_id,))
    salon_data = cursor.fetchone()
    conn.close()
    
    current_chat_id = salon_data[0] if salon_data else "Не установлен"
    
    keyboard = [
        [InlineKeyboardButton("📞 Изменить Chat ID", callback_data="owner_change_chat_id")],
        [InlineKeyboardButton("🕐 Настроить время работы", callback_data="owner_working_hours")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="owner_main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"⚙️ **Настройки салона**\n🏪 {salon_name}\n\n"
        f"📞 Текущий Chat ID: `{current_chat_id}`\n\n"
        f"Выберите настройку для изменения:",
        reply_markup=reply_markup
    )

    """Получает сообщение о техническом обслуживании"""
    try:
        conn = sqlite3.connect('salons.db')
        cursor = conn.cursor()
        cursor.execute('SELECT message FROM maintenance_mode WHERE is_active = 1 ORDER BY id DESC LIMIT 1')
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else "Система временно недоступна. Приносим извинения за неудобства."
    except:
        return "Система временно недоступна. Приносим извинения за неудобства."
def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    application.job_queue.run_once(lambda context: asyncio.create_task(start_reminder_scheduler(application)), when=5)
    application.job_queue.run_repeating(check_booking_reminders, interval=60, first=10)
    application.job_queue.run_repeating(cleanup_unconfirmed_bookings, interval=300, first=60)  # 🔧 
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_owner_login_input))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_owner_password_input))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_service_name_input))
    # Оставляем только самые необходимые команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("fixcaptcha", fix_captcha_command))  # временная команда для отладки
    application.add_handler(CommandHandler("test_booking", test_booking_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_service_name_input))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_service_price_input))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_service_duration_input))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_master_name_input))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_master_specialization_input))
    application.add_handler(CallbackQueryHandler(owner_pending_bookings_handler, pattern="^owner_pending_bookings$"))
    application.add_handler(CallbackQueryHandler(owner_confirmed_bookings_handler, pattern="^owner_confirmed_bookings$"))
    application.add_handler(CallbackQueryHandler(handle_remind_booking, pattern="^remind_booking_"))
    
    # 🔄 ОБРАБОТЧИКИ ИСТОРИИ
    application.add_handler(CallbackQueryHandler(owner_booking_history_handler, pattern="^owner_booking_history$"))
    application.add_handler(CallbackQueryHandler(client_booking_history_handler, pattern="^client_booking_history$"))
    
    # 🔄 ОБРАБОТЧИКИ ТЕХНИЧЕСКОГО ОБСЛУЖИВАНИЯ
    application.add_handler(CallbackQueryHandler(operator_maintenance_handler, pattern="^operator_maintenance$"))
    application.add_handler(CallbackQueryHandler(maintenance_enable_handler, pattern="^maintenance_enable$"))
    application.add_handler(CallbackQueryHandler(maintenance_schedule_handler, pattern="^maintenance_schedule$"))
    
    # 🔄 ОБРАБОТЧИКИ ПОДТВЕРЖДЕНИЯ САЛОНОМ
    application.add_handler(CallbackQueryHandler(handle_salon_confirm_booking, pattern="^salon_confirm_"))
    application.add_handler(CallbackQueryHandler(handle_salon_cancel_booking, pattern="^salon_cancel_"))
    
    # 🔄 ОБРАБОТЧИКИ СООБЩЕНИЙ
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages))
    # 🔄 СИСТЕМА КЛИЕНТОВ
    application.add_handler(CallbackQueryHandler(owner_main_menu_handler, pattern="^owner_main_menu$"))
    application.add_handler(CallbackQueryHandler(owner_manage_masters_handler, pattern="^owner_manage_masters$"))
    application.add_handler(CallbackQueryHandler(owner_manage_services_handler, pattern="^owner_manage_services$"))
    application.add_handler(CallbackQueryHandler(owner_salon_settings_handler, pattern="^owner_salon_settings$"))
    application.add_handler(CallbackQueryHandler(owner_stats_handler, pattern="^owner_stats$"))
    application.add_handler(CallbackQueryHandler(owner_get_link_handler, pattern="^owner_get_link$"))
    application.add_handler(CallbackQueryHandler(owner_pin_link_handler, pattern="^owner_pin_link$"))
    application.add_handler(CallbackQueryHandler(owner_working_hours_handler, pattern="^owner_working_hours$"))
    application.add_handler(CallbackQueryHandler(book_service_main_handler, pattern="^book_service_main$"))
    application.add_handler(CallbackQueryHandler(show_masters_main_handler, pattern="^show_masters_main$"))
    application.add_handler(CallbackQueryHandler(show_services_main_handler, pattern="^show_services_main$"))
    application.add_handler(CallbackQueryHandler(my_bookings_main_handler, pattern="^my_bookings_main$"))
    application.add_handler(CallbackQueryHandler(client_main_menu_handler, pattern="^client_main_menu$"))
    # 🔄 СИСТЕМА ОПЕРАТОРА
    application.add_handler(CallbackQueryHandler(operator_panel_main_handler, pattern="^operator_panel_main$"))
    application.add_handler(CallbackQueryHandler(operator_all_links_handler, pattern="^operator_all_links$"))
    application.add_handler(CallbackQueryHandler(operator_delete_db_handler, pattern="^operator_delete_db$"))
    application.add_handler(CallbackQueryHandler(operator_cleanup_handler, pattern="^operator_cleanup$"))
    application.add_handler(CallbackQueryHandler(main_menu_return_handler, pattern="^main_menu_return$"))
    application.add_handler(CallbackQueryHandler(show_main_menu, pattern="^show_main_menu$"))
    # 🔄 СИСТЕМА ВЛАДЕЛЬЦЕВ
    application.add_handler(CallbackQueryHandler(owner_login_start_handler, pattern="^owner_login_start$"))
    application.add_handler(CallbackQueryHandler(owner_get_link_handler, pattern="^owner_get_link$"))
    application.add_handler(CallbackQueryHandler(handle_cancel_service_creation, pattern="^cancel_service_creation$"))
    # 🔄 ОБЩИЕ КНОПКИ
    application.add_handler(CallbackQueryHandler(show_faq_callback, pattern="^show_faq$"))
    
    # 🔄 СУЩЕСТВУЮЩИЕ ОБРАБОТЧИКИ (оставляем все существующие)
    application.add_handler(CallbackQueryHandler(handle_reminder_choice, pattern="^(reminder_24|reminder_1)$"))
    application.add_handler(CallbackQueryHandler(handle_faq_main_callback, pattern="^(show_faq|book_service_from_faq|owner_login_from_faq)$"))
    application.add_handler(CallbackQueryHandler(handle_faq_callback, pattern="^faq_back$"))
    application.add_handler(CallbackQueryHandler(handle_cancel_booking_callback, pattern="^(cancel_booking_|confirm_cancel_|cancel_cancellation)"))
    application.add_handler(CallbackQueryHandler(handle_master_selection, pattern="^master_"))
    application.add_handler(CallbackQueryHandler(handle_calendar_navigation, pattern="^calendar_(prev|next)_"))
    application.add_handler(CallbackQueryHandler(handle_back_to_master, pattern="^back_to_master$"))
    application.add_handler(CallbackQueryHandler(handle_ignore_callback, pattern="^ignore$"))
    application.add_handler(CallbackQueryHandler(owner_delete_master_handler, pattern="^owner_delete_master$"))
    application.add_handler(CallbackQueryHandler(handle_master_delete_selection, pattern="^select_master_delete_"))
    application.add_handler(CallbackQueryHandler(handle_confirm_master_delete, pattern="^confirm_delete_master_"))
    application.add_handler(CallbackQueryHandler(owner_toggle_master_handler, pattern="^owner_toggle_master$"))
    application.add_handler(CallbackQueryHandler(handle_master_toggle_selection, pattern="^select_master_toggle_"))
    application.add_handler(CallbackQueryHandler(owner_manage_specializations, pattern="^owner_manage_specializations"))
    application.add_handler(CallbackQueryHandler(handle_edit_specializations, pattern="^edit_specializations_"))
    application.add_handler(CallbackQueryHandler(handle_toggle_master_service, pattern="^toggle_master_service_"))
    application.add_handler(CallbackQueryHandler(handle_service_selection, pattern="^service_"))
    application.add_handler(CallbackQueryHandler(handle_date_selection, pattern="^date_"))
    application.add_handler(CallbackQueryHandler(handle_time_selection, pattern="^time_"))
    application.add_handler(CallbackQueryHandler(handle_back_to_calendar, pattern="^back_to_calendar$"))
    application.add_handler(CallbackQueryHandler(owner_bookings_handler, pattern="^owner_bookings$"))
    application.add_handler(CallbackQueryHandler(owner_all_bookings_handler, pattern="^owner_all_bookings$"))
    application.add_handler(CallbackQueryHandler(owner_today_bookings_handler, pattern="^owner_today_bookings$"))
    application.add_handler(CallbackQueryHandler(handle_owner_booking_navigation, pattern="^(owner_prev_|owner_next_)"))
    application.add_handler(CallbackQueryHandler(show_masters_callback, pattern="^show_masters_from_faq$"))
    application.add_handler(CallbackQueryHandler(show_services_callback, pattern="^show_services_from_faq$"))
    application.add_handler(CallbackQueryHandler(handle_cancel_booking_callback, pattern="^(cancel_booking_|confirm_cancel_|cancel_cancellation)"))
    application.add_handler(CallbackQueryHandler(handle_back_to_calendar, pattern="^back_to_calendar"))
    application.add_handler(CallbackQueryHandler(operator_add_salon_handler, pattern="^operator_add_salon"))
    application.add_handler(CallbackQueryHandler(operator_list_salons_handler, pattern="^operator_list_salons"))
    application.add_handler(CallbackQueryHandler(owner_manage_masters, pattern="^owner_manage_masters"))
    application.add_handler(CallbackQueryHandler(owner_add_master_handler, pattern="^owner_add_master"))
    application.add_handler(CallbackQueryHandler(handle_suggested_price, pattern="^suggest_price_"))
    application.add_handler(CallbackQueryHandler(handle_salon_confirm_booking, pattern="^salon_confirm_"))
    application.add_handler(CallbackQueryHandler(handle_salon_cancel_booking, pattern="^salon_cancel_"))
    application.add_handler(CallbackQueryHandler(handle_suggested_price, pattern="^suggest_approximate_price$"))
    application.add_handler(CallbackQueryHandler(handle_confirm_price, pattern="^confirm_price_"))
    application.add_handler(CallbackQueryHandler(handle_suggested_price, pattern="^enter_custom_price$"))
    application.add_handler(CallbackQueryHandler(owner_main_menu_handler, pattern="^owner_main_menu"))
    application.add_handler(CallbackQueryHandler(owner_edit_working_hours_handler, pattern="^owner_edit_working_hours"))
    application.add_handler(CallbackQueryHandler(handle_edit_day_selection, pattern="^edit_day_"))
    application.add_handler(CallbackQueryHandler(handle_set_working_status, pattern="^set_working_"))
    application.add_handler(CallbackQueryHandler(show_main_menu, pattern="^show_main_menu$"))
    application.add_handler(CallbackQueryHandler(back_to_previous_handler, pattern="^back_to_previous$"))
    application.add_handler(CallbackQueryHandler(main_menu_return_handler, pattern="^main_menu_return$"))
    application.add_handler(CallbackQueryHandler(handle_refresh_bookings, pattern="^refresh_bookings$"))
    application.add_handler(CallbackQueryHandler(operator_toggle_salon_handler, pattern="^operator_toggle_salon$"))
    application.add_handler(CallbackQueryHandler(handle_salon_toggle_selection, pattern="^toggle_salon_"))
    # 🔄 СИСТЕМА ВЛАДЕЛЬЦЕВ - ОСНОВНЫЕ МЕНЮ
    application.add_handler(CallbackQueryHandler(owner_main_menu_handler, pattern="^owner_main_menu$"))
    application.add_handler(CallbackQueryHandler(owner_manage_masters_handler, pattern="^owner_manage_masters$"))
    application.add_handler(CallbackQueryHandler(owner_manage_services_handler, pattern="^owner_manage_services$"))
    application.add_handler(CallbackQueryHandler(owner_salon_settings_handler, pattern="^owner_salon_settings$"))
    application.add_handler(CallbackQueryHandler(owner_stats_handler, pattern="^owner_stats$"))
    application.add_handler(CallbackQueryHandler(owner_get_link_handler, pattern="^owner_get_link$"))
    application.add_handler(CallbackQueryHandler(owner_working_hours_handler, pattern="^owner_working_hours$"))
    
    # 🔄 СИСТЕМА ОПЕРАТОРА
    application.add_handler(CallbackQueryHandler(operator_panel_main_handler, pattern="^operator_panel_main$"))
    application.add_handler(CallbackQueryHandler(operator_list_salons_handler, pattern="^operator_list_salons$"))
    
    # 🔄 СИСТЕМА КЛИЕНТОВ
    
    application.add_handler(CallbackQueryHandler(book_service_main_handler, pattern="^book_service_main$"))
    application.add_handler(CallbackQueryHandler(show_masters_main_handler, pattern="^show_masters_main$"))
    application.add_handler(CallbackQueryHandler(show_services_main_handler, pattern="^show_services_main$"))
    application.add_handler(CallbackQueryHandler(my_bookings_main_handler, pattern="^my_bookings_main$"))
    application.add_handler(CallbackQueryHandler(show_faq_callback, pattern="^show_faq$"))
    application.add_handler(CallbackQueryHandler(client_main_menu_handler, pattern="^client_main_menu$"))
    application.add_handler(CallbackQueryHandler(show_client_main_menu, pattern="^client_main_menu$"))
    application.add_handler(CallbackQueryHandler(handle_change_hours, pattern="^change_hours_"))
    application.add_handler(CallbackQueryHandler(owner_manage_services, pattern="^owner_manage_services"))
    application.add_handler(CallbackQueryHandler(owner_add_service_handler, pattern="^owner_add_service"))
    application.add_handler(CallbackQueryHandler(owner_list_services_handler, pattern="^owner_list_services"))
    application.add_handler(CallbackQueryHandler(owner_edit_service_handler, pattern="^owner_edit_service"))
    application.add_handler(CallbackQueryHandler(handle_edit_service_selection, pattern="^edit_service_"))
    application.add_handler(CallbackQueryHandler(handle_change_service_name, pattern="^change_service_name_"))
    application.add_handler(CallbackQueryHandler(handle_change_service_price, pattern="^change_service_price_"))
    application.add_handler(CallbackQueryHandler(handle_change_service_duration, pattern="^change_service_duration_"))
    application.add_handler(CallbackQueryHandler(handle_toggle_service, pattern="^toggle_service_"))
    application.add_handler(CallbackQueryHandler(handle_delete_service, pattern="^delete_service_"))
    application.add_handler(CallbackQueryHandler(handle_master_selection_for_service, pattern="^select_master_"))
    application.add_handler(CallbackQueryHandler(finish_service_creation, pattern="^finish_masters_selection"))
    application.add_handler(CallbackQueryHandler(owner_logout_handler, pattern="^owner_logout_handler"))
    application.add_handler(CallbackQueryHandler(confirm_logout_handler, pattern="^confirm_logout"))
    application.add_handler(CallbackQueryHandler(owner_salon_settings_handler, pattern="^owner_salon_settings"))
    application.add_handler(CallbackQueryHandler(owner_change_chat_id_handler, pattern="^owner_change_chat_id"))
    application.add_handler(CallbackQueryHandler(owner_working_hours_handler, pattern="^owner_working_hours"))
    application.add_handler(CallbackQueryHandler(owner_edit_working_hours_handler, pattern="^owner_edit_working_hours"))
    application.add_handler(CallbackQueryHandler(handle_booking_confirmation, pattern="^confirm_booking_"))
    application.add_handler(CallbackQueryHandler(handle_edit_day_selection, pattern="^edit_day_"))
    application.add_handler(CallbackQueryHandler(handle_set_working_status, pattern="^set_working_"))
    application.add_handler(CallbackQueryHandler(owner_stats_handler, pattern="^owner_stats"))
    application.add_handler(CallbackQueryHandler(owner_list_masters_handler, pattern="^owner_list_masters"))
    # 🔄 НАВИГАЦИЯ ЗАПИСЕЙ
    application.add_handler(CallbackQueryHandler(handle_booking_navigation, pattern="^(prev_|next_)"))
    application.add_handler(CallbackQueryHandler(handle_delete_booking_callback, pattern="^delete_"))
    application.add_handler(CallbackQueryHandler(handle_confirm_delete, pattern="^confirm_"))
    application.add_handler(CallbackQueryHandler(handle_cancel_deletion, pattern="^cancel$"))
    application.add_handler(CallbackQueryHandler(handle_refresh_bookings, pattern="^refresh$"))
    application.add_handler(CallbackQueryHandler(maintenance_status_handler, pattern="^maintenance_status$"))
    application.add_handler(CallbackQueryHandler(maintenance_disable_handler, pattern="^maintenance_disable$"))
    application.add_handler(CallbackQueryHandler(maintenance_cancel_handler, pattern="^maintenance_cancel$"))

# Обработчик текстовых сообщений для даты техперерыва
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_maintenance_date_input))
    application.job_queue.run_repeating(
    check_unconfirmed_bookings,
    interval=300,  # 5 минут
    first=10
)
    # 🔄 ОБРАБОТКА СООБЩЕНИЙ
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages))
    
    print("🚀 Бот запускается с полностью инлайн-интерфейсом...")
    print(f"🤖 Бот: @{BOT_USERNAME}")
    print("🎯 Все команды заменены на инлайн-кнопки")
    print("💫 Осталась только команда /start")
    application.run_polling()

if __name__ == "__main__":
    main()
 