"""Модели ИС «Школа изучения итальянского языка».

Таблицы и столбцы повторяют физическую модель из ЛР 4 (study_group,
enrollment, student_id, ...), классы и методы — диаграмму классов из ЛР 9.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q, Sum

from school.formatting import fmt

phone_validator = RegexValidator(
    r"^\+?\d[\d\- ()]{5,18}\d$",
    "Телефон может содержать только цифры, пробелы, «+», «-» и скобки.",
)


class Level(models.TextChoices):
    """Уровни владения языком (перечисление Level из ЛР 9)."""

    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class EnrollmentStatus(models.TextChoices):
    ACTIVE = "обучается"
    FINISHED = "завершил"
    EXPELLED = "отчислен"


class Person(models.Model):
    """Абстрактный класс Person: общие атрибуты ученика и преподавателя.

    Своей таблицы не имеет — поля попадают в таблицы student и teacher.
    """

    last_name = models.CharField("фамилия", max_length=50)
    first_name = models.CharField("имя", max_length=50)
    phone = models.CharField(
        "телефон", max_length=20, blank=True, validators=[phone_validator]
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="учётная запись",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s",
    )

    class Meta:
        abstract = True
        ordering = ["last_name", "first_name"]

    def get_full_name(self) -> str:
        return f"{self.last_name} {self.first_name}"

    def __str__(self) -> str:
        return self.get_full_name()


class Student(Person):
    id = models.AutoField(primary_key=True, db_column="student_id")
    email = models.EmailField("e-mail", max_length=100, blank=True)
    birth_date = models.DateField("дата рождения", null=True, blank=True)

    class Meta(Person.Meta):
        db_table = "student"
        verbose_name = "ученик"
        verbose_name_plural = "ученики"

    def enroll(self, group: Group) -> Enrollment:
        return group.add_student(self)

    def get_debt(self) -> Decimal:
        active = self.enrollments.filter(status=EnrollmentStatus.ACTIVE)
        return sum((e.get_debt() for e in active), Decimal(0))


class Teacher(Person):
    id = models.AutoField(primary_key=True, db_column="teacher_id")
    is_native = models.BooleanField("носитель языка", default=False, db_column="native")

    class Meta(Person.Meta):
        db_table = "teacher"
        verbose_name = "преподаватель"
        verbose_name_plural = "преподаватели"

    def get_schedule(self) -> models.QuerySet[Lesson]:
        return Lesson.objects.filter(group__teacher=self)


class Course(models.Model):
    id = models.AutoField(primary_key=True, db_column="course_id")
    title = models.CharField("название", max_length=100)
    level = models.CharField("уровень", max_length=2, choices=Level.choices)
    hours = models.PositiveIntegerField("часов", validators=[MinValueValidator(1)])
    price = models.DecimalField(
        "стоимость, ₽",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        db_table = "course"
        ordering = ["level", "title"]
        verbose_name = "курс"
        verbose_name_plural = "курсы"
        constraints = [
            models.CheckConstraint(condition=Q(hours__gt=0), name="ck_course_hours"),
            models.CheckConstraint(condition=Q(price__gte=0), name="ck_course_price"),
        ]

    def get_groups(self) -> models.QuerySet[Group]:
        return self.groups.all()

    def __str__(self) -> str:
        return f"{self.title} ({self.level})"


class Classroom(models.Model):
    id = models.AutoField(primary_key=True, db_column="room_id")
    number = models.CharField("номер", max_length=10, unique=True)
    capacity = models.PositiveIntegerField(
        "вместимость", validators=[MinValueValidator(1)]
    )

    class Meta:
        db_table = "classroom"
        ordering = ["number"]
        verbose_name = "аудитория"
        verbose_name_plural = "аудитории"
        constraints = [
            models.CheckConstraint(
                condition=Q(capacity__gt=0), name="ck_classroom_capacity"
            ),
        ]

    def is_free(
        self, date: dt.date, time: dt.time, exclude_id: int | None = None
    ) -> bool:
        busy = self.lessons.filter(lesson_date=date, start_time=time)
        if exclude_id is not None:
            busy = busy.exclude(pk=exclude_id)
        return not busy.exists()

    def __str__(self) -> str:
        return f"ауд. {self.number}"


class Group(models.Model):
    id = models.AutoField(primary_key=True, db_column="group_id")
    name = models.CharField("название", max_length=30, unique=True)
    course = models.ForeignKey(
        Course, verbose_name="курс", on_delete=models.PROTECT, related_name="groups"
    )
    teacher = models.ForeignKey(
        Teacher,
        verbose_name="преподаватель",
        on_delete=models.PROTECT,
        related_name="groups",
    )
    start_date = models.DateField("дата старта")

    class Meta:
        db_table = "study_group"
        ordering = ["name"]
        verbose_name = "группа"
        verbose_name_plural = "группы"

    def add_student(self, student: Student) -> Enrollment:
        return Enrollment(student=student, group=self, enroll_date=dt.date.today())

    def get_students(self) -> models.QuerySet[Student]:
        return Student.objects.filter(
            enrollments__group=self, enrollments__status=EnrollmentStatus.ACTIVE
        )

    def __str__(self) -> str:
        return self.name


class Enrollment(models.Model):
    """Зачисление: разрешает связь «многие ко многим» ученик — группа."""

    id = models.AutoField(primary_key=True, db_column="enrollment_id")
    student = models.ForeignKey(
        Student,
        verbose_name="ученик",
        on_delete=models.PROTECT,
        related_name="enrollments",
    )
    group = models.ForeignKey(
        Group,
        verbose_name="группа",
        on_delete=models.PROTECT,
        related_name="enrollments",
    )
    enroll_date = models.DateField("дата зачисления", default=dt.date.today)
    status = models.CharField(
        "статус",
        max_length=20,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.ACTIVE,
    )

    class Meta:
        db_table = "enrollment"
        ordering = ["-enroll_date"]
        verbose_name = "зачисление"
        verbose_name_plural = "зачисления"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "group"],
                name="uq_enrollment",
                violation_error_message="Этот ученик уже зачислен в выбранную группу.",
            ),
        ]

    def add_payment(self, amount: Decimal, date: dt.date | None = None) -> Payment:
        return Payment.objects.create(
            enrollment=self, amount=amount, pay_date=date or dt.date.today()
        )

    def get_paid(self) -> Decimal:
        return self.payments.aggregate(total=Sum("amount"))["total"] or Decimal(0)

    def get_debt(self) -> Decimal:
        return max(self.group.course.price - self.get_paid(), Decimal(0))

    def is_paid(self) -> bool:
        return self.get_debt() == 0

    def __str__(self) -> str:
        return f"{self.student} — {self.group}"


class Payment(models.Model):
    id = models.AutoField(primary_key=True, db_column="payment_id")
    # Композиция Enrollment — Payment: оплаты удаляются вместе с зачислением.
    enrollment = models.ForeignKey(
        Enrollment,
        verbose_name="зачисление",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    pay_date = models.DateField("дата оплаты", default=dt.date.today)
    amount = models.DecimalField("сумма, ₽", max_digits=10, decimal_places=2)

    class Meta:
        db_table = "payment"
        ordering = ["-pay_date", "-id"]
        verbose_name = "оплата"
        verbose_name_plural = "оплаты"
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="ck_payment_amount"),
        ]

    def confirm(self) -> None:
        self.full_clean()
        self.save()

    def clean(self) -> None:
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Сумма должна быть больше нуля."})
        if not self.enrollment_id or self.amount is None:
            return
        enrollment = self.enrollment
        debt = enrollment.get_debt()
        if self.pk:
            old = Payment.objects.get(pk=self.pk)
            if old.enrollment_id == enrollment.id:
                debt += old.amount
        if self.amount > debt:
            raise ValidationError(
                {
                    "amount": f"Сумма превышает остаток к оплате по зачислению «{enrollment}»: {fmt(debt)} ₽."
                }
            )
        if self.pay_date and self.pay_date < enrollment.enroll_date:
            raise ValidationError(
                {"pay_date": "Дата оплаты не может быть раньше даты зачисления."}
            )

    def __str__(self) -> str:
        return f"{self.pay_date:%d.%m.%Y} — {self.amount} ₽ ({self.enrollment})"


class Lesson(models.Model):
    id = models.AutoField(primary_key=True, db_column="lesson_id")
    # Композиция Group — Lesson: занятия удаляются вместе с группой.
    group = models.ForeignKey(
        Group, verbose_name="группа", on_delete=models.CASCADE, related_name="lessons"
    )
    room = models.ForeignKey(
        Classroom,
        verbose_name="аудитория",
        on_delete=models.PROTECT,
        related_name="lessons",
    )
    lesson_date = models.DateField("дата")
    start_time = models.TimeField("время начала")
    topic = models.CharField("тема", max_length=200, blank=True)

    class Meta:
        db_table = "lesson"
        ordering = ["lesson_date", "start_time"]
        verbose_name = "занятие"
        verbose_name_plural = "занятия"
        constraints = [
            models.UniqueConstraint(
                fields=["room", "lesson_date", "start_time"],
                name="uq_lesson_room_time",
                violation_error_message="Аудитория в это время уже занята.",
            ),
        ]

    def reschedule(self, date: dt.date) -> None:
        self.lesson_date = date
        self.full_clean()
        self.save()

    def clean(self) -> None:
        if not (
            self.group_id and self.room_id and self.lesson_date and self.start_time
        ):
            return
        group, room = self.group, self.room
        if self.lesson_date < group.start_date:
            raise ValidationError(
                {
                    "lesson_date": f"Группа «{group}» начинает обучение {group.start_date:%d.%m.%Y}."
                }
            )
        if not room.is_free(self.lesson_date, self.start_time, self.pk):
            raise ValidationError(
                {"room": f"Аудитория {room.number} в это время уже занята."}
            )
        busy = (
            Lesson.objects.filter(
                group__teacher_id=group.teacher_id,
                lesson_date=self.lesson_date,
                start_time=self.start_time,
            )
            .exclude(pk=self.pk)
            .select_related("group")
            .first()
        )
        if busy is not None:
            raise ValidationError(
                f"Преподаватель {group.teacher} в это время ведёт занятие в группе «{busy.group}»."
            )
        students = group.get_students().count()
        if students > room.capacity:
            raise ValidationError(
                {
                    "room": f"В аудитории {room.number} {room.capacity} мест, а в группе {students} учеников."
                }
            )

    def __str__(self) -> str:
        return f"{self.lesson_date:%d.%m.%Y} {self.start_time:%H:%M} — {self.group}"
