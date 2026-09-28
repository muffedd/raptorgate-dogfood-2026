from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import (
    CommonPasswordValidator, MinimumLengthValidator, NumericPasswordValidator,
    UserAttributeSimilarityValidator,
)
from django.core.exceptions import ValidationError
from .models import Project

class ProjectForm(forms.ModelForm):
    class Meta:
        model=Project
        fields=['title','summary','repo_url','track']
    def __init__(self,*args,event=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['track'].queryset=event.tracks.all() if event else self.fields['track'].queryset.none()
    def clean_title(self):
        value=self.cleaned_data['title'].strip()
        if not value: raise ValidationError('A title is required')
        return value


class ParticipantSignupForm(UserCreationForm):
    """Only a normal user account; event roles are granted separately."""
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ('username',)

    def clean_password2(self):
        password = self.cleaned_data['password2']
        user = self.instance
        user.username = self.cleaned_data.get('username', '')
        for validator in (MinimumLengthValidator(8), CommonPasswordValidator(),
                          NumericPasswordValidator(), UserAttributeSimilarityValidator()):
            validator.validate(password, user)
        return password
