"""T3 adversarial lane: concurrent vote and comment writes on REAL PostgreSQL.

SQLite skips these: row-lock serialization is the mechanism under test and
SQLite does not provide it. Skips here are not evidence; run with DATABASE_URL
pointed at PostgreSQL.
"""
import threading
from django.db import connection, connections
from django.test import Client, TransactionTestCase
from eventhub.models import ProjectComment, PublicVote, PublicVoteAudit
from .t3_helpers import make_event, make_project, make_user


def _session_cookie(user):
    client = Client()
    client.force_login(user)
    return client.cookies["sessionid"].value


def _post_with_session(path, data, sessionid):
    client = Client()
    client.cookies.load({"sessionid": sessionid})
    try:
        return client.post(path, data).status_code
    finally:
        connections.close_all()


class ConcurrentVoteTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("race evidence requires PostgreSQL row locks")
        self.event = make_event("t3-race")
        self.alpha = make_project(self.event, "alpha")
        self.beta = make_project(self.event, "beta")

    def _blast(self, threads):
        barrier = threading.Barrier(len(threads))
        results = []

        def run(fn):
            barrier.wait()
            results.append(fn())

        workers = [threading.Thread(target=run, args=(fn,)) for fn in threads]
        for w in workers:
            w.start()
        for w in workers:
            w.join()
        return results

    def test_concurrent_first_votes_same_voter_leave_exactly_one(self):
        voter = make_user("racer")
        sessionid = _session_cookie(voter)
        statuses = self._blast([
            lambda: _post_with_session("/vote", {"event": "t3-race", "project": "alpha"}, sessionid),
            lambda: _post_with_session("/vote", {"event": "t3-race", "project": "beta"}, sessionid),
        ])
        self.assertEqual(sorted(statuses), [201, 409], statuses)
        self.assertEqual(PublicVote.objects.filter(event=self.event).count(), 1)
        self.assertEqual(PublicVoteAudit.objects.filter(event=self.event, action="cast").count(), 1)

    def test_concurrent_duplicate_vote_flood_leaves_exactly_one(self):
        voter = make_user("flooder")
        sessionid = _session_cookie(voter)
        statuses = self._blast([
            (lambda: _post_with_session("/vote", {"event": "t3-race", "project": "alpha"}, sessionid))
            for _ in range(8)
        ])
        self.assertEqual(statuses.count(201), 1, statuses)
        self.assertEqual(PublicVote.objects.filter(event=self.event).count(), 1)
        self.assertEqual(PublicVoteAudit.objects.filter(event=self.event, action="cast").count(), 1)

    def test_concurrent_votes_by_distinct_voters_on_one_project_all_count(self):
        voters = [make_user(f"v{i}") for i in range(4)]
        sessions = [_session_cookie(v) for v in voters]
        statuses = self._blast([
            (lambda s=s: _post_with_session("/vote", {"event": "t3-race", "project": "alpha"}, s))
            for s in sessions
        ])
        self.assertEqual(statuses, [201] * 4, statuses)
        self.assertEqual(PublicVote.objects.filter(event=self.event, project=self.alpha).count(), 4)


class ConcurrentCommentTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("race evidence requires PostgreSQL row locks")
        self.event = make_event("t3-race-cmt")
        make_project(self.event)

    def test_concurrent_comment_burst_respects_rate_limit(self):
        author = make_user("burst")
        sessionid = _session_cookie(author)
        barrier = threading.Barrier(10)
        results = []

        def fire(i):
            barrier.wait()
            results.append(_post_with_session("/projects/proj",
                                              {"event": "t3-race-cmt", "body": f"c{i}"},
                                              sessionid))

        threads = [threading.Thread(target=fire, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count(201), 5, results)
        self.assertEqual(results.count(429), 5, results)
        self.assertEqual(ProjectComment.objects.filter(event=self.event).count(), 5)
