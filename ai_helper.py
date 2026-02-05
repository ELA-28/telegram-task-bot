from openai import AsyncOpenAI
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from config import get_settings

settings = get_settings()
client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None


class AIHelper:
    """AI-помощник для планирования задач"""

    @staticmethod
    async def get_advice(tasks: List[Dict], user_context: str = "") -> str:
        """Получить совет по задачам"""
        if not client:
            return "AI-помощник не настроен. Добавьте OPENAI_API_KEY в .env файл"

        tasks_text = "\n".join([
            f"- {t['title']} (приоритет: {t['priority']}, статус: {t['status']})"
            for t in tasks[:10]
        ])

        prompt = f"""Ты - полезный помощник по продуктивности. Пользователь имеет следующие задачи:

{tasks_text}

Дай короткий, практичный совет (2-3 предложения) по улучшению продуктивности.
{user_context}

Отвечай на русском языке."""

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Ошибка AI: {str(e)}"

    @staticmethod
    async def plan_day(tasks: List[Dict], work_hours: int = 8) -> str:
        """Спланировать день на основе задач"""
        if not client:
            return "AI-помощник не настроен. Добавьте OPENAI_API_KEY в .env файл"

        # Сортируем по приоритету и дедлайну
        pending = [t for t in tasks if t['status'] == 'pending']
        pending.sort(key=lambda x: (
            {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}.get(x['priority'], 4),
            x['deadline'] or datetime.max
        ))

        tasks_text = "\n".join([
            f"- {t['title']} (приоритет: {t['priority']}, время: {t.get('estimated_time', '?')} мин)"
            for t in pending[:15]
        ])

        prompt = f"""Создай оптимальный план дня на {work_hours} часов для следующих задач:

{tasks_text}

Учитывай:
1. Сначала срочные и важные задачи
2. Чередуй сложные и простые задачи
3. Включи короткие перерывы каждые 2 часа
4. Будь реалистичным по времени

Ответ в формате:
📅 План на день:

🌅 Утро (9:00 - 12:00)
- [задача]

🌞 День (13:00 - 17:00)
- [задача]

🌆 Вечер (17:00 - 18:00)
- [задача]

💡 Совет: [короткий совет]"""

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Ошибка планирования: {str(e)}"

    @staticmethod
    async def analyze_tasks(tasks: List[Dict]) -> str:
        """Проанализировать задачи и дать рекомендации"""
        if not client:
            return "AI-помощник не настроен. Добавьте OPENAI_API_KEY в .env файл"

        total = len(tasks)
        completed = len([t for t in tasks if t['status'] == 'completed'])
        pending = len([t for t in tasks if t['status'] == 'pending'])
        overdue = len([t for t in tasks if t.get('deadline') and t['deadline'] < datetime.now() and t['status'] != 'completed'])

        by_priority = {
            'urgent': len([t for t in tasks if t['priority'] == 'urgent' and t['status'] != 'completed']),
            'high': len([t for t in tasks if t['priority'] == 'high' and t['status'] != 'completed']),
            'medium': len([t for t in tasks if t['priority'] == 'medium' and t['status'] != 'completed']),
            'low': len([t for t in tasks if t['priority'] == 'low' and t['status'] != 'completed']),
        }

        prompt = f"""Проанализируй состояние задач пользователя и дай рекомендации:

📊 Статистика:
- Всего задач: {total}
- Выполнено: {completed}
- Ожидает: {pending}
- Просрочено: {overdue}

По приоритету (невыполненные):
- 🔴 Срочные: {by_priority['urgent']}
- 🟠 Высокие: {by_priority['high']}
- 🟡 Средние: {by_priority['medium']}
- 🟢 Низкие: {by_priority['low']}

Дай 3-5 конкретных рекомендаций по улучшению продуктивности на русском языке."""

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Ошибка анализа: {str(e)}"

    @staticmethod
    async def optimize_schedule(tasks: List[Dict], available_hours: int = 8) -> str:
        """Оптимизировать расписание задач"""
        if not client:
            return "AI-помощник не настроен. Добавьте OPENAI_API_KEY в .env файл"

        tasks_with_time = [
            t for t in tasks
            if t['status'] != 'completed' and t.get('estimated_time')
        ]

        total_time = sum(t.get('estimated_time', 0) for t in tasks_with_time)

        tasks_text = "\n".join([
            f"- {t['title']} ({t.get('estimated_time', '?')} мин, приоритет: {t['priority']})"
            for t in tasks_with_time[:10]
        ])

        prompt = f"""Помоги оптимизировать расписание задач:

⏰ Доступное время: {available_hours} часов ({available_hours * 60} минут)
⏱️ Объем задач: {total_time} минут ({round(total_time / 60, 1)} часов)

Задачи:
{tasks_text if tasks_text else "Нет задач с оценкой времени"}

{"⚠️ Внимание: задач больше, чем можно выполнить за доступное время!" if total_time > available_hours * 60 else "✅ Все задачи manageable"}

Дай рекомендации:
1. Какие задачи сделать сегодня
2. Что можно делегировать или отложить
3. Как сгруппировать задачи для эффективности

Отвечай на русском языке, кратко и по делу."""

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Ошибка оптимизации: {str(e)}"

    @staticmethod
    async def break_down_task(task_title: str, task_description: str = "") -> str:
        """Разбить задачу на подзадачи"""
        if not client:
            return "AI-помощник не настроен. Добавьте OPENAI_API_KEY в .env файл"

        prompt = f"""Разбей следующую задачу на конкретные подзадачи:

Задача: {task_title}
Описание: {task_description}

Создай 3-7 подзадач в формате:
1. [подзадача]
2. [подзадача]
...

Каждая подзадача должна быть:
- Конкретной и измеримой
- Выполнимой за 15-60 минут
- Независимой от других (по возможности)

Отвечай только списком подзадач на русском языке."""

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Ошибка разбивки: {str(e)}"

    @staticmethod
    async def estimate_time(task_title: str, task_description: str = "") -> int:
        """Оценить время выполнения задачи в минутах"""
        if not client:
            return 30  # дефолтная оценка

        prompt = f"""Оцени время выполнения этой задачи в минутах.

Задача: {task_title}
Описание: {task_description}

Учитывай:
- Среднюю скорость работы
- Необходимость исследования/обучения
- Возможные задержки

Отвечи только числом (минуты), без дополнительного текста."""

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
            )
            result = response.choices[0].message.content.strip()
            # Извлекаем число из ответа
            import re
            match = re.search(r'\d+', result)
            return int(match.group()) if match else 30
        except Exception:
            return 30
