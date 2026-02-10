"""
Тестовый файл для проверки всех зависимостей бота
Запустите: python test_bot.py
"""

import asyncio
import sys
import os
from datetime import datetime

# Устанавливаем кодировку для Windows
if sys.platform == "win32":
    os.system("chcp 65001 > nul")

# Устанавливаем кодировку вывода
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Импорты
from config import get_settings
from database import (
    init_db, get_session,
    get_or_create_user, create_task, get_user_tasks, get_task_by_id
)
from models import User, Task, Base


async def test_database_connection():
    """Тест 1: Подключение к базе данных"""
    print("🔍 Тест 1: Подключение к базе данных...")
    try:
        await init_db()
        print("   ✅ База данных инициализирована")
        return True
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return False


async def test_create_user():
    """Тест 2: Создание пользователя"""
    print("\n🔍 Тест 2: Создание пользователя...")
    try:
        user = await get_or_create_user(
            telegram_id=123456,
            username="test_user",
            first_name="Test",
            last_name="User"
        )
        print(f"   ✅ Пользователь создан: ID={user.id}, telegram_id={user.telegram_id}")
        return user
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_create_task(user):
    """Тест 3: Создание задачи"""
    print("\n🔍 Тест 3: Создание задачи...")
    try:
        task = await create_task(
            user_id=user.id,
            title="Тестовая задача",
            description="Описание тестовой задачи",
            priority="high"
        )
        print(f"   ✅ Задача создана: ID={task.id}, title={task.title}, status={task.status}")
        return task
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_get_tasks(user):
    """Тест 4: Получение задач пользователя"""
    print("\n🔍 Тест 4: Получение задач пользователя...")
    try:
        tasks = await get_user_tasks(user.id)
        print(f"   ✅ Получено задач: {len(tasks)}")
        for task in tasks:
            print(f"      - {task.title} (status={task.status}, priority={task.priority})")
        return tasks
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return []


async def test_get_task_by_id(user, task):
    """Тест 5: Получение задачи по ID"""
    print("\n🔍 Тест 5: Получение задачи по ID...")
    try:
        found_task = await get_task_by_id(task.id, user.id)
        if found_task:
            print(f"   ✅ Задача найдена: {found_task.title}, статус={found_task.status}")
            print(f"      Категория загружена: {found_task.category is not None}")
            print(f"      Подзадачи загружены: {len(found_task.subtasks) if found_task.subtasks else 0}")
        else:
            print("   ❌ Задача не найдена")
        return found_task
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_filter_tasks(user):
    """Тест 6: Фильтрация задач по статусу"""
    print("\n🔍 Тест 6: Фильтрация задач по статусу...")
    try:
        # Создадим выполненную задачу
        completed_task = await create_task(
            user_id=user.id,
            title="Выполненная задача",
            priority="low"
        )
        # Обновим статус
        from database import update_task
        completed_task = await update_task(completed_task.id, user.id, status="completed")

        # Получим только активные
        all_tasks = await get_user_tasks(user.id)
        active_tasks = [t for t in all_tasks if t.status != "completed"]
        completed_tasks = [t for t in all_tasks if t.status == "completed"]

        print(f"   ✅ Всего задач: {len(all_tasks)}")
        print(f"   ✅ Активных: {len(active_tasks)}")
        print(f"   ✅ Выполненных: {len(completed_tasks)}")
        return True
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_check_raw_data():
    """Тест 7: Проверка сырых данных в базе"""
    print("\n🔍 Тест 7: Проверка сырых данных в базе...")
    try:
        from sqlalchemy import select, text
        async with get_session() as session:
            # Проверка через raw SQL
            result = await session.execute(text("SELECT id, title, status FROM tasks"))
            rows = result.fetchall()
            print(f"   ✅ Сырые данные из БД ({len(rows)} строк):")
            for row in rows:
                print(f"      ID={row[0]}, title={row[1]}, status={row[2]}")
        return True
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Главная функция тестирования"""
    print("=" * 60)
    print("🧪 ТЕСТИРОВАНИЕ БОТА")
    print("=" * 60)

    settings = get_settings()
    print(f"\n⚙️ Настройки:")
    print(f"   BOT_TOKEN: {'✅' if settings.bot_token else '❌'} {settings.bot_token[:20]}...")
    print(f"   DATABASE_URL: {settings.database_url}")
    print(f"   TIMEZONE: {settings.timezone}")

    # Тест 1: Подключение к БД
    if not await test_database_connection():
        print("\n❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось подключиться к БД")
        return

    # Тест 2: Создание пользователя
    user = await test_create_user()
    if not user:
        print("\n❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось создать пользователя")
        return

    # Тест 3: Создание задачи
    task = await test_create_task(user)
    if not task:
        print("\n❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось создать задачу")
        return

    # Тест 4: Получение задач
    tasks = await test_get_tasks(user)
    if not tasks:
        print("\n⚠️  ПРЕДУПРЕЖДЕНИЕ: Задачи не загружаются")

    # Тест 5: Получение задачи по ID
    await test_get_task_by_id(user, task)

    # Тест 6: Фильтрация
    await test_filter_tasks(user)

    # Тест 7: Сырые данные
    await test_check_raw_data()

    print("\n" + "=" * 60)
    print("🏁 ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
