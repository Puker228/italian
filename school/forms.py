"""Формы на основе моделей; проверки данных — в model.clean() и ограничениях БД."""

from __future__ import annotations

from typing import Any

from django import forms

from school.entities import Entity
from school.roles import Role


class StyledModelForm(forms.ModelForm):
    """ModelForm с классами Bootstrap и HTML5-полями даты и времени."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.DateInput):
                widget.input_type = "date"
                widget.format = "%Y-%m-%d"
            elif isinstance(widget, forms.TimeInput):
                widget.input_type = "time"
                widget.format = "%H:%M"
            if isinstance(widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(widget, forms.Select):
                css = "form-select"
            else:
                css = "form-control"
            widget.attrs["class"] = css


def form_class(entity: Entity, role: Role, user: Any) -> type[forms.ModelForm]:
    access = entity.access[role]

    class EntityForm(StyledModelForm):
        class Meta:
            model = entity.model
            fields = entity.fields

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            for name, scope in access.choices.items():
                field = self.fields[name]
                field.queryset = scope(field.queryset, user)

    return EntityForm


class ReportForm(forms.Form):
    kind = forms.ChoiceField(label="Отчёт")
    start = forms.DateField(label="с", widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(label="по", widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(
        self, *args: Any, choices: list[tuple[str, str]], **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.fields["kind"].choices = choices
        self.fields["kind"].widget.attrs["class"] = "form-select"
        for name in ("start", "end"):
            self.fields[name].widget.attrs["class"] = "form-control"
            self.fields[name].widget.format = "%Y-%m-%d"

    def clean(self) -> dict[str, Any]:
        data = super().clean()
        if data.get("start") and data.get("end") and data["start"] > data["end"]:
            raise forms.ValidationError("Дата начала периода позже даты окончания.")
        return data
