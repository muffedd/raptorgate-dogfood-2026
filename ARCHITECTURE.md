# Architecture

The portal is a self-hosted Django application with PostgreSQL in Docker Compose. The start command migrates and seeds the bundled official fixtures only when no event exists; it does not overwrite a live event. The web service is bound to 127.0.0.1. Django sessions identify roles, with score access checked on the server: a judge can fetch only their own rows, and an organizer alone can export CSV. The data path is fixtures.json -> Django models -> gallery and role-gated APIs. At this stage the T1/T2 checker is the acceptance target, not a complete production system.
