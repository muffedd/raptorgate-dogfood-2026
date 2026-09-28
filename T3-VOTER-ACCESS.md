# Voter access modes

An organizer chooses `Event.voting_access` (`authenticated`, `email`, or `open`) before the vote window. The normal seeded event remains `authenticated`; no new token or email flow is activated unless the organizer selects the mode. All three modes still require an active event and `voting_opens <= now < voting_closes`. A voter gets one saved ballot for the active event, a random-looking stable ballot order and a private receipt. A public receipt can reveal the selected project only after voting closes and the organizer publishes. The organizer-only vote audit includes the voter key, so it is not a public document.

## Authenticated (default)

Sign in using a Django account, open `/ballot`, and POST `/vote` with `event` and `project`. A database unique constraint enforces one vote per account per event. Creating multiple accounts is still a Sybil route; registration or verified identity must be governed by the operator.

## One-use open links

The organizer POSTs `/organizer/vote/open-link` with `event=<active-slug>` while `voting_access=open` and the window is open. The response shows a 256-bit secret and a `redeem_url` once; only its SHA-256 digest is stored. Distribute one distinct URL to each intended voter through a trusted channel. A GET of the URL displays a confirmation form without consuming the link. The CSRF-protected POST to `/vote/open/redeem` claims it once, stores a session grant and opens `/ballot`; a second browser cannot redeem it. The token expires at voting close. Issuing unlimited open links does **not** provide Sybil resistance: the organizer decides the invitation audience. A stolen link can be claimed by the thief first, and possession of a copied session cookie carries ballot access. The URL and organizer response use `no-store` and `no-referrer` where served by the app, but distribution paths can still expose it.

## Verified email codes

Set `VOTER_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `VOTER_EMAIL_FROM`, `VOTER_SMTP_HOST`, `VOTER_SMTP_PORT` (default 587), `VOTER_SMTP_USER`, `VOTER_SMTP_PASSWORD`, and optionally `VOTER_SMTP_TLS` (default 1) in the deployment environment. The SMTP password is a secret: use a secret manager, not a committed Compose file or chat. Without a configured SMTP backend, sender and host, `/vote/email/request` returns 503 and creates no code. **The standard offline demo does not configure SMTP, so this mode cannot be live-tested offline.** It is not a claim that an external mail server is part of the self-hosted one-command stack.

While voting is open, GET `/vote/email/request` shows the two forms. POST the address to `/vote/email/request`: a cryptographically random six-digit code is sent, and its hash alone is saved for ten minutes or until voting closes. POST address and code to `/vote/email/redeem`: a correct, unexpired code is consumed once, granting a browser session. Wrong-code attempts are throttled per email+IP (five per minute), and requests for codes are throttled per email (three per minute). One normalized email has one voter key for that event, even if requested from different browsers; no new code issues after redemption or voting. It proves control of a mailbox at the time of code delivery, **not** a unique human. Aliases and multiple accounts remain a Sybil route. An SMTP error rolls back the challenge; no fake "sent" state is shown.

## Review boundaries

All token/code redemption uses POST; GET previews do not write state. Browser CSRF checks apply. The event is locked on redemption/voting so duplicate first claims serialize under PostgreSQL. Changing access mode invalidates prior session grants of a different mode. The organizer is responsible for mode selection, SMTP operations, link distribution and abuse review. No external email provider is required for default authenticated voting or open-link voting. The test suite uses mocked mail transport for the email mode and real PostgreSQL for concurrency-sensitive logic; an actual SMTP delivery and real-device cold boot must be checked separately before claiming operational readiness.
