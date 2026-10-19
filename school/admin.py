"""Стандартная административная панель Django (/admin/)."""

from django.contrib import admin

from school.models import (
    Classroom,
    Course,
    Enrollment,
    Group,
    Lesson,
    Payment,
    Student,
    Teacher,
)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ["last_name", "first_name", "phone", "email", "birth_date", "user"]
    search_fields = ["last_name", "first_name", "email"]


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ["last_name", "first_name", "phone", "is_native", "user"]
    search_fields = ["last_name", "first_name"]


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ["title", "level", "hours", "price"]
    list_filter = ["level"]


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ["number", "capacity"]


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ["name", "course", "teacher", "start_date"]
    list_filter = ["course__level", "teacher"]
    inlines = [LessonInline]


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ["student", "group", "enroll_date", "status"]
    list_filter = ["status", "group"]
    inlines = [PaymentInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["pay_date", "enrollment", "amount"]
    date_hierarchy = "pay_date"


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ["lesson_date", "start_time", "group", "room", "topic"]
    list_filter = ["group", "room"]
    date_hierarchy = "lesson_date"
