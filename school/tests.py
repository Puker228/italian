import datetime as dt
import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from school.models import (
    Classroom,
    Enrollment,
    Group,
    Lesson,
    Payment,
    Student,
    Teacher,
)

PASSWORD = "italia2026"


class SchoolTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", admin_password="admin", stdout=open("/dev/null", "w"))
        cls.today = timezone.localdate()
        cls.a1 = Group.objects.get(name="A1-01")
        cls.b1 = Group.objects.get(name="B1-01")
        cls.room101 = Classroom.objects.get(number="101")
        cls.room201 = Classroom.objects.get(number="201")

    def login(self, username, password=PASSWORD):
        self.assertTrue(self.client.login(username=username, password=password))


class ModelTests(SchoolTestCase):
    def test_debt(self):
        sokolova = Student.objects.get(last_name="Соколова")
        self.assertEqual(sokolova.get_debt(), Decimal(12000))
        self.assertTrue(Enrollment.objects.get(student__last_name="Петров").is_paid())

    def test_room_conflict(self):
        lesson = Lesson(
            group=self.b1,
            room=self.room101,
            lesson_date=self.today,
            start_time=dt.time(18, 0),
        )
        with self.assertRaisesMessage(
            ValidationError, "Аудитория 101 в это время уже занята"
        ):
            lesson.full_clean()

    def test_teacher_busy(self):
        lesson = Lesson(
            group=self.a1,
            room=self.room201,
            lesson_date=self.today,
            start_time=dt.time(18, 0),
        )
        with self.assertRaisesMessage(
            ValidationError, "Росси Марко в это время ведёт занятие"
        ):
            lesson.full_clean()

    def test_lesson_before_group_start(self):
        lesson = Lesson(
            group=self.b1,
            room=self.room201,
            lesson_date=self.b1.start_date - dt.timedelta(days=1),
            start_time=dt.time(9, 0),
        )
        with self.assertRaisesMessage(ValidationError, "начинает обучение"):
            lesson.full_clean()

    def test_overpayment(self):
        enrollment = Enrollment.objects.get(
            student__last_name="Соколова", group=self.a1
        )
        with self.assertRaisesMessage(ValidationError, "превышает остаток"):
            Payment(
                enrollment=enrollment, amount=Decimal(20000), pay_date=self.today
            ).full_clean()
        Payment(
            enrollment=enrollment, amount=Decimal(12000), pay_date=self.today
        ).full_clean()

    def test_duplicate_enrollment(self):
        petrov = Student.objects.get(last_name="Петров")
        with self.assertRaisesMessage(ValidationError, "уже зачислен"):
            Enrollment(
                student=petrov, group=self.a1, enroll_date=self.today
            ).full_clean()

    def test_composition_cascade(self):
        enrollment = Enrollment.objects.get(student__last_name="Петров")
        enrollment.delete()
        self.assertFalse(Payment.objects.filter(enrollment_id=enrollment.id).exists())


class AdminViewTests(SchoolTestCase):
    def setUp(self):
        self.login("admin", "admin")

    def test_admin_menu(self):
        response = self.client.get(reverse("home"))
        for item in ("Отчёты", "Резервная копия", "Панель администратора"):
            self.assertContains(response, item)

    def test_all_lists_open(self):
        for slug in [
            "students",
            "teachers",
            "courses",
            "classrooms",
            "groups",
            "enrollments",
            "payments",
            "lessons",
        ]:
            self.assertEqual(
                self.client.get(reverse("entity_list", args=[slug])).status_code,
                200,
                slug,
            )
        self.assertContains(
            self.client.get(reverse("entity_list", args=["students"]), {"q": "Сок"}),
            "Соколова",
        )

    def test_create_student_with_validation(self):
        url = reverse("entity_create", args=["students"])
        response = self.client.post(
            url, {"last_name": "Новиков", "first_name": "Павел", "email": "bad@"}
        )
        self.assertContains(response, "Введите правильный адрес электронной почты")
        response = self.client.post(
            url,
            {
                "last_name": "Новиков",
                "first_name": "Павел",
                "phone": "+7 (999) 123-45-67",
            },
        )
        self.assertRedirects(response, reverse("entity_list", args=["students"]))
        self.assertTrue(Student.objects.filter(last_name="Новиков").exists())

    def test_protected_delete(self):
        petrov = Student.objects.get(last_name="Петров")
        response = self.client.post(
            reverse("entity_delete", args=["students", petrov.pk]), follow=True
        )
        self.assertContains(response, "Нельзя удалить")
        self.assertTrue(Student.objects.filter(pk=petrov.pk).exists())

    def test_reports_and_csv(self):
        response = self.client.get(
            reverse("reports"),
            {"kind": "debtors", "start": "2026-01-01", "end": "2030-01-01"},
        )
        self.assertContains(response, "Должников: 3, общая задолженность: 60 000.00 ₽")
        csv = self.client.get(
            reverse("reports"),
            {
                "kind": "income",
                "start": "2000-01-01",
                "end": "2030-01-01",
                "format": "csv",
            },
        )
        self.assertEqual(csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Платежей: 5", csv.content.decode("utf-8-sig"))

    def test_backup(self):
        response = self.client.get(reverse("backup"))
        data = json.loads(response.content)
        self.assertTrue(any(item["model"] == "school.lesson" for item in data))


class RoleTests(SchoolTestCase):
    def test_teacher_sees_only_own_lessons(self):
        self.login("rossi")
        response = self.client.get(reverse("api_schedule"))
        groups = {item["group"] for item in response.json()["results"]}
        self.assertEqual(groups, {"A1-01"})
        self.assertEqual(
            self.client.get(reverse("entity_list", args=["students"])).status_code, 403
        )
        self.assertEqual(self.client.get(reverse("reports")).status_code, 403)
        self.assertNotContains(self.client.get(reverse("home")), "Резервная копия")

    def test_teacher_cannot_edit_foreign_lesson(self):
        self.login("rossi")
        foreign = Lesson.objects.filter(group=self.b1).first()
        self.assertEqual(
            self.client.get(
                reverse("entity_update", args=["lessons", foreign.pk])
            ).status_code,
            404,
        )
        form = self.client.get(reverse("entity_create", args=["lessons"])).context[
            "form"
        ]
        self.assertEqual(list(form.fields["group"].queryset), [self.a1])

    def test_student_read_only(self):
        self.login("sokolova")
        self.assertContains(self.client.get(reverse("home")), "12 000.00 ₽")
        self.assertEqual(
            self.client.get(reverse("entity_create", args=["courses"])).status_code, 403
        )
        payments = self.client.get(reverse("entity_list", args=["payments"]))
        self.assertEqual(payments.context["page"].paginator.count, 2)
        self.assertNotContains(payments, "Петров")

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, f"{reverse('login')}?next=/")

    def test_teacher_profile_link(self):
        self.assertEqual(Teacher.objects.get(user__username="rossi").last_name, "Росси")
