"""Подключение к SQLite, создание схемы, тестовые данные и резервное копирование."""

from __future__ import annotations

import datetime as dt
import sqlite3
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from italian.models import (
    Base,
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

DEFAULT_DB_PATH = Path("italian_school.sqlite3")


def make_engine(path: Path | str = DEFAULT_DB_PATH) -> Engine:
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _record) -> None:
        # В SQLite проверка внешних ключей по умолчанию выключена.
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


def init_db(engine: Engine, with_demo_data: bool = True) -> sessionmaker[Session]:
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    if with_demo_data:
        with factory() as session:
            if session.scalar(select(Course.id).limit(1)) is None:
                seed(session)
                session.commit()
    return factory


def backup(engine: Engine, target: Path | str) -> None:
    """Резервная копия БД средствами SQLite (онлайн-бэкап)."""
    source_path = engine.url.database
    with sqlite3.connect(source_path) as src, sqlite3.connect(target) as dst:
        src.backup(dst)


def seed(session: Session) -> None:
    courses = [
        Course(
            title="Итальянский для начинающих",
            level=Level.A1,
            hours=48,
            price=Decimal(24000),
        ),
        Course(
            title="Базовый итальянский", level=Level.A2, hours=48, price=Decimal(26000)
        ),
        Course(title="Средний уровень", level=Level.B1, hours=64, price=Decimal(32000)),
        Course(
            title="Разговорный итальянский",
            level=Level.B2,
            hours=64,
            price=Decimal(36000),
        ),
    ]
    teachers = [
        Teacher(
            last_name="Росси", first_name="Марко", phone="+79161234567", is_native=True
        ),
        Teacher(
            last_name="Иванова",
            first_name="Елена",
            phone="+79167654321",
            is_native=False,
        ),
        Teacher(
            last_name="Бьянки",
            first_name="Джулия",
            phone="+79031112233",
            is_native=True,
        ),
    ]
    rooms = [
        Classroom(number="101", capacity=10),
        Classroom(number="102", capacity=8),
        Classroom(number="201", capacity=14),
    ]
    students = [
        Student(
            last_name="Петров",
            first_name="Алексей",
            phone="+79260000001",
            email="petrov@mail.ru",
            birth_date=dt.date(1995, 3, 12),
        ),
        Student(
            last_name="Соколова",
            first_name="Анна",
            phone="+79260000002",
            email="sokolova@yandex.ru",
            birth_date=dt.date(1999, 7, 1),
        ),
        Student(
            last_name="Кузнецов",
            first_name="Игорь",
            phone="+79260000003",
            email="kuznetsov@gmail.com",
            birth_date=dt.date(1988, 11, 23),
        ),
        Student(
            last_name="Морозова",
            first_name="Дарья",
            phone="+79260000004",
            email="morozova@mail.ru",
            birth_date=dt.date(2001, 1, 30),
        ),
        Student(
            last_name="Лебедев",
            first_name="Никита",
            phone="+79260000005",
            email="lebedev@inbox.ru",
            birth_date=dt.date(1993, 5, 17),
        ),
    ]
    groups = [
        Group(
            name="A1-01",
            course=courses[0],
            teacher=teachers[0],
            start_date=dt.date(2026, 9, 7),
        ),
        Group(
            name="A2-01",
            course=courses[1],
            teacher=teachers[1],
            start_date=dt.date(2026, 9, 14),
        ),
        Group(
            name="B1-01",
            course=courses[2],
            teacher=teachers[2],
            start_date=dt.date(2026, 10, 5),
        ),
    ]
    session.add_all(courses + teachers + rooms + students + groups)

    enrollments = [
        Enrollment(
            student=students[0], group=groups[0], enroll_date=dt.date(2026, 9, 1)
        ),
        Enrollment(
            student=students[1], group=groups[0], enroll_date=dt.date(2026, 9, 2)
        ),
        Enrollment(
            student=students[2], group=groups[1], enroll_date=dt.date(2026, 9, 10)
        ),
        Enrollment(
            student=students[3], group=groups[2], enroll_date=dt.date(2026, 9, 28)
        ),
        Enrollment(
            student=students[4], group=groups[2], enroll_date=dt.date(2026, 9, 29)
        ),
        Enrollment(
            student=students[1],
            group=groups[1],
            enroll_date=dt.date(2026, 6, 1),
            status=EnrollmentStatus.FINISHED,
        ),
    ]
    session.add_all(enrollments)

    session.add_all(
        [
            Payment(
                enrollment=enrollments[0],
                pay_date=dt.date(2026, 9, 1),
                amount=Decimal(24000),
            ),
            Payment(
                enrollment=enrollments[1],
                pay_date=dt.date(2026, 9, 2),
                amount=Decimal(12000),
            ),
            Payment(
                enrollment=enrollments[2],
                pay_date=dt.date(2026, 9, 10),
                amount=Decimal(26000),
            ),
            Payment(
                enrollment=enrollments[3],
                pay_date=dt.date(2026, 9, 28),
                amount=Decimal(16000),
            ),
            Payment(
                enrollment=enrollments[5],
                pay_date=dt.date(2026, 6, 1),
                amount=Decimal(26000),
            ),
        ]
    )

    topics = [
        "Знакомство, алфавит",
        "Артикли и существительные",
        "Глагол essere",
        "Глагол avere",
        "Числа и время",
    ]
    for i, topic in enumerate(topics):
        day = dt.date(2026, 10, 19) + dt.timedelta(days=i * 2)
        session.add(
            Lesson(
                group=groups[0],
                classroom=rooms[0],
                lesson_date=day,
                start_time=dt.time(18, 0),
                topic=topic,
            )
        )
        session.add(
            Lesson(
                group=groups[1],
                classroom=rooms[1],
                lesson_date=day,
                start_time=dt.time(19, 30),
                topic=f"A2: урок {i + 1}",
            )
        )
    session.add(
        Lesson(
            group=groups[2],
            classroom=rooms[2],
            lesson_date=dt.date(2026, 10, 20),
            start_time=dt.time(10, 0),
            topic="Passato prossimo",
        )
    )
