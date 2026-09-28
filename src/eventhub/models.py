from django.conf import settings
from django.db import models

class Event(models.Model):
    slug=models.SlugField(unique=True)
    title=models.CharField(max_length=160)
    submissions_close=models.DateTimeField()
    results_publish_at=models.DateTimeField(null=True,blank=True)
    published=models.BooleanField(default=False)
    rubric=models.JSONField(default=dict)
    active=models.BooleanField(default=False)
    voting_opens=models.DateTimeField(null=True,blank=True)
    voting_closes=models.DateTimeField(null=True,blank=True)
    voting_access=models.CharField(max_length=20,default="authenticated",choices=[("authenticated","Authenticated"),("email","Email verified"),("open","Open link")])

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
    invited_at=models.DateTimeField(null=True,blank=True)
    invite_token=models.CharField(max_length=64,blank=True,null=True,unique=True)
    invite_expires_at=models.DateTimeField(blank=True,null=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['event','slug'],name='unique_judge_in_event'),
                     models.UniqueConstraint(fields=['event','user'],name='unique_judge_event_user')]

class Score(models.Model):
    judge=models.ForeignKey(Judge,on_delete=models.CASCADE,related_name='scores')
    project=models.ForeignKey(Project,on_delete=models.CASCADE,related_name='scores')
    criteria=models.JSONField(default=dict)
    comment=models.TextField(blank=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['judge','project'],name='unique_judge_project')]

class Assignment(models.Model):
    judge=models.ForeignKey(Judge,on_delete=models.CASCADE,related_name='assignments')
    project=models.ForeignKey(Project,on_delete=models.CASCADE,related_name='assignments')
    class Meta:
        constraints=[models.UniqueConstraint(fields=['judge','project'],name='unique_judge_assignment')]

class ScoreAudit(models.Model):
    score=models.ForeignKey(Score,on_delete=models.CASCADE,related_name='history')
    editor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    previous=models.JSONField(null=True,blank=True)
    current=models.JSONField()
    written_at=models.DateTimeField(auto_now_add=True)

class PublicVote(models.Model):
    event=models.ForeignKey(Event,on_delete=models.CASCADE,related_name='public_votes')
    project=models.ForeignKey(Project,on_delete=models.CASCADE,related_name='public_votes')
    voter_key=models.CharField(max_length=180)
    receipt=models.CharField(max_length=40,unique=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['event','voter_key'],name='unique_public_vote_per_voter_event')]

class PublicVoteAudit(models.Model):
    event=models.ForeignKey(Event,on_delete=models.CASCADE)
    voter_key=models.CharField(max_length=180)
    project=models.ForeignKey(Project,on_delete=models.CASCADE)
    action=models.CharField(max_length=32)
    observed_ip=models.GenericIPAddressField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)

class ProjectComment(models.Model):
    event=models.ForeignKey(Event,on_delete=models.CASCADE)
    project=models.ForeignKey(Project,on_delete=models.CASCADE)
    author=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    body=models.TextField()
    created_at=models.DateTimeField(auto_now_add=True)
    hidden=models.BooleanField(default=False)

class PublicActionAttempt(models.Model):
    event=models.ForeignKey(Event,on_delete=models.CASCADE)
    actor_key=models.CharField(max_length=180)
    action=models.CharField(max_length=20)
    observed_ip=models.GenericIPAddressField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes=[models.Index(fields=['event','actor_key','action','created_at'])]

class VoterAccess(models.Model):
    """One-use open invite or email challenge. Never persist plaintext secrets."""
    event=models.ForeignKey(Event,on_delete=models.CASCADE)
    kind=models.CharField(max_length=10,choices=[('open','Open link'),('email','Email')])
    identity=models.CharField(max_length=254,blank=True)
    secret_hash=models.CharField(max_length=64,unique=True)
    expires_at=models.DateTimeField()
    redeemed_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['event','kind','identity'],name='unique_voter_access_identity',condition=models.Q(kind='email'))]

class APIToken(models.Model):
    """Explicit user-issued bearer credential; only its digest is stored."""
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='api_tokens')
    name=models.CharField(max_length=80)
    token_hash=models.CharField(max_length=64,unique=True)
    created_at=models.DateTimeField(auto_now_add=True)
    expires_at=models.DateTimeField()
    revoked_at=models.DateTimeField(null=True,blank=True)
