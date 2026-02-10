from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Optional


# ========== Main Menu ==========
def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню бота"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Мои задачи"), KeyboardButton(text="➕ Добавить задачу")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="🎯 Помощник")],
            [KeyboardButton(text="📁 Категории"), KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие или введите команду..."
    )
    return keyboard


# ========== Task Actions ==========
def get_task_actions_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Клавиатура действий над задачей"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="✅ Выполнить", callback_data=f"task_complete_{task_id}"),
        InlineKeyboardButton(text="⏳ В процессе", callback_data=f"task_progress_{task_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить", callback_data=f"task_edit_{task_id}"),
        InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"task_delete_{task_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="📝 Подзадачи", callback_data=f"subtasks_{task_id}"),
        InlineKeyboardButton(text="⏰ Напоминание", callback_data=f"reminder_{task_id}"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="tasks_list"))

    return builder.as_markup()


def get_tasks_list_keyboard(tasks: List[tuple], page: int = 0, page_size: int = 5) -> InlineKeyboardMarkup:
    """Клавиатура со списком задач"""
    builder = InlineKeyboardBuilder()

    # Добавляем задачи
    for task_id, title, status, priority in tasks[page * page_size:(page + 1) * page_size]:
        priority_emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "urgent": "🔴"}.get(priority, "⚪")
        status_emoji = {"pending": "⏳", "in_progress": "▶️", "completed": "✅"}.get(status, "⏳")

        builder.row(
            InlineKeyboardButton(
                text=f"{status_emoji} {priority_emoji} {title[:40]}...",
                callback_data=f"task_view_{task_id}"
            )
        )

    # Навигация по страницам
    has_prev = page > 0
    has_next = (page + 1) * page_size < len(tasks)

    nav_buttons = []
    if has_prev:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"tasks_page_{page - 1}"))

    nav_buttons.append(InlineKeyboardButton(
        text=f"{page + 1}/{(len(tasks) + page_size - 1) // page_size}",
        callback_data="ignore"
    ))

    if has_next:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"tasks_page_{page + 1}"))

    if nav_buttons:
        builder.row(*nav_buttons)

    # Кнопки фильтрации и действий
    builder.row(
        InlineKeyboardButton(text="✅ Выполненные", callback_data="filter_completed"),
        InlineKeyboardButton(text="📋 Все задачи", callback_data="filter_all")
    )
    builder.row(InlineKeyboardButton(text="📁 По категориям", callback_data="tasks_by_category"))
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="tasks_refresh"))
    builder.row(InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu"))

    return builder.as_markup()


# ========== Priority Selection ==========
def get_priority_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора приоритета"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="🟢 Низкий", callback_data="priority_low"),
        InlineKeyboardButton(text="🟡 Средний", callback_data="priority_medium"),
    )
    builder.row(
        InlineKeyboardButton(text="🟠 Высокий", callback_data="priority_high"),
        InlineKeyboardButton(text="🔴 Срочный", callback_data="priority_urgent"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel"))

    return builder.as_markup()


# ========== Status Selection ==========
def get_status_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора статуса"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="⏳ Ожидает", callback_data="status_pending"),
        InlineKeyboardButton(text="▶️ В процессе", callback_data="status_in_progress"),
    )
    builder.row(
        InlineKeyboardButton(text="✅ Выполнено", callback_data="status_completed"),
        InlineKeyboardButton(text="❌ Отменено", callback_data="status_cancelled"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel"))

    return builder.as_markup()


# ========== Category Selection ==========
def get_categories_keyboard(categories: List[tuple], add_task: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура выбора категории"""
    builder = InlineKeyboardBuilder()

    for cat_id, name, color in categories:
        builder.row(
            InlineKeyboardButton(
                text=f"📁 {name}",
                callback_data=f"category_{cat_id}" if not add_task else f"set_category_{cat_id}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="➕ Новая категория", callback_data="category_new"),
        InlineKeyboardButton(text="❤️ Без категории", callback_data="category_none" if not add_task else "set_category_none"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel"))

    return builder.as_markup()


# ========== Category Actions ==========
def get_category_actions_keyboard(category_id: int) -> InlineKeyboardMarkup:
    """Клавиатура действий над категорией"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"cat_rename_{category_id}"),
        InlineKeyboardButton(text="🎨 Изменить цвет", callback_data=f"cat_color_{category_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"cat_delete_{category_id}"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="categories_list"))

    return builder.as_markup()


# ========== AI Helper ==========
def get_ai_helper_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура AI-помощника"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="🤷 Спросить совет", callback_data="ai_advice"),
        InlineKeyboardButton(text="📅 Спланировать день", callback_data="ai_plan_day"),
    )
    builder.row(
        InlineKeyboardButton(text="🔍 Анализ задач", callback_data="ai_analyze"),
        InlineKeyboardButton(text="⚡ Оптимизация", callback_data="ai_optimize"),
    )
    builder.row(InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu"))

    return builder.as_markup()


# ========== Confirmation ==========
def get_confirmation_keyboard(action: str, item_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}_{item_id}"),
        InlineKeyboardButton(text="❌ Нет", callback_data="cancel"),
    )

    return builder.as_markup()


# ========== Filter Tasks ==========
def get_filter_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура фильтрации задач"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="📋 Все", callback_data="filter_all"),
        InlineKeyboardButton(text="⏳ Ожидающие", callback_data="filter_pending"),
    )
    builder.row(
        InlineKeyboardButton(text="▶️ В процессе", callback_data="filter_progress"),
        InlineKeyboardButton(text="✅ Выполненные", callback_data="filter_completed"),
    )
    builder.row(
        InlineKeyboardButton(text="🔴 Срочные", callback_data="filter_urgent"),
        InlineKeyboardButton(text="📅 Просроченные", callback_data="filter_overdue"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel"))

    return builder.as_markup()


# ========== Subtasks ==========
def get_subtasks_keyboard(subtasks: List[tuple], task_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подзадач"""
    builder = InlineKeyboardBuilder()

    for sub_id, title, is_completed in subtasks:
        emoji = "✅" if is_completed else "⬜"
        builder.row(
            InlineKeyboardButton(
                text=f"{emoji} {title[:40]}",
                callback_data=f"subtask_toggle_{sub_id}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="➕ Добавить подзадачу", callback_data=f"subtask_add_{task_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ К задаче", callback_data=f"task_view_{task_id}"),
    )

    return builder.as_markup()


# ========== Settings ==========
def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура настроек"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="🔔 Уведомления", callback_data="settings_notifications"),
        InlineKeyboardButton(text="🎨 Оформление", callback_data="settings_theme"),
    )
    builder.row(
        InlineKeyboardButton(text="📊 Экспорт данных", callback_data="settings_export"),
        InlineKeyboardButton(text="🗑️ Очистить данные", callback_data="settings_clear"),
    )
    builder.row(InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu"))

    return builder.as_markup()


# ========== Time Selection ==========
def get_time_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора времени для напоминания"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="⏰ Через 1 час", callback_data="remind_1h"),
        InlineKeyboardButton(text="⏰ Через 3 часа", callback_data="remind_3h"),
    )
    builder.row(
        InlineKeyboardButton(text="📅 Завтра", callback_data="remind_1d"),
        InlineKeyboardButton(text="📅 Через 3 дня", callback_data="remind_3d"),
    )
    builder.row(
        InlineKeyboardButton(text="📆 Через неделю", callback_data="remind_1w"),
        InlineKeyboardButton(text="⏱️ Свое время", callback_data="remind_custom"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel"))

    return builder.as_markup()


# ========== Cancel ==========
def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )
    return keyboard
