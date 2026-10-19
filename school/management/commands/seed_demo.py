"""Тестовые данные и демо-пользователи: python manage.py seed_demo."""

import datetime as dt
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from school.models import (
    Classroom,
    Course,
    Enrollment,
    EnrollmentStatus,
    Group,
    Lesson,
    Level,
    Payment,
    Student,
    Teacher,
)

DEMO_PASSWORD = "italia2026"


class Command(BaseCommand):
    help = "Заполняет пустую БД тестовыми данными и создаёт демо-пользователей."

    def add_arguments(self, parser):
        parser.add_argument(
            "--admin-password", default="admin", help="пароль пользователя admin"
        )

    @transaction.atomic
    def handle(self, *args, admin_password: str, **options):
        if Course.objects.exists():
            self.stdout.write("Данные уже есть — пропускаю.")
            return

        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser(
                "admin", password=admin_password, first_name="Администратор"
            )

        def user(username: str, first: str, last: str) -> User:
            return User.objects.create_user(
                username, password=DEMO_PASSWORD, first_name=first, last_name=last
            )

        today = timezone.localdate()

        courses = [
            Course.objects.create(
                title="Итальянский для начинающих",
                level=Level.A1,
                hours=48,
                price=Decimal(24000),
            ),
            Course.objects.create(
                title="Базовый итальянский",
                level=Level.A2,
                hours=48,
                price=Decimal(26000),
            ),
            Course.objects.create(
                title="Средний уровень", level=Level.B1, hours=64, price=Decimal(32000)
            ),
            Course.objects.create(
                title="Разговорный итальянский",
                level=Level.B2,
                hours=64,
                price=Decimal(36000),
            ),
        ]
        teachers = [
            Teacher.objects.create(
                last_name="Росси",
                first_name="Марко",
                phone="+79161234567",
                is_native=True,
                user=user("rossi", "Марко", "Росси"),
            ),
            Teacher.objects.create(
                last_name="Иванова",
                first_name="Елена",
                phone="+79167654321",
                user=user("ivanova", "Елена", "Иванова"),
            ),
            Teacher.objects.create(
                last_name="Бьянки",
                first_name="Джулия",
                phone="+79031112233",
                is_native=True,
                user=user("bianchi", "Джулия", "Бьянки"),
            ),
        ]
        rooms = [
            Classroom.objects.create(number="101", capacity=10),
            Classroom.objects.create(number="102", capacity=8),
            Classroom.objects.create(number="201", capacity=14),
        ]
        people = [
            ("petrov", "Петров", "Алексей", "petrov@mail.ru", dt.date(1995, 3, 12)),
            ("sokolova", "Соколова", "Анна", "sokolova@yandex.ru", dt.date(1999, 7, 1)),
            (
                "kuznetsov",
                "Кузнецов",
                "Игорь",
                "kuznetsov@gmail.com",
                dt.date(1988, 11, 23),
            ),
            ("morozova", "Морозова", "Дарья", "morozova@mail.ru", dt.date(2001, 1, 30)),
            ("lebedev", "Лебедев", "Никита", "lebedev@inbox.ru", dt.date(1993, 5, 17)),
        ]
        students = [
            Student.objects.create(
                last_name=last,
                first_name=first,
                phone=f"+7926000000{i + 1}",
                email=email,
                birth_date=born,
                user=user(login, first, last),
            )
            for i, (login, last, first, email, born) in enumerate(people)
        ]
        groups = [
            Group.objects.create(
                name="A1-01",
                course=courses[0],
                teacher=teachers[0],
                start_date=today - dt.timedelta(days=42),
            ),
            Group.objects.create(
                name="A2-01",
                course=courses[1],
                teacher=teachers[1],
                start_date=today - dt.timedelta(days=35),
            ),
            Group.objects.create(
                name="B1-01",
                course=courses[2],
                teacher=teachers[2],
                start_date=today - dt.timedelta(days=14),
            ),
        ]

        def enroll(student, group, days_before_start, status=EnrollmentStatus.ACTIVE):
            return Enrollment.objects.create(
                student=student,
                group=group,
                status=status,
                enroll_date=group.start_date - dt.timedelta(days=days_before_start),
            )

        enrollments = [
            enroll(students[0], groups[0], 6),
            enroll(students[1], groups[0], 5),
            enroll(students[2], groups[1], 4),
            enroll(students[3], groups[2], 7),
            enroll(students[4], groups[2], 6),
        ]
        finished = enroll(students[1], groups[1], 100, EnrollmentStatus.FINISHED)

        for enrollment, amount in zip(
            enrollments + [finished],
            [24000, 12000, 26000, 16000, 0, 26000],
            strict=True,
        ):
            if amount:
                Payment.objects.create(
                    enrollment=enrollment,
                    pay_date=enrollment.enroll_date,
                    amount=Decimal(amount),
                )

        topics = [
            "Знакомство, алфавит",
            "Артикли и существительные",
            "Глагол essere",
            "Глагол avere",
            "Числа и время",
        ]
        for i, topic in enumerate(topics):
            day = today + dt.timedelta(days=i * 2)
            Lesson.objects.create(
                group=groups[0],
                room=rooms[0],
                lesson_date=day,
                start_time=dt.time(18, 0),
                topic=topic,
            )
            Lesson.objects.create(
                group=groups[1],
                room=rooms[1],
                lesson_date=day,
                start_time=dt.time(19, 30),
                topic=f"A2: урок {i + 1}",
            )
            Lesson.objects.create(
                group=groups[2],
                room=rooms[2],
                lesson_date=day + dt.timedelta(days=1),
                start_time=dt.time(10, 0),
                topic=f"B1: урок {i + 1}",
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово. Вход: admin / {admin_password}; преподаватели rossi, ivanova, bianchi "
                f"и ученики petrov, sokolova, kuznetsov, morozova, lebedev — пароль {DEMO_PASSWORD}."
            )
        )
