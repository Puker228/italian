from django.urls import path

from school import views

urlpatterns = [
    path("", views.home, name="home"),
    path("reports/", views.reports, name="reports"),
    path("backup/", views.backup, name="backup"),
    path("api/schedule/", views.api_schedule, name="api_schedule"),
    path("api/courses/", views.api_courses, name="api_courses"),
    path("<slug:slug>/", views.entity_list, name="entity_list"),
    path("<slug:slug>/add/", views.entity_create, name="entity_create"),
    path("<slug:slug>/<int:pk>/edit/", views.entity_update, name="entity_update"),
    path("<slug:slug>/<int:pk>/delete/", views.entity_delete, name="entity_delete"),
]
