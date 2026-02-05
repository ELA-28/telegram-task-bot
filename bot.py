import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import get_settings
from database import (
    init_db, get_or_create_user, create_task, get_user_tasks,
    get_task_by_id, update_task, delete_task, get_user_categories,
    create_category, get_category_by_id, delete_category,
    create_subtask, toggle_subtask, get_user_statistics,
    get_tasks_due_soon, mark_reminder_sent
)
from keyboards import (
    get_main_menu_keyboard, get_task_actions_keyboard, get_tasks_list_keyboard,
    get_priority_keyboard, get_status_keyboard, get_categories_keyboard,
    get_category_actions_keyboard, get_ai_helper_keyboard,
    get_confirmation_keyboard, get_filter_keyboard, get_subtasks_keyboard,
    get_settings_keyboard, get_time_keyboard, get_cancel_keyboard
)
from utils import (
    format_task, format_task_short, format_category, format_datetime,
    format_duration, translate_priority, translate_status, parse_deadline,
    format_statistics, validate_title, calculate_remind_time, get_task_priority_score
)
from ai_helper import AIHelper

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

# Инициализация бота и диспетчера
bot = Bot(token=settings.bot_token)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=settings.timezone)

# ========== FSM States ==========
class TaskStates(StatesGroup):
    title = State()
    description = State()
    priority = State()
    deadline = State()
    category = State()
    estimate = State()

class CategoryStates(StatesGroup):
    name = State()
    color = State()

class SubtaskStates(StatesGroup):
    title = State()

class ReminderStates(StatesGroup):
    custom = State()

class AIStates(StatesGroup):
    question = State()

# ========== Handlers ==========

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )

    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        f"Я ваш персональный бот для управления задачами.\n\n"
        f"🎯 Что я умею:\n"
        f"• 📋 Хранить ваши задачи\n"
        f"• 📊 Отслеживать прогресс\n"
        f"• ⏰ Напоминать о дедлайнах\n"
        f"• 🤷 Помогать с планированием\n"
        f"• 🤔 AI-помощник для советов\n\n"
        f"Используйте меню ниже или команды:\n"
        f"/tasks - список задач\n"
        f"/add - создать задачу\n"
        f"/help - справка",
        reply_markup=get_main_menu_keyboard()
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Обработчик команды /help"""
    help_text = """📚 *Справка по боту*

🔹 *Основные команды:*
/start - Начать работу
/tasks - Мои задачи
/add - Добавить задачу
/stats - Статистика
/categories - Категории
/ai - AI-помощник

🔹 *Управление задачами:*
• Нажмите на задачу для просмотра
• Используйте кнопки для действий
• Устанавливайте приоритеты и дедлайны

🔹 *Категории:*
• Группируйте задачи по категориям
• Фильтруйте по категориям

🔹 *AI-помощник:*
• Получайте советы по продуктивности
• Планируйте день с AI
• Оптимизируйте расписание

