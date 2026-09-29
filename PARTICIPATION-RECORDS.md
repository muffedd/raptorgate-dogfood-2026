# Judge participation records (T4 slice)

Configure a separate random `RECORD_SIGNING_KEY` of at least 32 characters in the server environment and keep it secret. Without it, issuance and verification return 503. The checked-in local Compose demo key and the Django fallback secret must not sign records. Organizer issuance after voting close and result publication: POST `/organizer/records/issue` with `judge=<slug>` (authenticated superuser session and CSRF). A judge must have at least one eligible canonical score. First issue freezes an event/judge/review-count/time payload, backed by an HMAC-SHA256 signature keyed with this separate secret. Repeat calls return the existing record, not a mutable update. Public GET `/records/<id>/verify` reports the snapshot, signature and current signature validity only while public results are available; it exposes no judge score, criteria or comment.

Trust model: the server holds a symmetric secret and also writes the database rows. Its `valid` response checks for a match between a row and the server-held key, not independent authenticity; a server operator with the key can forge or replace both. This proves a record matches a particular deployment's current signing key and stored payload; it is not a portable certificate, a signed PDF, a cryptographic proof that a judge actually reviewed a project, or a third-party-verifiable signature. Exporting the signing key to verify elsewhere would compromise the application. Rotating the record signing key invalidates old records unless keys/verification are migrated. The organizer should not issue these for a privacy-sensitive event without first deciding whether judge slug and review count can be public. No automatic batch issuance or judge-facing certificate UI is shipped.

## Portable public ballot acceptance proof

`GET /receipt/<secret>/proof` after result publication returns an Ed25519
signature over the event, project, secret receipt and cast timestamp. The
organizer must configure `CERTIFICATE_PRIVATE_KEY_PEM`; without it this route
fails closed with 503. Save the JSON and run `python verify.py proof.json
--trusted-public-key <organizer-key>` to verify offline. The key must be
obtained through a trusted organizer channel, not merely copied from the
proof. Possession of the secret receipt permits anyone to reveal that ballot's
choice after publication; keep it private unless sharing is intentional.
There is no proof of voter identity or unique humanity. The proof is signed
on demand, so key rotation changes the signature; preserve the old key for
long-lived proofs. Pre-publication requests return 404.
