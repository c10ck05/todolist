"""Todo serialization and repeat-date helpers."""

from datetime import datetime, timedelta


def todo_dict(todo, subtasks=None):
    return {
        "id": todo.id,
        "content": todo.todo,
        "completed": todo.completed,
        "deadline": todo.deadline.isoformat() if todo.deadline else None,
        "category": todo.category,
        "repeat": todo.repeat_cycle,
        "priority": todo.priority,
        "detail": todo.detail,
        "sort_order": todo.sort_order,
        "subtasks": subtasks if subtasks is not None else [],
    }


def subtask_dict(subtask):
    return {"id": subtask.id, "content": subtask.content, "completed": subtask.completed}


def add_interval(current_deadline: datetime, repeat_cycle: dict):
    if not repeat_cycle:
        return None

    repeat_type = repeat_cycle.get("type")
    if repeat_type == "daily":
        return current_deadline + timedelta(days=1)
    if repeat_type == "interval":
        days_to_add = int(repeat_cycle.get("value", 1))
        return current_deadline + timedelta(days=days_to_add)
    if repeat_type == "weekly":
        target_days_str = repeat_cycle.get("days", [])
        if not target_days_str:
            return current_deadline + timedelta(days=7)

        day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
        target_days = [day_map[day] for day in target_days_str if day in day_map]
        current_weekday = current_deadline.weekday()
        days_ahead = []
        for target_day in target_days:
            difference = (target_day - current_weekday) % 7
            days_ahead.append(difference or 7)
        return current_deadline + timedelta(days=min(days_ahead))
    if repeat_type == "monthly":
        return current_deadline + timedelta(days=30)

    return None
