from django import forms
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
