"""T3 adversarial lane: comment XSS, moderation controls, closed windows,
throttle scoping, and cross-event comment isolation."""
from datetime import timedelta
from django.test import Client, TestCase
from django.utils import timezone
from eventhub.models import Event, ProjectComment
from .t3_helpers import make_event, make_organizer, make_project, make_user


class CommentXSSTests(TestCase):
    def setUp(self):
        self.event = make_event("t3-xss")
        self.project = make_project(self.event)
        self.author = make_user("author")
        self.client.force_login(self.author)
        self.path = "/projects/proj"

    def test_script_and_handler_payloads_render_escaped(self):
        payloads = [
            "<script>alert(document.cookie)</script>",
            '<img src=x onerror="alert(1)">',
            '"><svg onload=alert(1)>',
            "<a href=\"javascript:alert(1)\">click</a>",
        ]
        for payload in payloads:
            resp = self.client.post(self.path, {"event": "t3-xss", "body": payload})
            self.assertEqual(resp.status_code, 201, payload)
        page = self.client.get(self.path, {"event": "t3-xss"}).content.decode()
        self.assertNotIn("<script>alert", page)
        self.assertNotIn("<img src=x", page)
        self.assertNotIn("<svg onload", page)
        self.assertNotIn('<a href="javascript:alert', page)
        self.assertIn("&lt;a href=&quot;javascript:alert(1)&quot;&gt;", page)
        self.assertIn("&lt;script&gt;", page)

    def test_comment_author_username_is_escaped(self):
        evil = make_user("evil<script>")
        self.client.force_login(evil)
        self.client.post(self.path, {"event": "t3-xss", "body": "hi"})
        page = self.client.get(self.path, {"event": "t3-xss"}).content.decode()
        self.assertNotIn("evil<script>", page)
        self.assertIn("evil&lt;script&gt;", page)


class CommentControlTests(TestCase):
    def setUp(self):
        self.event = make_event("t3-ctrl")
        self.project = make_project(self.event)
        self.other_event = make_event("t3-ctrl-foreign", active=False)
        self.other_project = make_project(self.other_event, "foreign")
        self.author = make_user("author")
        self.organizer = make_organizer()

    def _post(self, body="hello", event="t3-ctrl", path="/projects/proj"):
        return self.client.post(path, {"event": event, "body": body})

    def test_author_cannot_moderate_own_or_foreign_comments(self):
        self.client.force_login(self.author)
        self.assertEqual(self._post().status_code, 201)
        comment = ProjectComment.objects.get()
        resp = self.client.post(f"/organizer/comments/{comment.pk}/hide", {"event": "t3-ctrl"})
        self.assertEqual(resp.status_code, 403)
        comment.refresh_from_db()
        self.assertFalse(comment.hidden)

    def test_moderation_requires_post(self):
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.get("/organizer/comments/1/hide").status_code, 405)

    def test_moderator_cannot_hide_comment_from_another_event(self):
        self.client.force_login(self.author)
        self.assertEqual(self._post().status_code, 201)
        comment = ProjectComment.objects.get()
        self.client.force_login(self.organizer)
        # Guessing the pk but scoping to a different event must miss.
        resp = self.client.post(f"/organizer/comments/{comment.pk}/hide",
                                {"event": "t3-ctrl-foreign"})
        self.assertEqual(resp.status_code, 404)
        comment.refresh_from_db()
        self.assertFalse(comment.hidden)
        # And the legitimate hide works and removes it from the page.
        resp = self.client.post(f"/organizer/comments/{comment.pk}/hide", {"event": "t3-ctrl"})
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(self.client.get("/projects/proj", {"event": "t3-ctrl"}), "hello")

    def test_anonymous_comment_rejected(self):
        self.assertEqual(self._post().status_code, 401)
        self.assertEqual(ProjectComment.objects.count(), 0)

    def test_comment_window_boundaries(self):
        self.client.force_login(self.author)
        Event.objects.filter(pk=self.event.pk).update(
            voting_opens=timezone.now() + timedelta(hours=1))
        self.assertEqual(self._post().status_code, 403)  # not yet open
        Event.objects.filter(pk=self.event.pk).update(
            voting_opens=timezone.now() - timedelta(hours=2),
            voting_closes=timezone.now() - timedelta(hours=1))
        self.assertEqual(self._post().status_code, 403)  # already closed
        self.assertEqual(ProjectComment.objects.count(), 0)

    def test_body_length_and_blank_limits(self):
        self.client.force_login(self.author)
        self.assertEqual(self._post(body="").status_code, 400)
        self.assertEqual(self._post(body="   ").status_code, 400)
        self.assertEqual(self._post(body="x" * 2001).status_code, 400)
        self.assertEqual(self._post(body="x" * 2000).status_code, 201)
        self.assertEqual(ProjectComment.objects.count(), 1)

    def test_comments_on_draft_duplicate_and_foreign_projects_rejected(self):
        self.client.force_login(self.author)
        canonical = make_project(self.event, "canonical")
        make_project(self.event, "dup", duplicate_of=canonical)
        make_project(self.event, "draft", draft=True)
        for slug in ("dup", "draft"):
            resp = self.client.post(f"/projects/{slug}", {"event": "t3-ctrl", "body": "hi"})
            self.assertEqual(resp.status_code, 404, slug)
        self.assertEqual(self._post(path="/projects/foreign", event="t3-ctrl").status_code, 404)
        self.assertEqual(ProjectComment.objects.count(), 0)

    def test_throttle_is_scoped_per_event_not_per_project(self):
        self.client.force_login(self.author)
        make_project(self.event, "second")
        for i in range(3):
            self.assertEqual(self._post(body=f"a{i}").status_code, 201)
        for i in range(2):
            self.assertEqual(self.client.post("/projects/second",
                                              {"event": "t3-ctrl", "body": f"b{i}"}).status_code, 201)
        # Sixth comment inside the minute, even on another project, must be throttled.
        self.assertEqual(self.client.post("/projects/second",
                                          {"event": "t3-ctrl", "body": "sixth"}).status_code, 429)
        self.assertEqual(ProjectComment.objects.filter(event=self.event).count(), 5)

    def test_csrf_required_on_comment_post(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.author)
        resp = csrf_client.post("/projects/proj", {"event": "t3-ctrl", "body": "hi"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(ProjectComment.objects.count(), 0)
        csrf_client.get("/projects/proj", {"event": "t3-ctrl"})
        token = csrf_client.cookies["csrftoken"].value
        resp = csrf_client.post("/projects/proj", {"event": "t3-ctrl", "body": "hi"},
                                HTTP_X_CSRFTOKEN=token)
        self.assertEqual(resp.status_code, 201)


class CommentInactiveEventTests(TestCase):
    """The no-slug fallback must not make a deactivated event commentable."""

    def test_comment_does_not_fall_back_to_inactive_event(self):
        event = make_event("t3-cmt-inactive", active=False)
        make_project(event)
        author = make_user("author")
        self.client.force_login(author)
        resp = self.client.post("/projects/proj", {"body": "hi"})
        self.assertIn(resp.status_code, (401, 403, 404))
        self.assertEqual(ProjectComment.objects.count(), 0)
