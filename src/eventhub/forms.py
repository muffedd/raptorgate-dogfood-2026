from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import (
    CommonPasswordValidator, MinimumLengthValidator, NumericPasswordValidator,
    UserAttributeSimilarityValidator,
)
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from .models import GALLERY_IMAGE_LIMIT, TAG_LIMIT, TAG_MAX_LEN, Project

_http_url=URLValidator(schemes=['http','https'])

class ProjectForm(forms.ModelForm):
    gallery_images_text=forms.CharField(required=False,label='Gallery image URLs',
        widget=forms.Textarea(attrs={'rows':3}),
        help_text='One http/https image URL per line, up to %d.'%GALLERY_IMAGE_LIMIT)
    tags_text=forms.CharField(required=False,label='Tags',
        help_text='Comma-separated, up to %d tags of %d characters or fewer.'%(TAG_LIMIT,TAG_MAX_LEN))
    class Meta:
        model=Project
        fields=['title','summary','repo_url','track','thumbnail_url','demo_video_url','live_url']
    def __init__(self,*args,event=None,**kwargs):
        super().__init__(*args,**kwargs)
        raw=getattr(event,'custom_questions',None) or []
        self.question_defs=[q for q in raw
            if isinstance(q,dict) and isinstance(q.get('key'),str) and isinstance(q.get('label'),str)]
        self.fields['track'].queryset=event.tracks.all() if event else self.fields['track'].queryset.none()
        for q in self.question_defs:
            self.fields['cq_'+q['key']]=forms.CharField(label=q['label'],
                required=bool(q.get('required')),max_length=500,
                widget=forms.Textarea(attrs={'rows':2}))
        self.order_fields(list(self.Meta.fields)+['gallery_images_text','tags_text']
            +['cq_'+q['key'] for q in self.question_defs])
    def clean_title(self):
        value=self.cleaned_data['title'].strip()
        if not value: raise ValidationError('A title is required')
        return value
    def _http_only(self,name,label):
        value=self.cleaned_data.get(name,'')
        if value:
            try:_http_url(value)
            except ValidationError: raise ValidationError('%s must be an http or https URL'%label)
        return value
    def clean_thumbnail_url(self): return self._http_only('thumbnail_url','Thumbnail URL')
    def clean_demo_video_url(self): return self._http_only('demo_video_url','Demo video URL')
    def clean_live_url(self): return self._http_only('live_url','Live URL')
    def clean_gallery_images_text(self):
        urls=[line.strip() for line in (self.cleaned_data.get('gallery_images_text') or '').splitlines() if line.strip()]
        if len(urls)>GALLERY_IMAGE_LIMIT:
            raise ValidationError('At most %d gallery images'%GALLERY_IMAGE_LIMIT)
        for url in urls:
            if len(url)>200: raise ValidationError('Gallery image URLs must be 200 characters or fewer')
            try:_http_url(url)
            except ValidationError: raise ValidationError('Every gallery image must be a valid http or https URL: %s'%url)
        return urls
    def clean_tags_text(self):
        tags=[]; seen=set()
        for piece in (self.cleaned_data.get('tags_text') or '').split(','):
            tag=' '.join(piece.split())
            if not tag: continue
            if len(tag)>TAG_MAX_LEN: raise ValidationError('Tags must be %d characters or fewer'%TAG_MAX_LEN)
            folded=tag.casefold()
            if folded in seen: continue
            seen.add(folded); tags.append(tag)
        if len(tags)>TAG_LIMIT: raise ValidationError('At most %d tags'%TAG_LIMIT)
        return tags
    def clean(self):
        cleaned=super().clean()
        self.custom_answers={q['key']:cleaned.get('cq_'+q['key'])
            for q in self.question_defs if cleaned.get('cq_'+q['key'])}
        return cleaned
    def save(self,commit=True):
        instance=super().save(commit=False)
        instance.gallery_images=self.cleaned_data.get('gallery_images_text',[])
        instance.tags=self.cleaned_data.get('tags_text',[])
        instance.custom_answers=self.custom_answers
        if commit: instance.save()
        return instance


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
