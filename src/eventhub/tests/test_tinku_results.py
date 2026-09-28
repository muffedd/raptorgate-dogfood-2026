from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Judge, Project, Score, Team, Track
from eventhub.ranking import weighted_score, standings

FULL={'functionality':5,'quality':5,'innovation':5}
LOW={'functionality':1,'quality':1,'innovation':1}

class ResultNormalizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='rn',title='RN',submissions_close=timezone.now()-timedelta(days=1))
        cls.track=Track.objects.create(event=cls.event,slug='t',name='T')
        cls.team=Team.objects.create(event=cls.event,slug='tm',name='TM')
        User=get_user_model()
        cls.u1=User.objects.create_user(username='rn-u1')
        cls.u2=User.objects.create_user(username='rn-u2')
        cls.j1=Judge.objects.create(event=cls.event,slug='j1',user=cls.u1)
        cls.j2=Judge.objects.create(event=cls.event,slug='j2',user=cls.u2)
    def proj(self,slug,**kwargs):
        return Project.objects.create(event=self.event,team=self.team,track=self.track,slug=slug,title=slug,**kwargs)
    def rows_by_slug(self):
        return {r['project']:r for r in standings(self.event)}

    def test_harsh_and_lenient_judges_normalize_to_same_relative_rank(self):
        # Harsh judge rates x=1,y=2; lenient judge rates x=4,y=5. After
        # per-judge centering both must contribute identical z-scores, so the
        # normalized gap reflects only within-judge relative merit.
        x=self.proj('x'); y=self.proj('y')
        Score.objects.create(judge=self.j1,project=x,criteria=LOW)
        Score.objects.create(judge=self.j1,project=y,criteria={'functionality':2,'quality':2,'innovation':2})
        Score.objects.create(judge=self.j2,project=x,criteria={'functionality':4,'quality':4,'innovation':4})
        Score.objects.create(judge=self.j2,project=y,criteria=FULL)
        rows=standings(self.event)
        self.assertEqual([r['project'] for r in rows],['y','x'])
        by=self.rows_by_slug()
        self.assertEqual(by['x']['raw'],2.5)
        self.assertEqual(by['y']['raw'],3.5)
        self.assertEqual(by['x']['normalized'],2.0)
        self.assertEqual(by['y']['normalized'],4.0)
        self.assertEqual(by['x']['reviews'],2)

    def test_single_score_judge_contributes_neutral(self):
        # A judge with one scored project has zero spread: normalized must be
        # the neutral 3.0 while raw still reports the actual 5.0.
        x=self.proj('x')
        Score.objects.create(judge=self.j1,project=x,criteria=FULL)
        row=self.rows_by_slug()['x']
        self.assertEqual(row['raw'],5.0)
        self.assertEqual(row['normalized'],3.0)
        self.assertEqual(row['reviews'],1)

    def test_normalized_clamped_to_one_five_scale(self):
        # Six flat-low projects give the judge a tiny spread, pushing the lone
        # top project's z-score past the scale end; it must clamp to 5.0, and
        # the mirrored case must clamp to 1.0.
        for i in range(6):
            Score.objects.create(judge=self.j1,project=self.proj('lo%d'%i),criteria=LOW)
        Score.objects.create(judge=self.j1,project=self.proj('top'),criteria=FULL)
        by=self.rows_by_slug()
        self.assertEqual(by['top']['normalized'],5.0)
        self.assertEqual(by['lo0']['normalized'],2.592)
        self.assertTrue(all(1.0<=r['normalized']<=5.0 for r in by.values()))
        for s in Score.objects.all(): s.delete()
        for i in range(6):
            Score.objects.create(judge=self.j1,project=Project.objects.get(slug='lo%d'%i),criteria=FULL)
        Score.objects.create(judge=self.j1,project=Project.objects.get(slug='top'),criteria=LOW)
        by=self.rows_by_slug()
        self.assertEqual(by['top']['normalized'],1.0)
        self.assertEqual(by['lo0']['normalized'],3.408)

    def test_unscored_projects_rank_last_and_ties_break_by_slug(self):
        # Two projects scored by flat judges tie at neutral 3.0 and must order
        # by slug; an unscored project carries null raw/normalized and sorts last.
        a=self.proj('alpha'); b=self.proj('beta'); self.proj('zz-unscored')
        Score.objects.create(judge=self.j1,project=b,criteria=FULL)
        Score.objects.create(judge=self.j2,project=a,criteria=LOW)
        rows=standings(self.event)
        self.assertEqual([r['project'] for r in rows],['alpha','beta','zz-unscored'])
        self.assertEqual(rows[0]['normalized'],3.0)
        self.assertEqual(rows[1]['normalized'],3.0)
        self.assertIsNone(rows[2]['raw'])
        self.assertIsNone(rows[2]['normalized'])
        self.assertEqual(rows[2]['reviews'],0)

    def test_event_rubric_reweights_raw_and_ranking(self):
        # Under default weights functionality-heavy A outranks innovation-heavy
        # B; an innovation-heavy saved rubric must flip the order.
        a=self.proj('a'); b=self.proj('b')
        af={'functionality':5,'quality':1,'innovation':1}
        bf={'functionality':1,'quality':1,'innovation':5}
        Score.objects.create(judge=self.j1,project=a,criteria=af)
        Score.objects.create(judge=self.j1,project=b,criteria=bf)
        rows=standings(self.event)
        self.assertEqual([r['project'] for r in rows],['a','b'])
        self.assertEqual(self.rows_by_slug()['a']['raw'],2.6)
        self.event.rubric={'functionality':0.2,'quality':0.3,'innovation':0.5}
        self.event.save(update_fields=['rubric'])
        rows=standings(self.event)
        self.assertEqual([r['project'] for r in rows],['b','a'])
        by=self.rows_by_slug()
        self.assertEqual(by['a']['raw'],1.8)
        self.assertEqual(by['b']['raw'],3.0)
        self.assertEqual(by['a']['normalized'],2.0)
        self.assertEqual(by['b']['normalized'],4.0)

    def test_out_of_range_score_row_excluded_from_normalization(self):
        # A direct-ORM row with a criterion of 6 cannot be weighted. It must be
        # excluded from its project's aggregates AND from the judge's centering
        # stats, leaving the judge's valid score to normalize as flat-neutral.
        x=self.proj('x'); y=self.proj('y')
        Score.objects.create(judge=self.j1,project=x,criteria=LOW)
        Score.objects.create(judge=self.j1,project=y,criteria={'functionality':6,'quality':1,'innovation':1})
        by=self.rows_by_slug()
        self.assertEqual(by['x']['normalized'],3.0)
        self.assertEqual(by['x']['raw'],1.0)
        self.assertEqual(by['y']['reviews'],0)
        self.assertIsNone(by['y']['normalized'])

    def test_scores_on_duplicate_projects_do_not_pollute_standings(self):
        # The duplicate gets no row, and its score must not enter the judge's
        # centering stats: with it the judge would look non-flat and x would
        # normalize below 3.0 instead of neutral.
        x=self.proj('x')
        dup=self.proj('x-dup',duplicate_of=x)
        Score.objects.create(judge=self.j1,project=x,criteria=LOW)
        Score.objects.create(judge=self.j1,project=dup,criteria=FULL)
        rows=standings(self.event)
        self.assertEqual([r['project'] for r in rows],['x'])
        self.assertEqual(rows[0]['normalized'],3.0)
        self.assertEqual(rows[0]['reviews'],1)

    def test_weighted_score_rejects_boolean_criteria(self):
        # A JSON boolean is not an integer score from 1 to 5. True slips past
        # isinstance(v,int) because bool subclasses int, and True==1 satisfies
        # the range check, so it is wrongly weighted as a score of 1.
        self.assertIsNone(weighted_score({'functionality':True,'quality':4,'innovation':4}))
        self.assertIsNone(weighted_score({'functionality':False,'quality':4,'innovation':4}))
