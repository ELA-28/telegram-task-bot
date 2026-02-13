import asyncio
import logging
import io
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import get_settings
from database import (
    init_db, get_or_create_user, create_task, get_user_tasks,
    get_task_by_id, update_task, delete_task, get_user_categories,
    create_category, get_category_by_id, delete_category, update_category,
    create_subtask, toggle_subtask, get_user_statistics,
    get_tasks_due_soon, mark_reminder_sent
)
from keyboards import (
    get_main_menu_keyboard, get_task_actions_keyboard, get_tasks_list_keyboard,
    get_priority_keyboard, get_status_keyboard, get_categories_keyboard,
    get_category_actions_keyboard, get_ai_helper_keyboard,
    get_confirmation_keyboard, get_filter_keyboard, get_subtasks_keyboard,
    get_settings_keyboard, get_time_keyboard, get_cancel_keyboard,
    get_edit_task_keyboard
)
from utils import (
    format_task, format_task_short, format_category, format_datetime,
    format_duration, translate_priority, translate_status, parse_deadline,
    format_statistics, validate_title, calculate_remind_time, get_task_priority_score,
    escape_markdown
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
    rename = State()

class SubtaskStates(StatesGroup):
    title = State()

class ReminderStates(StatesGroup):
    custom = State()

class AIStates(StatesGroup):
    question = State()

class EditTaskStates(StatesGroup):
    title = State()
    description = State()
    priority = State()
    deadline = State()
    category = State()

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

    # Отладочное логирование
    logging.info(f"show_tasks: user_id={user.id}, telegram_id={message.from_user.id}")

    all_tasks = await get_user_tasks(user.id)

    # Отладочное логирование
    logging.info(f"show_tasks: got {len(all_tasks)} tasks from DB")
    for t in all_tasks:
        logging.info(f"  - Task: id={t.id}, title={t.title}, status={t.status}")

    # Показываем только невыполненные задачи
    tasks = [t for t in all_tasks if t.status != "completed"]
    completed_count = len(all_tasks) - len(tasks)

    logging.info(f"show_tasks: filtered {len(tasks)} active tasks, {completed_count} completed")

    if not tasks:
        if completed_count > 0:
            await message.answer(
                f"✅ Все ваши задачи выполнены! ({completed_count})\n\n"
                f"Нажмите ➕ *Добавить задачу* чтобы создать новую!",
                reply_markup=get_main_menu_keyboard()
            )
        else:
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

    completed_text = f"\n✅ Выполненных: {completed_count}" if completed_count > 0 else ""

    await message.answer(
        f"📋 *Активные задачи* ({len(tasks)}){completed_text}\n\n"
        f"Выберите задачу для просмотра:",
        reply_markup=get_tasks_list_keyboard(tasks_data)
    )


@dp.callback_query(F.data == "tasks_list")
async def tasks_list_callback(callback: types.CallbackQuery):
    """Обработчик возврата к списку задач"""
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    all_tasks = await get_user_tasks(user.id)

    # Показываем только невыполненные задачи
    tasks = [t for t in all_tasks if t.status != "completed"]
    completed_count = len(all_tasks) - len(tasks)

    if not tasks:
        if completed_count > 0:
            await callback.message.edit_text(
                f"✅ Все задачи выполнены! ({completed_count})\n\n"
                f"Создайте новую или посмотрите выполненные через фильтр."
            )
        else:
            await callback.message.edit_text(
                "У вас пока нет задач.\n\n"
                "Нажмите ➕ Добавить задачу чтобы создать первую!"
            )
        await callback.answer()
        return

    tasks_data = [
        (t.id, t.title, t.status, t.priority)
        for t in sorted(tasks, key=get_task_priority_score)
    ]

    completed_text = f"\n✅ Выполненных: {completed_count}" if completed_count > 0 else ""

    await callback.message.edit_text(
        f"📋 *Активные задачи* ({len(tasks)}){completed_text}\n\n"
        f"Выберите задачу для просмотра:",
        reply_markup=get_tasks_list_keyboard(tasks_data)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("tasks_page_"))
async def tasks_page_callback(callback: types.CallbackQuery):
    """Переключение страниц в списке задач"""
    page = int(callback.data.split("_")[2])
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    all_tasks = await get_user_tasks(user.id)

    # Показываем только невыполненные задачи
    tasks = [t for t in all_tasks if t.status != "completed"]
    completed_count = len(all_tasks) - len(tasks)

    if not tasks:
        await callback.answer("Нет задач", show_alert=True)
        return

    tasks_data = [
        (t.id, t.title, t.status, t.priority)
        for t in sorted(tasks, key=get_task_priority_score)
    ]

    completed_text = f"\n✅ Выполненных: {completed_count}" if completed_count > 0 else ""

    await callback.message.edit_text(
        f"📋 *Активные задачи* ({len(tasks)}){completed_text}\n\n"
        f"Выберите задачу для просмотра:",
        reply_markup=get_tasks_list_keyboard(tasks_data, page=page)
    )
    await callback.answer()


@dp.callback_query(F.data == "filter_completed")
async def show_completed_tasks(callback: types.CallbackQuery):
    """Показать выполненные задачи"""
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    tasks = await get_user_tasks(user.id, status="completed")

    if not tasks:
        await callback.answer("Нет выполненных задач", show_alert=True)
        return

    tasks_data = [
        (t.id, t.title, t.status, t.priority)
        for t in sorted(tasks, key=get_task_priority_score)
    ]

    await callback.message.edit_text(
        f"✅ *Выполненные задачи* ({len(tasks)})\n\n"
        f"Выберите задачу для просмотра:",
        reply_markup=get_tasks_list_keyboard(tasks_data)
    )
    await callback.answer()


@dp.callback_query(F.data == "filter_all")
async def show_all_tasks(callback: types.CallbackQuery):
    """Показать все задачи"""
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    tasks = await get_user_tasks(user.id)

    if not tasks:
        await callback.message.edit_text("У вас пока нет задач.")
        await callback.answer()
        return

    tasks_data = [
        (t.id, t.title, t.status, t.priority)
        for t in sorted(tasks, key=get_task_priority_score)
    ]

    await callback.message.edit_text(
        f"📋 *Все задачи* ({len(tasks)})\n\n"
        f"Выберите задачу для просмотра:",
        reply_markup=get_tasks_list_keyboard(tasks_data)
    )
    await callback.answer()


@dp.callback_query(F.data == "tasks_by_category")
async def show_tasks_by_category(callback: types.CallbackQuery):
    """Показать задачи по категориям"""
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    tasks = await get_user_tasks(user.id)
    categories = await get_user_categories(user.id)

    if not tasks:
        await callback.answer("Нет задач", show_alert=True)
        return

    # Создаем словарь категорий для быстрого доступа
    category_map = {c.id: c.name for c in categories}

    # Группируем задачи по категориям
    tasks_by_cat = {}
    for task in tasks:
        cat_id = task.category_id
        cat_name = category_map.get(cat_id, "Без категории")

        if cat_name not in tasks_by_cat:
            tasks_by_cat[cat_name] = []
        tasks_by_cat[cat_name].append(task)

    # Формируем текст
    text = "📋 *Задачи по категориям*\n\n"

    # Сортируем категории по названию
    for cat_name in sorted(tasks_by_cat.keys()):
        cat_tasks = tasks_by_cat[cat_name]

        # Считаем задачи по статусу
        total = len(cat_tasks)
        completed = sum(1 for t in cat_tasks if t.status == "completed")
        active = total - completed

        text += f"📁 *{escape_markdown(cat_name)}*\n"
        text += f"   Активных: {active} | Выполнено: {completed}\n"

        # Показываем только активные задачи
        active_tasks = [t for t in cat_tasks if t.status != "completed"]
        for task in sorted(active_tasks, key=get_task_priority_score):
            priority_emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "urgent": "🔴"}.get(task.priority, "⚪")
            text += f"   {priority_emoji} {escape_markdown(task.title)}\n"
            if task.description:
                text += f"      └ {escape_markdown(task.description)}\n"

        text += "\n"

    # Общие итоги
    total_tasks = len(tasks)
    total_completed = sum(1 for t in tasks if t.status == "completed")
    total_active = total_tasks - total_completed

    text = f"📊 *Всего*: {total_active} активных / {total_completed} выполнено\n\n{text}"

    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data == "tasks_refresh")
