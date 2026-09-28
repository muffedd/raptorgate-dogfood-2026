from django.conf import settings
from django.db import models

class Event(models.Model):
    slug=models.SlugField(unique=True)
    title=models.CharField(max_length=160)
    submissions_close=models.DateTimeField()
    results_publish_at=models.DateTimeField(null=True,blank=True)

class Track(models.Model):
    event=models.ForeignKey(Event,on_delete=models.CASCADE,related_name='tracks')
    slug=models.SlugField()
    name=models.CharField(max_length=100)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['event','slug'],name='unique_track_in_event')]

class Team(models.Model):
    event=models.ForeignKey(Event,on_delete=models.CASCADE,related_name='teams')
    slug=models.SlugField()
    name=models.CharField(max_length=160)
    members=models.ManyToManyField(settings.AUTH_USER_MODEL,related_name='teams')
    invite_token=models.CharField(max_length=64,blank=True,unique=True,null=True)
    invite_expires_at=models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['event','slug'],name='unique_team_in_event')]

class Project(models.Model):
    event=models.ForeignKey(Event,on_delete=models.CASCADE,related_name='projects')
    slug=models.SlugField()
    team=models.ForeignKey(Team,on_delete=models.PROTECT,related_name='projects')
    track=models.ForeignKey(Track,on_delete=models.PROTECT,related_name='projects')
    title=models.CharField(max_length=180)
    summary=models.TextField(blank=True)
    repo_url=models.URLField(blank=True)
    submitted_at=models.DateTimeField(null=True,blank=True)
    draft=models.BooleanField(default=False)
    duplicate_of=models.ForeignKey('self',null=True,blank=True,on_delete=models.SET_NULL)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['event','slug'],name='unique_project_in_event')]

class Judge(models.Model):
    event=models.ForeignKey(Event,on_delete=models.CASCADE,related_name='judges')
    slug=models.SlugField()
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='judge_roles')
    tracks=models.ManyToManyField(Track,related_name='judges')
    class Meta:
        constraints=[models.UniqueConstraint(fields=['event','slug'],name='unique_judge_in_event')]

class Score(models.Model):
    judge=models.ForeignKey(Judge,on_delete=models.CASCADE,related_name='scores')
    project=models.ForeignKey(Project,on_delete=models.CASCADE,related_name='scores')
    criteria=models.JSONField(default=dict)
    comment=models.TextField(blank=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['judge','project'],name='unique_judge_project')]
