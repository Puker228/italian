"""Роли пользователей: администратор, преподаватель, ученик (ТЗ, ЛР 1)."""

from __future__ import annotations

from enum import StrEnum

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.http import HttpRequest


class Role(StrEnum):
    ADMIN = "Администратор"
    TEACHER = "Преподаватель"
    STUDENT = "Ученик"


def get_role(user: AbstractBaseUser | AnonymousUser) -> Role | None:
    if not user.is_authenticated:
        return None
    if user.is_staff:
        return Role.ADMIN
    if hasattr(user, "teacher"):
        return Role.TEACHER
    if hasattr(user, "student"):
        return Role.STUDENT
    return None


def role_context(request: HttpRequest) -> dict:
    """Контекст-процессор: роль и пункты меню в каждом шаблоне."""
    from school.entities import ENTITIES

    role = get_role(request.user)
    menu = [(e.slug, e.title_for(role)) for e in ENTITIES.values() if role in e.access]
    return {"role": role, "is_admin": role == Role.ADMIN, "menu": menu}
