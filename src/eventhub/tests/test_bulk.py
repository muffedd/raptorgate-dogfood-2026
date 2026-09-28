"""Transactional, scoped project migration with strict CSV validation."""
import csv
from datetime import timedelta
from io import StringIO
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Project, Team, Track

HEADER='project_slug,title,summary,repo_url,team_slug,track_slug\n'

class BulkProjectTests(TestCase):
    def setUp(self):
        self.event=Event.objects.create(slug='bulk',title='Bulk',active=True,
                          submissions_close=timezone.now()+timedelta(days=1))
        self.team=Team.objects.create(event=self.event,slug='red',name='Red')
        self.track=Track.objects.create(event=self.event,slug='tools',name='Tools')
        other=Event.objects.create(slug='other',title='Other',submissions_close=timezone.now()+timedelta(days=1))
        Team.objects.create(event=other,slug='foreign',name='Foreign')
        Track.objects.create(event=other,slug='foreign',name='Foreign')
        user=get_user_model()
        self.org=user.objects.create_superuser('bulk-org','bulk@example.org','secret')
        self.participant=user.objects.create_user('bulk-person')

    def upload(self, body):
        return self.client.post('/organizer/projects/import', data=body, content_type='text/csv')

    def test_organizer_import_and_export_roundtrip(self):
        self.client.force_login(self.org)
        body=HEADER+'p-1,Project One,Summary,https://example.org/red,red,tools\n'
        self.assertEqual(self.upload(body).status_code,201)
        self.assertEqual(Project.objects.get(slug='p-1').event,self.event)
        response=self.client.get('/organizer/projects.csv')
        self.assertEqual(response.status_code,200)
        rows=list(csv.DictReader(StringIO(response.content.decode())))
        self.assertEqual(rows[0]['title'],'Project One')
        self.assertEqual(self.upload(body).status_code,409)
        self.assertEqual(Project.objects.count(),1)

    def test_unauthorized_roles_cannot_import_or_export(self):
        for user in (None,self.participant):
            if user:self.client.force_login(user)
            for url in ('/organizer/projects/import','/organizer/projects.csv'):
                response=self.upload(HEADER+'p,Name,,,red,tools\n') if url.endswith('import') else self.client.get(url)
                self.assertEqual(response.status_code,403)
        self.assertFalse(Project.objects.exists())

    def test_all_or_nothing_and_cross_event_scope(self):
        self.client.force_login(self.org)
        for bad in ('foreign,tools','red,foreign'):
            body=HEADER+'good,Good,,,red,tools\n'+'bad,Bad,,,'+bad+'\n'
            self.assertEqual(self.upload(body).status_code,400)
            self.assertFalse(Project.objects.exists())
        duplicate=HEADER+'good,Good,,,red,tools\ngood,Again,,,red,tools\n'
        self.assertEqual(self.upload(duplicate).status_code,400)
        self.assertFalse(Project.objects.exists())

    def test_closed_and_published_event_blocked(self):
        self.client.force_login(self.org)
        body=HEADER+'p,Name,,,red,tools\n'
        self.event.submissions_close=timezone.now()-timedelta(seconds=1)
        self.event.save()
        self.assertEqual(self.upload(body).status_code,409)
        self.event.submissions_close=timezone.now()+timedelta(days=1)
        self.event.published=True
        self.event.save()
        self.assertEqual(self.upload(body).status_code,409)
        self.assertFalse(Project.objects.exists())

    def test_malformed_csv_and_formula_export(self):
        self.client.force_login(self.org)
        for body in ('not,a,valid,header\np,Name,,,red,tools\n',
                     HEADER+'p,Name,,,red,tools,extra\n',
                     HEADER+'p,Name,,,red\n',
                     HEADER+'p,Name,,,red,tools\np,Again,,,red,tools\n'):
            self.assertEqual(self.upload(body).status_code,400)
        self.assertFalse(Project.objects.exists())
        Project.objects.create(event=self.event,team=self.team,track=self.track,slug='p',title='=1+1')
        rows=list(csv.DictReader(StringIO(self.client.get('/organizer/projects.csv').content.decode())))
        self.assertEqual(rows[0]['title'],"'=1+1")

    def test_caps_and_method_gates(self):
        self.client.force_login(self.org)
        self.assertEqual(self.client.get('/organizer/projects/import').status_code,405)
        self.assertEqual(self.client.post('/organizer/projects.csv').status_code,405)
        huge=HEADER+'p,Name,'+('x'*(1024*1024))+',,red,tools\n'
        self.assertEqual(self.upload(huge).status_code,413)
        many=HEADER+''.join(f'p-{i},Name,,,red,tools\n' for i in range(501))
        self.assertEqual(self.upload(many).status_code,400)
        self.assertFalse(Project.objects.exists())

    def test_no_active_event_does_not_fall_back(self):
        Event.objects.filter(pk=self.event.pk).update(active=False)
        self.client.force_login(self.org)
        self.assertEqual(self.client.get('/organizer/projects.csv').status_code,404)
        self.assertEqual(self.upload(HEADER+'p,Name,,,red,tools\n').status_code,404)
        self.assertFalse(Project.objects.exists())

    def test_two_valid_rows_with_one_existing_slug_do_not_partially_import(self):
        Project.objects.create(event=self.event,team=self.team,track=self.track,slug='taken',title='Before')
        self.client.force_login(self.org)
        self.assertEqual(self.upload(HEADER+'fresh,Fresh,,,red,tools\ntaken,Collision,,,red,tools\n').status_code,409)
        self.assertEqual(list(Project.objects.values_list('slug',flat=True)),['taken'])
