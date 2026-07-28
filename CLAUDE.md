# Tests

- run tests using the command: docker exec web python manage.py test
- use a subagent to run test, make it report only the result to you
- when working on a feature, execute only tests concerning this feature during developpemnt phase
- write an explicit (concise input description, expected results) docstring when you create or update a test

# Glossary

- a "bâtiment réel" (real building) is a building with a physical presence on the ground (status field, see the BuildingStatus class) and matching the definition of a building (is_active field)
