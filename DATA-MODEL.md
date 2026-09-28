# Data model

An Event owns Tracks, Teams, Projects, and Judges. Team membership links Django users to teams. A Project belongs to one team and track and may point to a canonical project when duplicated. A Judge owns one row per scored project with a database uniqueness constraint. Criteria are stored as JSON; this is a temporary implementation choice until rubric editing and formal validation land. The fixture import is idempotent on event/slug keys, but manual reseeding is not a general migration path. Organizer CSV export offers a way out; full import/export is not yet implemented.
