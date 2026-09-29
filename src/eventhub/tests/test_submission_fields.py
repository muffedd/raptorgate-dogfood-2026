"""Gap 5: submission reference fields (thumbnail, gallery images, demo/live
URLs, tags) and organizer-defined custom questions on the submission flow."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from eventhub.models import Event, Project, Team, Track, clean_question_defs

QUESTIONS=[
    {"key":"stack","label":"Tech stack","required":True},
    {"key":"notes","label":"Anything judges should know?","required":False},
]

class SubmissionFieldTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='fields',title='Fields',active=True,
            submissions_close=timezone.now()+timedelta(hours=2),custom_questions=QUESTIONS)
        cls.track=Track.objects.create(event=cls.event,slug='dev',name='Dev')
        cls.team=Team.objects.create(event=cls.event,slug='crew',name='Crew')
        User=get_user_model()
        cls.member=User.objects.create_user(username='fielder')
        cls.team.members.add(cls.member)

    def payload(self,**overrides):
        data={'title':'Fielded','summary':'With extras','repo_url':'https://example.org/repo',
              'track':str(self.track.pk),
              'thumbnail_url':'https://example.org/thumb.png',
              'demo_video_url':'https://videos.example.org/demo',
              'live_url':'https://demo.example.org',
              'gallery_images_text':'https://example.org/a.png\nhttps://example.org/b.png',
              'tags_text':'ai, Web , ai',
              'cq_stack':'Django + Postgres','cq_notes':'  '}
        data.update(overrides)
        return data

    def test_reference_fields_persist(self):
        self.client.force_login(self.member)
        r=self.client.post('/projects/new',self.payload())
        self.assertEqual(r.status_code,201)
        p=Project.objects.get(event=self.event,team=self.team)
        self.assertEqual(p.thumbnail_url,'https://example.org/thumb.png')
        self.assertEqual(p.demo_video_url,'https://videos.example.org/demo')
        self.assertEqual(p.live_url,'https://demo.example.org')
        self.assertEqual(p.gallery_images,['https://example.org/a.png','https://example.org/b.png'])
        self.assertEqual(p.tags,['ai','Web'])
        self.assertEqual(p.custom_answers,{'stack':'Django + Postgres'})

    def test_edit_form_reloads_auxiliary_fields_and_keeps_them_on_resubmit(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post('/projects/new',self.payload()).status_code,201)
        page=self.client.get('/projects/new')
        self.assertContains(page,'https://example.org/a.png')
        self.assertContains(page,'https://example.org/b.png')
        self.assertContains(page,'ai, Web')
        self.assertContains(page,'Django + Postgres')
        # Browser posts the values now present in its rendered edit fields.
        form=page.context['form']
        data=self.payload(title='Edited title',
            gallery_images_text=form['gallery_images_text'].value(),
            tags_text=form['tags_text'].value(),
            cq_stack=form['cq_stack'].value())
        self.assertEqual(self.client.post('/projects/new',data).status_code,200)
        project=Project.objects.get(event=self.event,team=self.team)
        self.assertEqual(project.gallery_images,['https://example.org/a.png','https://example.org/b.png'])
        self.assertEqual(project.tags,['ai','Web'])
        self.assertEqual(project.custom_answers,{'stack':'Django + Postgres'})

    def test_track_option_uses_name(self):
        self.client.force_login(self.member)
        page=self.client.get('/projects/new')
        self.assertContains(page, '<option value="%s">Dev</option>'%self.track.pk, html=True)
        self.assertNotContains(page, 'Track object')

    def test_required_custom_question_enforced(self):
        self.client.force_login(self.member)
        data=self.payload(); del data['cq_stack']
        self.assertEqual(self.client.post('/projects/new',data).status_code,400)
        self.assertFalse(Project.objects.filter(event=self.event).exists())

    def test_optional_question_may_be_blank(self):
        self.client.force_login(self.member)
        data=self.payload(); del data['cq_notes']
        self.assertEqual(self.client.post('/projects/new',data).status_code,201)
        self.assertNotIn('notes',Project.objects.get(event=self.event).custom_answers)

    def test_unknown_question_keys_ignored(self):
        self.client.force_login(self.member)
        r=self.client.post('/projects/new',self.payload(cq_surprise='boo'))
        self.assertEqual(r.status_code,201)
        self.assertEqual(Project.objects.get(event=self.event).custom_answers,{'stack':'Django + Postgres'})

    def test_canonical_update_replaces_fields(self):
        self.client.force_login(self.member)
        self.client.post('/projects/new',self.payload())
        r=self.client.post('/projects/new',self.payload(title='Again',
            thumbnail_url='https://example.org/new.png',gallery_images_text='',
            tags_text='solo',cq_stack='Flask'))
        self.assertEqual(r.status_code,200)
        self.assertEqual(Project.objects.filter(event=self.event,team=self.team).count(),1)
        p=Project.objects.get(event=self.event,team=self.team)
        self.assertEqual(p.thumbnail_url,'https://example.org/new.png')
        self.assertEqual(p.gallery_images,[])
        self.assertEqual(p.tags,['solo'])
        self.assertEqual(p.custom_answers,{'stack':'Flask'})

    def test_all_reference_url_fields_reject_unsafe_schemes(self):
        self.client.force_login(self.member)
        for field in ('thumbnail_url','demo_video_url','live_url'):
            for value in ('javascript:alert(1)','ftp://example.org/file','data:text/html,x'):
                with self.subTest(field=field,value=value):
                    self.assertEqual(self.client.post('/projects/new',self.payload(**{field:value})).status_code,400)
        self.assertFalse(Project.objects.filter(event=self.event).exists())

    def test_gallery_per_image_length_and_tag_casefold_dedupe(self):
        self.client.force_login(self.member)
        long_image='https://example.org/'+('x'*181)
        self.assertEqual(self.client.post('/projects/new',self.payload(gallery_images_text=long_image)).status_code,400)
        result=self.client.post('/projects/new',self.payload(tags_text='AI, ai, Web, web'))
        self.assertEqual(result.status_code,201)
        self.assertEqual(Project.objects.get(event=self.event).tags,['AI','Web'])

    def test_non_http_reference_urls_rejected(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post('/projects/new',self.payload(thumbnail_url='ftp://example.org/t.png')).status_code,400)
        self.assertEqual(self.client.post('/projects/new',self.payload(live_url='javascript:alert(1)')).status_code,400)

    def test_gallery_image_validation(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post('/projects/new',self.payload(gallery_images_text='not-a-url')).status_code,400)
        self.assertEqual(self.client.post('/projects/new',self.payload(gallery_images_text='javascript:alert(1)')).status_code,400)
        too_many='\n'.join(f'https://example.org/{i}.png' for i in range(7))
        self.assertEqual(self.client.post('/projects/new',self.payload(gallery_images_text=too_many)).status_code,400)

    def test_tag_limits(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post('/projects/new',self.payload(tags_text=','.join(f't{i}' for i in range(9)))).status_code,400)
        self.assertEqual(self.client.post('/projects/new',self.payload(tags_text='x'*31)).status_code,400)

    def test_submit_page_lists_custom_questions(self):
        self.client.force_login(self.member)
        r=self.client.get('/projects/new')
        self.assertContains(r,'Tech stack')
        self.assertContains(r,'Anything judges should know?')

    def test_event_without_questions_still_submits(self):
        self.event.custom_questions=[];self.event.save()
        self.client.force_login(self.member)
        data=self.payload(); del data['cq_stack']; del data['cq_notes']
        self.assertEqual(self.client.post('/projects/new',data).status_code,201)

class ReferenceRenderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='render',title='Render',active=True,
            submissions_close=timezone.now()-timedelta(days=1),
            voting_opens=timezone.now()-timedelta(days=1),voting_closes=timezone.now()+timedelta(days=1),
            custom_questions=QUESTIONS)
        cls.track=Track.objects.create(event=cls.event,slug='dev',name='Dev')
        cls.team=Team.objects.create(event=cls.event,slug='crew',name='Crew')
        cls.project=Project.objects.create(event=cls.event,team=cls.team,track=cls.track,slug='shown',
            title='Shown',summary='S',thumbnail_url='https://example.org/t.png',
            demo_video_url='https://videos.example.org/d',live_url='https://live.example.org',
            gallery_images=['https://example.org/1.png','https://example.org/2.png'],
            tags=['ai','web'],
            custom_answers={'stack':'<script>alert(1)</script>','notes':'stale answer'})
        cls.plain=Project.objects.create(event=cls.event,team=Team.objects.create(event=cls.event,slug='other',name='Other'),
            track=cls.track,slug='plain',title='Plain')

    def test_detail_renders_reference_block(self):
        r=self.client.get('/projects/shown')
        self.assertContains(r,'https://example.org/t.png')
        self.assertContains(r,'https://example.org/1.png')
        self.assertContains(r,'https://example.org/2.png')
        self.assertContains(r,'https://videos.example.org/d')
        self.assertContains(r,'https://live.example.org')
        self.assertContains(r,'>ai</li>')
        self.assertContains(r,'Tech stack')
        self.assertContains(r,'&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(r,'<script>alert(1)</script>')

    def test_answers_to_removed_questions_not_rendered(self):
        self.event.custom_questions=[QUESTIONS[0]];self.event.save()
        r=self.client.get('/projects/shown')
        self.assertNotContains(r,'stale answer')

    def test_gallery_card_thumbnail_and_tags(self):
        r=self.client.get('/projects')
        self.assertContains(r,'https://example.org/t.png')
        self.assertContains(r,'card-tags')

    def test_missing_fields_render_clean(self):
        r=self.client.get('/projects/plain')
        self.assertEqual(r.status_code,200)
        self.assertNotContains(r,'rg-project-thumb')
        self.assertNotContains(r,'rg-project-gallery')
        self.assertNotContains(r,'rg-project-qa')

class EventQuestionDefinitionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User=get_user_model()
        cls.org=User.objects.create_superuser(username='q-org',email='q@example.org',password='x')

    def create(self,**overrides):
        self.client.force_login(self.org)
        data={'name':'Q Event','slug':'q-event','submissions_close':'2030-01-01T00:00:00+00:00'}
        data.update(overrides)
        return self.client.post('/events/new',data)

    def test_create_event_with_questions(self):
        r=self.create(custom_questions='[{"key":"stack","label":"Tech stack","required":true},{"key":"links","label":"Links","required":false}]')
        self.assertEqual(r.status_code,201)
        self.assertEqual(Event.objects.get(slug='q-event').custom_questions,
            [{'key':'stack','label':'Tech stack','required':True},{'key':'links','label':'Links','required':False}])

    def test_create_event_without_questions_defaults_empty(self):
        r=self.create(slug='q-plain')
        self.assertEqual(r.status_code,201)
        self.assertEqual(Event.objects.get(slug='q-plain').custom_questions,[])

    def test_event_create_rejects_non_boolean_required(self):
        result=self.create(slug='q-required',custom_questions='[{"key":"stack","label":"Stack","required":"yes"}]')
        self.assertEqual(result.status_code,400)
        self.assertFalse(Event.objects.filter(slug='q-required').exists())

    def test_malformed_questions_rejected(self):
        self.assertEqual(self.create(custom_questions='not json').status_code,400)
        self.assertEqual(self.create(slug='q-bad2',custom_questions='[{"key":"Bad Key","label":"x"}]').status_code,400)
        self.assertEqual(self.create(slug='q-bad3',custom_questions='[{"key":"a","label":""}]').status_code,400)
        self.assertEqual(self.create(slug='q-bad4',custom_questions='[{"key":"a","label":"x"},{"key":"a","label":"y"}]').status_code,400)
        too_many='['+','.join('{"key":"q%d","label":"L%d"}'%(i,i) for i in range(11))+']'
        self.assertEqual(self.create(slug='q-bad5',custom_questions=too_many).status_code,400)
        self.assertFalse(Event.objects.filter(slug__startswith='q-bad').exists())


class QuestionDefinitionBoundaryTests(TestCase):
    def test_normalizes_label_and_boolean_default(self):
        self.assertEqual(clean_question_defs([{'key':'stack','label':'  Tech stack  '}]),
                         [{'key':'stack','label':'Tech stack','required':False}])

    def test_rejects_malformed_shapes_types_and_lengths(self):
        invalid=[None,{},[None],[{'key':'Bad Key','label':'A'}],
                 [{'key':'stack','label':'   '}],
                 [{'key':'stack','label':'x'*161}],
                 [{'key':'stack','label':'A','required':'true'}],
                 [{'key':'stack','label':'A'},{'key':'stack','label':'B'}],
                 [{'key':'a','label':'A'}]*11]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                clean_question_defs(value)

    def test_accepts_ten_unique_definitions(self):
        definitions=[{'key':f'q{i}','label':f'Question {i}','required':i%2==0}
                     for i in range(10)]
        self.assertEqual(clean_question_defs(definitions),definitions)