🔹 *Напоминания:*
• Бот напомнит о задачах до дедлайна
• Можно настроить自定义 напоминания"""

    await message.answer(help_text, parse_mode="Markdown")


# ========== Task Management ==========

@dp.message(F.text == "📋 Мои задачи")
@dp.message(Command("tasks"))
async def show_tasks(message: types.Message, state: FSMContext):
    """Показать список задач"""
    await state.clear()

    user = await get_or_create_user(telegram_id=message.from_user.id)
    tasks = await get_user_tasks(user.id)

    if not tasks:
        await message.answer(
            "У вас пока нет задач.\n\n"
            "Нажмите ➕ *Добавить задачу* чтобы создать первую!",
            reply_markup=get_main_menu_keyboard()
        )
        return

    # Готовим данные для клавиатуры
    tasks_data = [
        (t.id, t.title, t.status, t.priority)
        for t in sorted(tasks, key=get_task_priority_score)
    ]

    await message.answer(
        f"📋 *Ваши задачи* ({len(tasks)})\n\n"
        f"Выберите задачу для просмотра:",
        reply_markup=get_tasks_list_keyboard(tasks_data)
    )


@dp.callback_query(F.data == "tasks_list")
async def tasks_list_callback(callback: types.CallbackQuery):
    """Обработчик возврата к списку задач"""
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    tasks = await get_user_tasks(user.id)

    if not tasks:
        await callback.message.edit_text(
            "У вас пока нет задач.\n\n"
            "Нажмите ➕ *Добавить задачу* чтобы создать первую!"
        )
        await callback.answer()
        return

    tasks_data = [
        (t.id, t.title, t.status, t.priority)
        for t in sorted(tasks, key=get_task_priority_score)
    ]

    await callback.message.edit_text(
        f"📋 *Ваши задачи* ({len(tasks)})\n\n"
        f"Выберите задачу для просмотра:",
        reply_markup=get_tasks_list_keyboard(tasks_data)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("task_view_"))
async def view_task(callback: types.CallbackQuery):
    """Просмотр задачи"""
    task_id = int(callback.data.split("_")[2])
    user = await get_or_create_user(telegram_id=callback.from_user.id)

    task = await get_task_by_id(task_id, user.id)

    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        format_task(task),
        parse_mode="Markdown",
        reply_markup=get_task_actions_keyboard(task_id)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("task_complete_"))
async def complete_task(callback: types.CallbackQuery):
    """Завершить задачу"""
    task_id = int(callback.data.split("_")[2])
    user = await get_or_create_user(telegram_id=callback.from_user.id)

    task = await update_task(task_id, user.id, status="completed")

    if task:
        await callback.answer("✅ Задача выполнена!")
        await callback.message.edit_text(
            format_task(task),
            parse_mode="Markdown",
            reply_markup=get_task_actions_keyboard(task_id)
        )
    else:
        await callback.answer("Ошибка", show_alert=True)


@dp.callback_query(F.data.startswith("task_progress_"))
async def progress_task(callback: types.CallbackQuery):
    """Перевести задачу в процесс"""
    task_id = int(callback.data.split("_")[2])
    user = await get_or_create_user(telegram_id=callback.from_user.id)

    task = await update_task(task_id, user.id, status="in_progress")

    if task:
        await callback.answer("▶️ Задача в процессе")
        await callback.message.edit_text(
            format_task(task),
            parse_mode="Markdown",
            reply_markup=get_task_actions_keyboard(task_id)
        )
    else:
        await callback.answer("Ошибка", show_alert=True)


@dp.callback_query(F.data.startswith("task_delete_"))
async def delete_task_callback(callback: types.CallbackQuery):
    """Удалить задачу с подтверждением"""
    task_id = int(callback.data.split("_")[2])

    await callback.message.edit_reply_markup(
        reply_markup=get_confirmation_keyboard("delete_task", task_id)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("confirm_delete_task_"))
async def confirm_delete_task(callback: types.CallbackQuery):
    """Подтверждение удаления задачи"""
    task_id = int(callback.data.split("_")[3])
    user = await get_or_create_user(telegram_id=callback.from_user.id)

    success = await delete_task(task_id, user.id)

    if success:
        await callback.answer("🗑️ Задача удалена")
        # Возвращаемся к списку задач
        tasks = await get_user_tasks(user.id)

        if tasks:
            tasks_data = [
                (t.id, t.title, t.status, t.priority)
                for t in sorted(tasks, key=get_task_priority_score)
            ]
            await callback.message.edit_text(
                f"📋 *Ваши задачи* ({len(tasks)})",
                reply_markup=get_tasks_list_keyboard(tasks_data)
            )
        else:
            await callback.message.edit_text(
                "У вас пока нет задач.\n\n"
                "Нажмите ➕ *Добавить задачу* чтобы создать первую!",
                reply_markup=get_main_menu_keyboard()
            )
    else:
        await callback.answer("Ошибка удаления", show_alert=True)


# ========== Add Task ==========

@dp.message(F.text == "➕ Добавить задачу")
@dp.message(Command("add"))
async def add_task_start(message: types.Message, state: FSMContext):
    """Начало добавления задачи"""
    await state.clear()
    await state.set_state(TaskStates.title)

    await message.answer(
        "📝 *Новая задача*\n\n"
        "Введите название задачи:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )


@dp.message(TaskStates.title)
async def add_task_title(message: types.Message, state: FSMContext):
    """Обработка названия задачи"""
    is_valid, title = validate_title(message.text)

    if not is_valid:
        await message.answer(title)  # Здесь title - это сообщение об ошибке
        return

    await state.update_data(title=title)
    await state.set_state(TaskStates.description)

    await message.answer(
        f"✅ Название: *{title}*\n\n"
        f"Введите описание (или отправьте /skip чтобы пропустить):",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )


@dp.message(TaskStates.description)
async def add_task_description(message: types.Message, state: FSMContext):
    """Обработка описания задачи"""
    if message.text == "/skip":
        description = None
    else:
        description = message.text

    await state.update_data(description=description)
    await state.set_state(TaskStates.priority)

    await message.answer(
        "Выберите приоритет задачи:",
        reply_markup=get_priority_keyboard()
    )


@dp.callback_query(TaskStates.priority, F.data.startswith("priority_"))
async def add_task_priority(callback: types.CallbackQuery, state: FSMContext):
    """Обработка приоритета"""
    priority = callback.data.split("_")[1]
    await state.update_data(priority=priority)
    await state.set_state(TaskStates.category)

    # Получаем категории пользователя
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    categories = await get_user_categories(user.id)

    categories_data = [(c.id, c.name, c.color) for c in categories]

    await callback.message.edit_text(
        "Выберите категорию (или /skip чтобы пропустить):",
        reply_markup=get_categories_keyboard(categories_data, add_task=True)
    )
    await callback.answer()


@dp.callback_query(TaskStates.category, F.data.startswith("set_category_"))
async def add_task_category(callback: types.CallbackQuery, state: FSMContext):
    """Обработка категории"""
    category_data = callback.data.split("_")[2]

    if category_data == "none":
        await state.update_data(category_id=None)
    else:
        await state.update_data(category_id=int(category_data))

    await state.set_state(TaskStates.deadline)

    await callback.message.edit_text(
        "Введите дедлайн в формате: DD.MM.YYYY HH:MM\n"
        "Или отправьте /skip чтобы пропустить:",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()


@dp.message(TaskStates.deadline)
async def add_task_deadline(message: types.Message, state: FSMContext):
    """Обработка дедлайна"""
    if message.text == "/skip":
        deadline = None
    else:
        deadline = parse_deadline(message.text)
        if not deadline:
            await message.answer(
                "❌ Неверный формат даты. Попробуйте еще раз или /skip:"
            )
            return

    await state.update_data(deadline=deadline)

    # Создаем задачу
    data = await state.get_data()
    user = await get_or_create_user(telegram_id=message.from_user.id)

    task = await create_task(
        user_id=user.id,
        title=data['title'],
        description=data.get('description'),
        priority=data['priority'],
        category_id=data.get('category_id'),
        deadline=deadline
    )

    await state.clear()

    await message.answer(
        f"✅ *Задача создана!*\n\n{format_task(task)}",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )


# ========== Categories ==========

@dp.message(F.text == "📁 Категории")
@dp.message(Command("categories"))
async def show_categories(message: types.Message):
    """Показать категории"""
    user = await get_or_create_user(telegram_id=message.from_user.id)
    categories = await get_user_categories(user.id)

    if not categories:
        await message.answer(
            "У вас пока нет категорий.\n\n"
            "Создайте первую категорию для организации задач!",
            reply_markup=get_main_menu_keyboard()
        )
        return

    text = "📁 *Ваши категории*\n\n"
    for cat in categories:
        task_count = len(cat.tasks) if hasattr(cat, 'tasks') else 0
        text += f"{format_category(cat)}\n\n"

    # Создаем клавиатуру с категориями
    categories_data = [(c.id, c.name, c.color) for c in categories]

    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=get_categories_keyboard(categories_data)
    )


@dp.callback_query(F.data == "category_new")
async def new_category(callback: types.CallbackQuery, state: FSMContext):
    """Создание новой категории"""
    await state.set_state(CategoryStates.name)
    await callback.message.edit_text(
        "📁 *Создание категории*\n\n"
        "Введите название категории:",
        parse_mode="Markdown"
    )
    await callback.answer()


@dp.message(CategoryStates.name)
async def category_name(message: types.Message, state: FSMContext):
    """Обработка названия категории"""
    name = message.text.strip()

    if len(name) < 2:
        await message.answer("Название слишком короткое (минимум 2 символа)")
        return

    if len(name) > 100:
        await message.answer("Название слишком длинное (максимум 100 символов)")
        return

    user = await get_or_create_user(telegram_id=message.from_user.id)

    category = await create_category(user.id, name)

    await state.clear()

    await message.answer(
        f"✅ Категория *{name}* создана!",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )


# ========== Statistics ==========

@dp.message(F.text == "📊 Статистика")
@dp.message(Command("stats"))
async def show_statistics(message: types.Message):
    """Показать статистику"""
    user = await get_or_create_user(telegram_id=message.from_user.id)
    stats = await get_user_statistics(user.id)

    await message.answer(
        format_statistics(stats),
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )


# ========== AI Helper ==========

@dp.message(F.text == "🎯 Помощник")
@dp.message(Command("ai"))
async def ai_helper_menu(message: types.Message):
    """Меню AI-помощника"""
    await message.answer(
        "🤖 *AI-Помощник*\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=get_ai_helper_keyboard()
    )


@dp.callback_query(F.data == "ai_advice")
async def ai_advice(callback: types.CallbackQuery):
    """Получить совет от AI"""
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    tasks = await get_user_tasks(user.id)

    tasks_data = [
        {
            'title': t.title,
            'priority': t.priority,
            'status': t.status,
            'deadline': t.deadline
        }
        for t in tasks
    ]

    await callback.answer("🤔 Думаю...")
    advice = await AIHelper.get_advice(tasks_data)

    await callback.message.edit_text(
        f"🤷 *Совет дня*\n\n{advice}",
        parse_mode="Markdown"
    )


@dp.callback_query(F.data == "ai_plan_day")
async def ai_plan_day(callback: types.CallbackQuery):
    """Спланировать день с AI"""
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    tasks = await get_user_tasks(user.id)

    tasks_data = [
        {
            'title': t.title,
            'priority': t.priority,
            'status': t.status,
            'deadline': t.deadline,
            'estimated_time': t.estimated_time
        }
        for t in tasks
    ]

    await callback.answer("📅 Планирую...")
    plan = await AIHelper.plan_day(tasks_data)

    await callback.message.edit_text(
        f"📅 *План на день*\n\n{plan}",
        parse_mode="Markdown"
    )


@dp.callback_query(F.data == "ai_analyze")
async def ai_analyze(callback: types.CallbackQuery):
    """Анализ задач с AI"""
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    tasks = await get_user_tasks(user.id)

    tasks_data = [
        {
            'title': t.title,
            'priority': t.priority,
            'status': t.status,
            'deadline': t.deadline
        }
        for t in tasks
    ]

    await callback.answer("📊 Анализирую...")
    analysis = await AIHelper.analyze_tasks(tasks_data)

    await callback.message.edit_text(
        f"📊 *Анализ задач*\n\n{analysis}",
        parse_mode="Markdown"
    )


@dp.callback_query(F.data == "ai_optimize")
async def ai_optimize(callback: types.CallbackQuery):
    """Оптимизация расписания с AI"""
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    tasks = await get_user_tasks(user.id)

    tasks_data = [
        {
            'title': t.title,
            'priority': t.priority,
            'status': t.status,
            'deadline': t.deadline,
            'estimated_time': t.estimated_time
        }
        for t in tasks
    ]

    await callback.answer("⚡ Оптимизирую...")
    optimization = await AIHelper.optimize_schedule(tasks_data)

    await callback.message.edit_text(
        f"⚡ *Оптимизация расписания*\n\n{optimization}",
        parse_mode="Markdown"
    )


# ========== Cancel ==========

@dp.message(F.text == "❌ Отмена")
@dp.message(Command("cancel"))
async def cancel_action(message: types.Message, state: FSMContext):
    """Отмена текущего действия"""
    await state.clear()
    await message.answer(
        "❌ Действие отменено",
        reply_markup=get_main_menu_keyboard()
    )


@dp.callback_query(F.data == "cancel")
async def cancel_callback(callback: types.CallbackQuery, state: FSMContext):
    """Отмена текущего действия (callback)"""
    await state.clear()

    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass

    await callback.answer("❌ Отменено")


# ========== Other ==========

@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    await callback.answer()

    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass

    await callback.message.answer(
        "Главное меню",
        reply_markup=get_main_menu_keyboard()
    )


# ========== Scheduled Tasks ==========

async def check_deadlines():
    """Проверка дедлайнов и отправка напоминаний"""
    tasks = await get_tasks_due_soon(hours=24)

    for task in tasks:
        try:
            user = await get_or_create_user(telegram_id=task.user_id)

            time_left = task.deadline - datetime.now()
            hours_left = int(time_left.total_seconds() / 3600)

            if hours_left <= 2:
                urgency = "⚠️ СРОЧНО! "
                time_str = f"всего {hours_left} час(ов)!"
            else:
                urgency = ""
                time_str = f"через {hours_left} час(ов)"

            message = (
                f"{urgency}⏰ *Напоминание о задаче*\n\n"
                f"{format_task_short(task)}\n\n"
                f"⏰ Дедлайн: {time_str}"
            )

            await bot.send_message(
                chat_id=task.user_id,
                text=message,
                parse_mode="Markdown"
            )

            await mark_reminder_sent(task.id)

        except Exception as e:
            logger.error(f"Error sending reminder for task {task.id}: {e}")


# ========== Main ==========

async def main():
    """Главная функция запуска бота"""
    # Инициализация базы данных
    await init_db()

    # Добавляем задачу на проверку дедлайнов каждый час
    scheduler.add_job(
        check_deadlines,
        "interval",
        hours=1,
        id="check_deadlines"
    )
    scheduler.start()

    # Запуск поллинга
    logger.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
