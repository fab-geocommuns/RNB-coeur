from django import forms
from django.contrib.auth.models import User


class RollbackForm(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.all().order_by("username"),
        required=True,
        label="Utilisateur",
    )
    start_time = forms.DateTimeField(
        required=False,
        label="Date de début",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local", "step": "1"}),
    )
    end_time = forms.DateTimeField(
        required=False,
        label="Date de fin",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local", "step": "1"}),
    )
