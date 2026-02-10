from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload
from sqlalchemy import select, and_, or_, func
from contextlib import asynccontextmanager
from typing import Optional, List
from datetime import datetime

from models import Base, User, Task, Category, Subtask, Reminder
from config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """Инициализация базы данных - создание всех таблиц"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def reset_db():
    """Полный сброс базы данных - удалить и создать все таблицы"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session():
    """Контекстный менеджер для работы с сессией"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ========== User Operations ==========

async def get_or_create_user(telegram_id: int, username: str = None,
                             first_name: str = None, last_name: str = None) -> User:
    """Получить или создать пользователя"""
    async with get_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            session.add(user)
            await session.flush()
            await session.refresh(user)

        return user


async def get_user_by_telegram_id(telegram_id: int) -> Optional[User]:
    """Получить пользователя по telegram_id"""
    async with get_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()


# ========== Task Operations ==========

async def create_task(user_id: int, title: str, description: str = None,
                      priority: str = "medium", category_id: int = None,
                      deadline: datetime = None, estimated_time: int = None) -> Task:
    """Создать новую задачу"""
    from sqlalchemy.orm import selectinload
    async with get_session() as session:
        task = Task(
            user_id=user_id,
            title=title,
            description=description,
            priority=priority,
            category_id=category_id,
            deadline=deadline,
            estimated_time=estimated_time,
        )
        session.add(task)
        await session.flush()
        # Загружаем связанные данные перед refresh
        await session.refresh(task, attribute_names=['category', 'subtasks'])
        return task


async def get_user_tasks(user_id: int, status: str = None,
                         category_id: int = None) -> List[Task]:
    """Получить задачи пользователя с фильтрацией"""
    from sqlalchemy.orm import selectinload
    async with get_session() as session:
        query = select(Task).options(
            selectinload(Task.category),
            selectinload(Task.subtasks)
        ).where(Task.user_id == user_id)

        if status:
            query = query.where(Task.status == status)
        if category_id:
            query = query.where(Task.category_id == category_id)

        query = query.order_by(Task.created_at.desc())

        result = await session.execute(query)
        return result.scalars().all()


async def get_task_by_id(task_id: int, user_id: int) -> Optional[Task]:
    """Получить задачу по ID с проверкой владельца"""
    from sqlalchemy.orm import selectinload
    async with get_session() as session:
        result = await session.execute(
            select(Task)
            .options(
                selectinload(Task.category),
                selectinload(Task.subtasks)
            )
            .where(
                and_(Task.id == task_id, Task.user_id == user_id)
            )
        )
        return result.scalar_one_or_none()


async def update_task(task_id: int, user_id: int, **kwargs) -> Optional[Task]:
    """Обновить задачу"""
    async with get_session() as session:
        result = await session.execute(
            select(Task).where(
                and_(Task.id == task_id, Task.user_id == user_id)
            )
        )
        task = result.scalar_one_or_none()

        if task:
            for key, value in kwargs.items():
                if hasattr(task, key) and value is not None:
                    setattr(task, key, value)

            if kwargs.get('status') == 'completed' and not task.completed_at:
                task.completed_at = datetime.utcnow()

            await session.flush()
            await session.refresh(task)

        return task


async def delete_task(task_id: int, user_id: int) -> bool:
    """Удалить задачу"""
    async with get_session() as session:
        result = await session.execute(
            select(Task).where(
                and_(Task.id == task_id, Task.user_id == user_id)
            )
        )
        task = result.scalar_one_or_none()

        if task:
            await session.delete(task)
            return True

        return False


async def get_tasks_with_reminders() -> List[Task]:
    """Получить задачи для которых нужно отправить напоминания"""
    async with get_session() as session:
        result = await session.execute(
            select(Task).join(Reminder).where(
                and_(
                    Reminder.is_sent == False,
                    Reminder.remind_at <= datetime.utcnow()
                )
            )
        )
        return result.scalars().all()


async def get_tasks_due_soon(hours: int = 24) -> List[Task]:
    """Получить задачи, срок которых истекает в ближайшие часы"""
    from datetime import timedelta

    deadline_threshold = datetime.utcnow() + timedelta(hours=hours)

    async with get_session() as session:
        result = await session.execute(
            select(Task).where(
                and_(
                    Task.status == "pending",
                    Task.deadline.isnot(None),
                    Task.deadline <= deadline_threshold,
                    Task.reminder_sent == False
                )
            )
        )
        return result.scalars().all()


async def mark_reminder_sent(task_id: int):
    """Отметить напоминание как отправленное"""
    async with get_session() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if task:
            task.reminder_sent = True


# ========== Category Operations ==========

async def create_category(user_id: int, name: str, color: str = "#3498db") -> Category:
    """Создать категорию"""
    async with get_session() as session:
        category = Category(user_id=user_id, name=name, color=color)
        session.add(category)
        await session.flush()
        await session.refresh(category)
        return category


async def get_user_categories(user_id: int) -> List[Category]:
    """Получить категории пользователя"""
    from sqlalchemy.orm import selectinload
    async with get_session() as session:
        result = await session.execute(
            select(Category)
            .options(selectinload(Category.tasks))
            .where(Category.user_id == user_id)
            .order_by(Category.name)
        )
        return result.scalars().all()


async def get_category_by_id(category_id: int, user_id: int) -> Optional[Category]:
    """Получить категорию по ID с задачами"""
    async with get_session() as session:
        result = await session.execute(
            select(Category)
            .options(selectinload(Category.tasks))
            .where(
                and_(Category.id == category_id, Category.user_id == user_id)
            )
        )
        return result.scalar_one_or_none()


async def delete_category(category_id: int, user_id: int) -> bool:
    """Удалить категорию"""
    async with get_session() as session:
        result = await session.execute(
            select(Category).where(
                and_(Category.id == category_id, Category.user_id == user_id)
            )
        )
        category = result.scalar_one_or_none()

        if category:
            await session.delete(category)
            return True

        return False


async def update_category(category_id: int, user_id: int, **kwargs) -> Optional[Category]:
    """Обновить категорию с задачами"""
    async with get_session() as session:
        result = await session.execute(
            select(Category)
            .options(selectinload(Category.tasks))
            .where(
                and_(Category.id == category_id, Category.user_id == user_id)
            )
        )
        category = result.scalar_one_or_none()

        if category:
            for key, value in kwargs.items():
                if hasattr(category, key) and value is not None:
                    setattr(category, key, value)

            await session.flush()
            await session.refresh(category)

        return category


# ========== Subtask Operations ==========

async def create_subtask(task_id: int, title: str) -> Subtask:
    """Создать подзадачу"""
    async with get_session() as session:
        subtask = Subtask(task_id=task_id, title=title)
        session.add(subtask)
        await session.flush()
        await session.refresh(subtask)
        return subtask


async def toggle_subtask(subtask_id: int) -> Optional[Subtask]:
    """Переключить статус подзадачи"""
    async with get_session() as session:
        result = await session.execute(select(Subtask).where(Subtask.id == subtask_id))
        subtask = result.scalar_one_or_none()

        if subtask:
            subtask.is_completed = not subtask.is_completed
            await session.flush()
            await session.refresh(subtask)

        return subtask


# ========== Statistics ==========

async def get_user_statistics(user_id: int) -> dict:
    """Получить статистику пользователя"""
    async with get_session() as session:
        total = await session.execute(
            select(func.count(Task.id)).where(Task.user_id == user_id)
        )
        total_tasks = total.scalar() or 0

        completed = await session.execute(
            select(func.count(Task.id)).where(
                and_(Task.user_id == user_id, Task.status == "completed")
            )
        )
        completed_tasks = completed.scalar() or 0

        pending = await session.execute(
            select(func.count(Task.id)).where(
                and_(Task.user_id == user_id, Task.status == "pending")
            )
        )
        pending_tasks = pending.scalar() or 0

        overdue = await session.execute(
            select(func.count(Task.id)).where(
                and_(
                    Task.user_id == user_id,
                    Task.status == "pending",
                    Task.deadline < datetime.utcnow()
                )
            )
        )
        overdue_tasks = overdue.scalar() or 0

        return {
            "total": total_tasks,
            "completed": completed_tasks,
            "pending": pending_tasks,
            "overdue": overdue_tasks,
            "completion_rate": round(completed_tasks / total_tasks * 100, 1) if total_tasks > 0 else 0
        }
