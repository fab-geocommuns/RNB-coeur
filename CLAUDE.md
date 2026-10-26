# Code style

- write all code comments and docstrings in English

# Tests

- run tests using the command: docker exec web python manage.py test
- use a subagent to run test, make it report only the result to you
- when working on a feature, execute only tests concerning this feature during developpemnt phase
- write an explicit (concise input description, expected results) docstring when you create or update a test

# Migrations

- deploys have no downtime: the previous code runs ~1 min 30 on the new schema, so every migration must work with it (see "Déploiement et migrations" in readme.md)
- rename a field with `db_column="old_name"`, not a database rename
- drop a field in two deploys: first a state-only `SeparateDatabaseAndState` (column made nullable if `NOT NULL`), then `DROP COLUMN` later

# Glossary

- a "bâtiment réel" (real building) is a building with a physical presence on the ground (status field, see the BuildingStatus class) and matching the definition of a building (is_active field)
