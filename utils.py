from datetime import datetime, timedelta
from typing import Optional
import pytz


def format_task(task) -> str:
    """Отформатировать задачу для отображения"""
    priority_emoji = {
        "low": "🟢",
        "medium": "🟡",
        "high": "🟠",
        "urgent": "🔴"
    }

    status_emoji = {
        "pending": "⏳",
        "in_progress": "▶️",
        "completed": "✅",
        "cancelled": "❌"
    }

    emoji_priority = priority_emoji.get(task.priority, "⚪")
    emoji_status = status_emoji.get(task.status, "⏳")

    lines = [
        f"{emoji_status} *{task.title}*",
        "",
        f"📊 Приоритет: {emoji_priority} {translate_priority(task.priority)}",
        f"📋 Статус: {translate_status(task.status)}",
    ]

    if task.description:
        lines.append(f"📝 Описание: {task.description}")

    if task.deadline:
        deadline_str = format_datetime(task.deadline)
        is_overdue = task.deadline < datetime.now(pytz.UTC) and task.status != "completed"
        overdue_text = " ⚠️ *ПРОСРОЧЕНО*" if is_overdue else ""
        lines.append(f"⏰ Дедлайн: {deadline_str}{overdue_text}")

    if task.estimated_time:
        lines.append(f"⏱️ Оценка времени: {format_duration(task.estimated_time)}")

    if task.category:
        lines.append(f"📁 Категория: {task.category.name}")

    # Подзадачи
    if task.subtasks:
        completed_subtasks = sum(1 for s in task.subtasks if s.is_completed)
        total_subtasks = len(task.subtasks)
        lines.append(f"✓ Подзадачи: {completed_subtasks}/{total_subtasks}")

    # Дата создания
    lines.append(f"📅 Создано: {format_datetime(task.created_at)}")

    return "\n".join(lines)


def format_task_short(task) -> str:
    """Краткое форматирование задачи для списков"""
    priority_emoji = {
        "low": "🟢",
        "medium": "🟡",
        "high": "🟠",
        "urgent": "🔴"
    }

    status_emoji = {
        "pending": "⏳",
        "in_progress": "▶️",
        "completed": "✅",
        "cancelled": "❌"
    }

    emoji_priority = priority_emoji.get(task.priority, "⚪")
    emoji_status = status_emoji.get(task.status, "⏳")

    title = task.title[:50] + "..." if len(task.title) > 50 else task.title

    deadline_str = ""
    if task.deadline:
        deadline_str = f" 📅 {format_datetime_short(task.deadline)}"

    return f"{emoji_status} {emoji_priority} *{title}*{deadline_str}"


def format_category(category) -> str:
    """Отформатировать категорию"""
    task_count = len(category.tasks) if hasattr(category, 'tasks') else 0

    return f"📁 *{category.name}*\n" \
           f"Задач: {task_count}\n" \
           f"Цвет: {category.color}"


def format_datetime(dt: datetime) -> str:
    """Отформатировать дату и время"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.UTC)
    return dt.strftime("%d.%m.%Y %H:%M")


def format_datetime_short(dt: datetime) -> str:
    """Краткое форматирование даты"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.UTC)

    now = datetime.now(pytz.UTC)
    diff = dt - now

    if diff.days == 0:
        return "сегодня"
    elif diff.days == 1:
        return "завтра"
    elif diff.days == -1:
        return "вчера"
    elif diff.days < -1:
        return f"{abs(diff.days)} дн. назад"
    elif diff.days < 7:
        return f"через {diff.days} дн."
    else:
        return dt.strftime("%d.%m")


def format_duration(minutes: int) -> str:
    """Отформатировать длительность"""
    if minutes < 60:
        return f"{minutes} мин"
    elif minutes < 1440:
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}ч {mins}мин" if mins else f"{hours}ч"
    else:
        days = minutes // 1440
        hours = (minutes % 1440) // 60
        return f"{days}д {hours}ч" if hours else f"{days}д"


def translate_priority(priority: str) -> str:
    """Перевести приоритет"""
    translations = {
        "low": "Низкий",
        "medium": "Средний",
        "high": "Высокий",
        "urgent": "Срочный"
    }
    return translations.get(priority, priority)


def translate_status(status: str) -> str:
    """Перевести статус"""
    translations = {
        "pending": "Ожидает",
        "in_progress": "В процессе",
        "completed": "Выполнено",
        "cancelled": "Отменено"
    }
    return translations.get(status, status)


def parse_deadline(text: str) -> Optional[datetime]:
    """Парсить дедлайн из текста"""
    from dateutil import parser
    import pytz

    try:
        dt = parser.parse(text, fuzzy=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=pytz.UTC)
        return dt
    except Exception:
        return None


def format_statistics(stats: dict) -> str:
    """Отформатировать статистику"""
    completion_rate = stats.get("completion_rate", 0)

    return f"""📊 *Ваша статистика*

✅ Выполнено: {stats.get('completed', 0)}
⏳ Ожидающих: {stats.get('pending', 0)}
⚠️ Просроченных: {stats.get('overdue', 0)}
📋 Всего задач: {stats.get('total', 0)}

📈 Эффективность: {completion_rate}%"""


def validate_title(title: str) -> tuple[bool, str]:
    """Проверить валидность заголовка задачи"""
    title = title.strip()

    if not title:
        return False, "Заголовок не может быть пустым"

    if len(title) < 3:
        return False, "Заголовок слишком короткий (минимум 3 символа)"

    if len(title) > 255:
        return False, "Заголовок слишком длинный (максимум 255 символов)"

    return True, title


def calculate_remind_time(deadline: datetime) -> datetime:
    """Рассчитать время напоминания (за 2 часа до дедлайна)"""
    return deadline - timedelta(hours=2)


def get_task_priority_score(task) -> int:
    """Получить оценку приоритета задачи для сортировки"""
    priority_scores = {
        "urgent": 0,
        "high": 1,
        "medium": 2,
        "low": 3
    }

    score = priority_scores.get(task.priority, 2) * 1000

    # Если есть дедлайн, учитываем его
    if task.deadline:
        days_until = (task.deadline - datetime.now(pytz.UTC)).days
        score += max(0, min(days_until, 30)) * 10

    # Задачи в процессе имеют больший приоритет
    if task.status == "in_progress":
        score -= 5

    return score