async def refresh_tasks(callback: types.CallbackQuery):
    """Обновить список задач (показать активные)"""
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    all_tasks = await get_user_tasks(user.id)

    # Показываем только невыполненные задачи
    tasks = [t for t in all_tasks if t.status != "completed"]
    completed_count = len(all_tasks) - len(tasks)

    if not tasks:
        if completed_count > 0:
            await callback.message.edit_text(
                f"✅ Все задачи выполнены! ({completed_count})"
            )
        else:
            await callback.message.edit_text("У вас пока нет задач.")
        await callback.answer()
        return

    tasks_data = [
        (t.id, t.title, t.status, t.priority)
        for t in sorted(tasks, key=get_task_priority_score)
    ]

    completed_text = f"\n✅ Выполненных: {completed_count}" if completed_count > 0 else ""

    await callback.message.edit_text(
        f"📋 *Активные задачи* ({len(tasks)}){completed_text}\n\n"
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

        # Возвращаемся к списку активных задач
        all_tasks = await get_user_tasks(user.id)
        tasks = [t for t in all_tasks if t.status != "completed"]
        completed_count = len(all_tasks) - len(tasks)

        if not tasks:
            await callback.message.edit_text(
                f"✅ Все задачи выполнены! ({completed_count})\n\n"
                f"Нажмите ➕ Добавить задачу чтобы создать новую."
            )
            return

        tasks_data = [
            (t.id, t.title, t.status, t.priority)
            for t in sorted(tasks, key=get_task_priority_score)
        ]

        completed_text = f"\n✅ Выполненных: {completed_count}" if completed_count > 0 else ""

        await callback.message.edit_text(
            f"📋 *Активные задачи* ({len(tasks)}){completed_text}\n\n"
            f"Выберите задачу для просмотра:",
            reply_markup=get_tasks_list_keyboard(tasks_data)
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
        # Возвращаемся к списку активных задач
        all_tasks = await get_user_tasks(user.id)
        tasks = [t for t in all_tasks if t.status != "completed"]
        completed_count = len(all_tasks) - len(tasks)

        if tasks:
            tasks_data = [
                (t.id, t.title, t.status, t.priority)
                for t in sorted(tasks, key=get_task_priority_score)
            ]

            completed_text = f"\n✅ Выполненных: {completed_count}" if completed_count > 0 else ""

            await callback.message.edit_text(
                f"📋 *Активные задачи* ({len(tasks)}){completed_text}\n\n"
                f"Выберите задачу для просмотра:",
                reply_markup=get_tasks_list_keyboard(tasks_data)
            )
        else:
            if completed_count > 0:
                await callback.message.edit_text(
                    f"✅ Все задачи выполнены! ({completed_count})\n\n"
                    f"Нажмите ➕ Добавить задачу чтобы создать новую."
                )
            else:
                await callback.message.edit_text(
                    "У вас пока нет задач.\n\n"
                    "Нажмите ➕ Добавить задачу чтобы создать первую!"
                )
    else:
        await callback.answer("Ошибка удаления", show_alert=True)


@dp.callback_query(F.data.startswith("task_edit_"))
async def edit_task_callback(callback: types.CallbackQuery):
    """Меню редактирования задачи"""
    task_id = int(callback.data.split("_")[2])
    user = await get_or_create_user(telegram_id=callback.from_user.id)

    task = await get_task_by_id(task_id, user.id)

    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        f"✏️ *Редактирование задачи*\n\n"
        f"Выберите поле для изменения:",
        parse_mode="Markdown",
        reply_markup=get_edit_task_keyboard(task_id)
    )
    await callback.answer()


# ========== Edit Task Title ==========
@dp.callback_query(F.data.startswith("edit_title_"))
async def edit_title_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования названия"""
    task_id = int(callback.data.split("_")[2])
    await state.update_data(task_id=task_id)
    await state.set_state(EditTaskStates.title)

    await callback.message.answer(
        "✏️ *Редактирование названия*\n\n"
        "Введите новое название задачи:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()


@dp.message(EditTaskStates.title)
async def edit_title_message(message: types.Message, state: FSMContext):
    """Обработка нового названия"""
    is_valid, title = validate_title(message.text)

    if not is_valid:
        await message.answer(title)
        return

    data = await state.get_data()
    task_id = data.get('task_id')
    user = await get_or_create_user(telegram_id=message.from_user.id)

    task = await update_task(task_id, user.id, title=title)
    await state.clear()

    if task:
        await message.answer(
            f"✅ Название изменено на \"{title}\"!",
            reply_markup=get_main_menu_keyboard()
        )
        # Показываем обновленную задачу
        await message.answer(
            format_task(task),
            parse_mode="Markdown",
            reply_markup=get_task_actions_keyboard(task_id)
        )
    else:
        await message.answer(
            "❌ Ошибка: задача не найдена",
            reply_markup=get_main_menu_keyboard()
        )


# ========== Edit Task Description ==========
@dp.callback_query(F.data.startswith("edit_desc_"))
async def edit_description_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования описания"""
    task_id = int(callback.data.split("_")[2])
    await state.update_data(task_id=task_id)
    await state.set_state(EditTaskStates.description)

    await callback.message.answer(
        "✏️ *Редактирование описания*\n\n"
        "Введите новое описание (или отправьте /skip чтобы очистить):",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()


@dp.message(EditTaskStates.description)
async def edit_description_message(message: types.Message, state: FSMContext):
    """Обработка нового описания"""
    if message.text == "/skip":
        description = None
    else:
        description = message.text

    data = await state.get_data()
    task_id = data.get('task_id')
    user = await get_or_create_user(telegram_id=message.from_user.id)

    task = await update_task(task_id, user.id, description=description)
    await state.clear()

    if task:
        desc_text = f"\"{description}\"" if description else "очищено"
        await message.answer(
            f"✅ Описание {desc_text}!",
            reply_markup=get_main_menu_keyboard()
        )
        # Показываем обновленную задачу
        await message.answer(
            format_task(task),
            parse_mode="Markdown",
            reply_markup=get_task_actions_keyboard(task_id)
        )
    else:
        await message.answer(
            "❌ Ошибка: задача не найдена",
            reply_markup=get_main_menu_keyboard()
        )


# ========== Edit Task Priority ==========
@dp.callback_query(F.data.startswith("edit_priority_"))
async def edit_priority_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования приоритета"""
    task_id = int(callback.data.split("_")[2])
    await state.update_data(task_id=task_id)
    await state.set_state(EditTaskStates.priority)

    await callback.message.answer(
        "✏️ *Редактирование приоритета*\n\n"
        "Выберите новый приоритет:",
        parse_mode="Markdown",
        reply_markup=get_priority_keyboard()
    )
    await callback.answer()


@dp.callback_query(EditTaskStates.priority, F.data.startswith("priority_"))
async def edit_priority_select(callback: types.CallbackQuery, state: FSMContext):
    """Выбор нового приоритета"""
    priority = callback.data.split("_")[1]
    data = await state.get_data()
    task_id = data.get('task_id')
    user = await get_or_create_user(telegram_id=callback.from_user.id)

    task = await update_task(task_id, user.id, priority=priority)
    await state.clear()

    if task:
        priority_text = translate_priority(priority)
        await callback.message.answer(
            f"✅ Приоритет изменен на {priority_text}!",
            reply_markup=get_main_menu_keyboard()
        )
        # Показываем обновленную задачу
        await callback.message.answer(
            format_task(task),
            parse_mode="Markdown",
            reply_markup=get_task_actions_keyboard(task_id)
        )
    else:
        await callback.message.answer(
            "❌ Ошибка: задача не найдена",
            reply_markup=get_main_menu_keyboard()
        )
    await callback.answer()


# ========== Edit Task Deadline ==========
@dp.callback_query(F.data.startswith("edit_deadline_"))
async def edit_deadline_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования дедлайна"""
    task_id = int(callback.data.split("_")[2])
    await state.update_data(task_id=task_id)
    await state.set_state(EditTaskStates.deadline)

    await callback.message.answer(
        "✏️ *Редактирование дедлайна*\n\n"
        "Введите новый дедлайн в формате: DD.MM.YYYY HH:MM\n"
        "Или отправьте /skip чтобы убрать дедлайн:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()


@dp.message(EditTaskStates.deadline)
async def edit_deadline_message(message: types.Message, state: FSMContext):
    """Обработка нового дедлайна"""
    if message.text == "/skip":
        deadline = None
    else:
        deadline = parse_deadline(message.text)
        if not deadline:
            await message.answer(
                "❌ Неверный формат даты. Попробуйте еще раз или /skip:"
            )
            return

    data = await state.get_data()
    task_id = data.get('task_id')
    user = await get_or_create_user(telegram_id=message.from_user.id)

    task = await update_task(task_id, user.id, deadline=deadline)
    await state.clear()

    if task:
        deadline_text = format_datetime(deadline) if deadline else "убран"
        await message.answer(
            f"✅ Дедлайн {deadline_text}!",
            reply_markup=get_main_menu_keyboard()
        )
        # Показываем обновленную задачу
        await message.answer(
            format_task(task),
            parse_mode="Markdown",
            reply_markup=get_task_actions_keyboard(task_id)
        )
    else:
        await message.answer(
            "❌ Ошибка: задача не найдена",
            reply_markup=get_main_menu_keyboard()
        )


# ========== Edit Task Category ==========
@dp.callback_query(F.data.startswith("edit_category_"))
async def edit_category_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования категории"""
    task_id = int(callback.data.split("_")[2])
    await state.update_data(task_id=task_id)
    await state.set_state(EditTaskStates.category)

    # Получаем категории пользователя
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    categories = await get_user_categories(user.id)

    categories_data = [(c.id, c.name, c.color) for c in categories]

    await callback.message.answer(
        "✏️ *Редактирование категории*\n\n"
        "Выберите новую категорию:",
        parse_mode="Markdown",
        reply_markup=get_categories_keyboard(categories_data, add_task=True)
    )
    await callback.answer()


@dp.callback_query(EditTaskStates.category, F.data.startswith("set_category_"))
async def edit_category_select(callback: types.CallbackQuery, state: FSMContext):
    """Выбор новой категории"""
    category_data = callback.data.split("_")[2]

    if category_data == "none":
        category_id = None
    else:
        category_id = int(category_data)

    data = await state.get_data()
    task_id = data.get('task_id')
    user = await get_or_create_user(telegram_id=callback.from_user.id)

    task = await update_task(task_id, user.id, category_id=category_id)
    await state.clear()

    if task:
        category_text = "убрана" if category_id is None else "изменена"
        await callback.message.answer(
            f"✅ Категория {category_text}!",
            reply_markup=get_main_menu_keyboard()
        )
        # Показываем обновленную задачу
        await callback.message.answer(
            format_task(task),
            parse_mode="Markdown",
            reply_markup=get_task_actions_keyboard(task_id)
        )
    else:
        await callback.message.answer(
            "❌ Ошибка: задача не найдена",
            reply_markup=get_main_menu_keyboard()
        )
    await callback.answer()


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

    # Отправляем новое сообщение вместо редактирования
    await callback.message.answer(
        "Выберите категорию:",
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

    # Отправляем новое сообщение вместо редактирования
    await callback.message.answer(
        "Введите дедлайн в формате: DD.MM.YYYY HH:MM\n"
        "Или отправьте /skip чтобы пропустить:",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()


@dp.callback_query(TaskStates.category, F.data == "set_category_none")
async def add_task_no_category(callback: types.CallbackQuery, state: FSMContext):
    """Обработка пропуска категории"""
    await state.update_data(category_id=None)
    await state.set_state(TaskStates.deadline)

    await callback.message.answer(
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

    # Отладочное логирование
    logging.info(f"Creating task: user_id={user.id}, title={data.get('title')}, priority={data.get('priority')}")

    task = await create_task(
        user_id=user.id,
        title=data['title'],
        description=data.get('description'),
        priority=data['priority'],
        category_id=data.get('category_id'),
        deadline=deadline
    )

    # Отладочное логирование
    logging.info(f"Task created: id={task.id}, status={task.status}")

    await state.clear()

    # Показываем короткое подтверждение и сразу список задач
    await message.answer(
        f"✅ Задача \"{task.title}\" создана!",
        reply_markup=get_main_menu_keyboard()
    )

    # Сразу показываем список активных задач
    all_tasks = await get_user_tasks(user.id)
    tasks = [t for t in all_tasks if t.status != "completed"]
    completed_count = len(all_tasks) - len(tasks)

    if not tasks:
        return

    tasks_data = [
        (t.id, t.title, t.status, t.priority)
        for t in sorted(tasks, key=get_task_priority_score)
    ]

    completed_text = f"\n✅ Выполненных: {completed_count}" if completed_count > 0 else ""

    await message.answer(
        f"📋 *Активные задачи* ({len(tasks)}){completed_text}\n\n"
        f"Выберите задачу для просмотра:",
        reply_markup=get_tasks_list_keyboard(tasks_data)
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
    # Сохраняем текущее состояние, чтобы вернуться после создания категории
    current_state = await state.get_state()
    await state.update_data(return_to_task_creation=current_state == TaskStates.category)

    await state.set_state(CategoryStates.name)

    # Отправляем новое сообщение вместо редактирования
    await callback.message.answer(
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

    # Проверяем - нужно ли вернуться к созданию задачи
    data = await state.get_data()
    return_to_task = data.get('return_to_task_creation', False)

    # Очищаем только состояние категории, но сохраняем данные
    current_data = await state.get_data()
    await state.set_state(TaskStates.category)

    if return_to_task:
        # Возвращаемся к выбору категории для задачи
        # Загружаем категории заново
        categories = await get_user_categories(user.id)
        categories_data = [(c.id, c.name, c.color) for c in categories]

        await message.answer(
            f"✅ Категория \"{name}\" создана!\n\nВыберите категорию для задачи:",
            reply_markup=get_categories_keyboard(categories_data, add_task=True)
        )
    else:
        await state.clear()
        await message.answer(
            f"✅ Категория *{name}* создана!",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )


@dp.callback_query(F.data.startswith("category_"))
async def view_category(callback: types.CallbackQuery):
    """Просмотр категории и действий над ней"""
    # Пропускаем callback для создания новой категории
    if callback.data == "category_new":
        return

    category_id = int(callback.data.split("_")[1])
    user = await get_or_create_user(telegram_id=callback.from_user.id)

    category = await get_category_by_id(category_id, user.id)

    if not category:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    task_count = len(category.tasks) if hasattr(category, 'tasks') else 0

    await callback.message.edit_text(
        f"📁 *{category.name}*\n\n"
        f"Задач: {task_count}\n"
        f"Цвет: {category.color}\n\n"
        f"Выберите действие:",
        parse_mode="Markdown",
        reply_markup=get_category_actions_keyboard(category_id)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("cat_delete_"))
async def delete_category_callback(callback: types.CallbackQuery):
    """Удаление категории с подтверждением"""
    category_id = int(callback.data.split("_")[2])

    await callback.message.edit_reply_markup(
        reply_markup=get_confirmation_keyboard("delete_category", category_id)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("confirm_delete_category_"))
async def confirm_delete_category(callback: types.CallbackQuery):
    """Подтверждение удаления категории"""
    category_id = int(callback.data.split("_")[3])
    user = await get_or_create_user(telegram_id=callback.from_user.id)

    success = await delete_category(category_id, user.id)

    if success:
        await callback.answer("🗑️ Категория удалена")

        # Показываем обновленный список категорий
        categories = await get_user_categories(user.id)

        if not categories:
            await callback.message.edit_text(
                "У вас больше нет категорий.\n\n"
                "Создайте новую для организации задач!"
            )
            return

        text = "📁 *Ваши категории*\n\n"
        for cat in categories:
            task_count = len(cat.tasks) if hasattr(cat, 'tasks') else 0
            text += f"📁 *{cat.name}*\nЗадач: {task_count}\n\n"

        categories_data = [(c.id, c.name, c.color) for c in categories]

        await callback.message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=get_categories_keyboard(categories_data)
        )
    else:
        await callback.answer("Ошибка удаления", show_alert=True)


@dp.callback_query(F.data.startswith("cat_rename_"))
async def rename_category_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало переименования категории"""
    category_id = int(callback.data.split("_")[2])
    await state.update_data(category_id=category_id)
    await state.set_state(CategoryStates.rename)

    await callback.message.answer(
        "✏️ Введите новое название категории:",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()


@dp.message(CategoryStates.rename)
async def category_rename(message: types.Message, state: FSMContext):
    """Обработка нового названия категории"""
    name = message.text.strip()

    if len(name) < 2:
        await message.answer("Название слишком короткое (минимум 2 символа)")
        return

    if len(name) > 100:
        await message.answer("Название слишком длинное (максимум 100 символов)")
        return

    data = await state.get_data()
    category_id = data.get('category_id')
    user = await get_or_create_user(telegram_id=message.from_user.id)

    category = await update_category(category_id, user.id, name=name)

    await state.clear()

    if category:
        task_count = len(category.tasks) if hasattr(category, 'tasks') else 0

        await message.answer(
            f"✅ Категория переименована в *{name}*!",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )

        # Показываем обновленную категорию
        await message.answer(
            f"📁 *{category.name}*\n\n"
            f"Задач: {task_count}\n"
            f"Цвет: {category.color}\n\n"
            f"Выберите действие:",
            parse_mode="Markdown",
            reply_markup=get_category_actions_keyboard(category_id)
        )
    else:
        await message.answer(
            "❌ Ошибка: категория не найдена",
            reply_markup=get_main_menu_keyboard()
        )


@dp.callback_query(F.data.startswith("cat_color_"))
async def color_category_callback(callback: types.CallbackQuery, state: FSMContext):
    """Изменение цвета категории"""
    category_id = int(callback.data.split("_")[2])
    await state.update_data(category_id=category_id)
    await state.set_state(CategoryStates.color)

    # Предлагаем выбрать из предустановленных цветов (используем простые коды)
    colors_keyboard = InlineKeyboardBuilder()
    colors = [
        ("🔴 Красный", "red"),
        ("🟠 Оранжевый", "orange"),
        ("🟡 Желтый", "yellow"),
        ("🟢 Зеленый", "green"),
        ("🔵 Голубой", "blue"),
        ("🟣 Фиолетовый", "purple"),
        ("⚫ Черный", "black"),
        ("⚪ Серый", "gray"),
    ]

    for text, color_code in colors:
        colors_keyboard.row(
            InlineKeyboardButton(text=text, callback_data=f"color_{color_code}")
        )

    colors_keyboard.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel"))

    await callback.message.edit_text(
        "🎨 Выберите новый цвет:",
        reply_markup=colors_keyboard.as_markup()
    )
    await callback.answer()


@dp.callback_query(CategoryStates.color, F.data.startswith("color_"))
async def set_category_color(callback: types.CallbackQuery, state: FSMContext):
    """Установка нового цвета категории"""
    # Карта кодов цветов в hex
    color_map = {
        "red": "#e74c3c",
        "orange": "#e67e22",
        "yellow": "#f1c40f",
        "green": "#2ecc71",
        "blue": "#3498db",
        "purple": "#9b59b6",
        "black": "#34495e",
        "gray": "#95a5a6",
    }

    color_code = callback.data.split("_")[1]
    hex_color = color_map.get(color_code, "#3498db")

    data = await state.get_data()
    category_id = data.get('category_id')
    user = await get_or_create_user(telegram_id=callback.from_user.id)

    category = await update_category(category_id, user.id, color=hex_color)

    await state.clear()

    if category:
        task_count = len(category.tasks) if hasattr(category, 'tasks') else 0

        await callback.message.edit_text(
            f"📁 *{category.name}*\n\n"
            f"Задач: {task_count}\n"
            f"Цвет: {category.color}\n\n"
            f"Выберите действие:",
            parse_mode="Markdown",
            reply_markup=get_category_actions_keyboard(category_id)
        )
        await callback.answer("🎨 Цвет изменен!")
    else:
        await callback.answer("Ошибка", show_alert=True)


@dp.callback_query(F.data == "categories_list")
async def categories_list_callback(callback: types.CallbackQuery):
    """Возврат к списку категорий"""
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    categories = await get_user_categories(user.id)

    if not categories:
        await callback.message.edit_text(
            "У вас пока нет категорий.\n\n"
            "Создайте первую категорию для организации задач!"
        )
        await callback.answer()
        return

    text = "📁 *Ваши категории*\n\n"
    for cat in categories:
        task_count = len(cat.tasks) if hasattr(cat, 'tasks') else 0
        text += f"📁 *{cat.name}*\nЗадач: {task_count}\n\n"

    categories_data = [(c.id, c.name, c.color) for c in categories]

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_categories_keyboard(categories_data)
    )
    await callback.answer()


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
