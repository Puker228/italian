"""ORM-модели ИС «Школа изучения итальянского языка».

Таблицы повторяют физическую модель из ЛР 4 (study_group, enrollment, ...),
методы классов — диаграмму классов из ЛР 9.
"""

from __future__ import annotations

import datetime as dt
import enum
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


class Level(enum.StrEnum):
    """Уровни владения языком (перечисление Level из ЛР 9)."""

    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class EnrollmentStatus(enum.StrEnum):
    ACTIVE = "обучается"
    FINISHED = "завершил"
    EXPELLED = "отчислен"


class Person:
    """Абстрактный класс Person: общие атрибуты слушателя и преподавателя."""

    last_name: Mapped[str] = mapped_column(String(50))
    first_name: Mapped[str] = mapped_column(String(50))
    phone: Mapped[str | None] = mapped_column(String(20))

    def get_full_name(self) -> str:
        return f"{self.last_name} {self.first_name}"

    def __str__(self) -> str:
        return self.get_full_name()


class Student(Person, Base):
    __tablename__ = "student"

    id: Mapped[int] = mapped_column("student_id", Integer, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(100))
    birth_date: Mapped[dt.date | None] = mapped_column(Date)

    enrollments: Mapped[list[Enrollment]] = relationship(back_populates="student")

    def enroll(self, group: Group) -> Enrollment:
        return group.add_student(self)

    def get_debt(self) -> Decimal:
        return sum(
            (
                e.get_debt()
                for e in self.enrollments
                if e.status == EnrollmentStatus.ACTIVE
            ),
            Decimal(0),
        )


class Teacher(Person, Base):
    __tablename__ = "teacher"

    id: Mapped[int] = mapped_column("teacher_id", Integer, primary_key=True)
    is_native: Mapped[bool] = mapped_column("native", Boolean, default=False)

    groups: Mapped[list[Group]] = relationship(back_populates="teacher")

    def get_schedule(self) -> list[Lesson]:
        lessons = [lesson for g in self.groups for lesson in g.lessons]
        return sorted(lessons, key=lambda x: (x.lesson_date, x.start_time))


class Course(Base):
    __tablename__ = "course"
    __table_args__ = (
        CheckConstraint("hours > 0", name="ck_course_hours"),
        CheckConstraint("price >= 0", name="ck_course_price"),
    )

    id: Mapped[int] = mapped_column("course_id", Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    level: Mapped[Level] = mapped_column(Enum(Level, native_enum=False, length=2))
    hours: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    groups: Mapped[list[Group]] = relationship(back_populates="course")

    def get_groups(self) -> list[Group]:
        return list(self.groups)

    def __str__(self) -> str:
        return f"{self.title} ({self.level})"


class Classroom(Base):
    __tablename__ = "classroom"
    __table_args__ = (CheckConstraint("capacity > 0", name="ck_classroom_capacity"),)

    id: Mapped[int] = mapped_column("room_id", Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(10), unique=True)
    capacity: Mapped[int] = mapped_column(Integer)

    lessons: Mapped[list[Lesson]] = relationship(back_populates="classroom")

    def is_free(
        self, date: dt.date, time: dt.time, exclude_id: int | None = None
    ) -> bool:
        return not any(
            les.lesson_date == date and les.start_time == time and les.id != exclude_id
            for les in self.lessons
        )

    def __str__(self) -> str:
        return f"ауд. {self.number}"


class Group(Base):
    __tablename__ = "study_group"

    id: Mapped[int] = mapped_column("group_id", Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    course_id: Mapped[int] = mapped_column(ForeignKey("course.course_id"))
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teacher.teacher_id"))
    start_date: Mapped[dt.date] = mapped_column(Date)

    course: Mapped[Course] = relationship(back_populates="groups")
    teacher: Mapped[Teacher] = relationship(back_populates="groups")
    enrollments: Mapped[list[Enrollment]] = relationship(back_populates="group")
    # Композиция Group — Lesson: занятия удаляются вместе с группой.
    lessons: Mapped[list[Lesson]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )

    def add_student(self, student: Student) -> Enrollment:
        enrollment = Enrollment(
            student=student,
            group=self,
            enroll_date=dt.date.today(),
            status=EnrollmentStatus.ACTIVE,
        )
        return enrollment

    def get_students(self) -> list[Student]:
        return [
            e.student for e in self.enrollments if e.status == EnrollmentStatus.ACTIVE
        ]

    def __str__(self) -> str:
        return self.name


class Enrollment(Base):
    __tablename__ = "enrollment"
    __table_args__ = (UniqueConstraint("student_id", "group_id", name="uq_enrollment"),)

    id: Mapped[int] = mapped_column("enrollment_id", Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("student.student_id"))
    group_id: Mapped[int] = mapped_column(ForeignKey("study_group.group_id"))
    enroll_date: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[EnrollmentStatus] = mapped_column(
        Enum(
            EnrollmentStatus,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=EnrollmentStatus.ACTIVE,
    )

    student: Mapped[Student] = relationship(back_populates="enrollments")
    group: Mapped[Group] = relationship(back_populates="enrollments")
    # Композиция Enrollment — Payment: оплаты удаляются вместе с зачислением.
    payments: Mapped[list[Payment]] = relationship(
        back_populates="enrollment", cascade="all, delete-orphan"
    )

    def add_payment(self, amount: Decimal, date: dt.date | None = None) -> Payment:
        payment = Payment(amount=amount, pay_date=date or dt.date.today())
        self.payments.append(payment)
        return payment

    def get_paid(self) -> Decimal:
        return sum((p.amount for p in self.payments), Decimal(0))

    def get_debt(self) -> Decimal:
        return max(self.group.course.price - self.get_paid(), Decimal(0))

    def is_paid(self) -> bool:
        return self.get_debt() == 0

    def __str__(self) -> str:
        return f"{self.student} — {self.group}"


class Payment(Base):
    __tablename__ = "payment"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_payment_amount"),)

    id: Mapped[int] = mapped_column("payment_id", Integer, primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("enrollment.enrollment_id"))
    pay_date: Mapped[dt.date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    enrollment: Mapped[Enrollment] = relationship(back_populates="payments")


class Lesson(Base):
    __tablename__ = "lesson"
    __table_args__ = (
        UniqueConstraint(
            "room_id", "lesson_date", "start_time", name="uq_lesson_room_time"
        ),
    )

    id: Mapped[int] = mapped_column("lesson_id", Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("study_group.group_id"))
    room_id: Mapped[int] = mapped_column(ForeignKey("classroom.room_id"))
    lesson_date: Mapped[dt.date] = mapped_column(Date)
    start_time: Mapped[dt.time] = mapped_column(Time)
    topic: Mapped[str | None] = mapped_column(String(200))

    group: Mapped[Group] = relationship(back_populates="lessons")
    classroom: Mapped[Classroom] = relationship(back_populates="lessons")

    def reschedule(self, date: dt.date) -> None:
        self.lesson_date = date
