"""Todo serialization and repeat-date helpers."""

from datetime import datetime, timedelta
from calendar import monthrange

from fastapi import HTTPException

MAX_REPEAT_DAYS = 3650


def normalize_repeat(value):
    """Accept legacy strings and validate structured repeat settings."""
    if not value:
        return {"type": "none"}
    if isinstance(value, str):
        value = {"type": value}
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="반복 설정이 올바르지 않습니다.")
    repeat_type = value.get("type", "none")
    if repeat_type not in ("none", "daily", "weekly", "monthly", "interval"):
        raise HTTPException(status_code=400, detail="지원하지 않는 반복 주기입니다.")
    result = {"type": repeat_type}
    if repeat_type == "weekly":
        days = value.get("days", [])
        weekdays = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        if not isinstance(days, list) or any(day not in weekdays for day in days):
            raise HTTPException(status_code=400, detail="반복 요일이 올바르지 않습니다.")
        result["days"] = [day for day in weekdays if day in days]
    if repeat_type == "interval":
        days = value.get("value", 1)
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_REPEAT_DAYS:
            raise HTTPException(status_code=400, detail=f"반복 간격은 1~{MAX_REPEAT_DAYS}일이어야 합니다.")
        result["value"] = days
    return result


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
    """Return the next date, or a recoverable client error at date limits."""
    try:
        return _add_interval(current_deadline, repeat_cycle)
    except (OverflowError, ValueError):
        raise HTTPException(400, '다음 반복 날짜가 지원 범위를 벗어납니다. 마감일이나 반복 설정을 변경해주세요.')


def _add_interval(current_deadline: datetime, repeat_cycle: dict):
    repeat_cycle = normalize_repeat(repeat_cycle)
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
        year = current_deadline.year + (current_deadline.month == 12)
        month = current_deadline.month % 12 + 1
        day = min(current_deadline.day, monthrange(year, month)[1])
        return current_deadline.replace(year=year, month=month, day=day)

    return None
