# User-Organization 1:N Relation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `organization` ForeignKey to `UserProfile` and populate it via data migration from the existing M2M, as the first step in migrating from N:N to 1:N user-org membership.

**Architecture:** Since Django's built-in `User` model can't be modified directly, the `organization` FK is added to `UserProfile` (the existing `OneToOneField` extension of `User` in `batid`). A schema migration creates the nullable column; a separate data migration populates it from the existing `Organization.users` M2M. The M2M is left intact — consumers are not changed in this plan.

**Tech Stack:** Django 4.x, PostgreSQL, `batid` app migrations

---

## File Map

| Action | File |
|--------|------|
| Modify | `app/batid/models/others.py` — add `organization` FK to `UserProfile` |
| Create | `app/batid/migrations/0127_userprofile_organization.py` — schema migration (auto-generated) |
| Create | `app/batid/migrations/0128_populate_userprofile_organization.py` — data migration |
| Modify | `app/batid/tests/test_rnbuser.py` — add test for migration logic |

---

## Task 1: Add `organization` FK to `UserProfile`

**Files:**
- Modify: `app/batid/models/others.py:203-207`

- [ ] **Step 1: Add the ForeignKey field to `UserProfile`**

In `app/batid/models/others.py`, update `UserProfile` to:

```python
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    organization = models.ForeignKey(
        "Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="members",
    )
    job_title = models.CharField(max_length=255, blank=True, null=True)
    max_allowed_contributions = models.IntegerField(null=False, default=500)
    total_contributions = models.IntegerField(null=False, default=0)
```

- [ ] **Step 2: Generate the schema migration**

```bash
docker exec web python manage.py makemigrations batid --name userprofile_organization
```

Expected output:
```
Migrations for 'batid':
  batid/migrations/0127_userprofile_organization.py
    - Add field organization to userprofile
```

- [ ] **Step 3: Run the schema migration**

```bash
docker exec web python manage.py migrate batid
```

Expected: `OK` — no errors.

- [ ] **Step 4: Run existing tests to ensure nothing broke**

```bash
docker exec web python manage.py test batid.tests.test_rnbuser
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/batid/models/others.py app/batid/migrations/0127_userprofile_organization.py
git commit -m "feat: add organization FK to UserProfile (nullable, step 1 of N:N → 1:N)"
```

---

## Task 2: Write a test for the data migration logic

**Files:**
- Modify: `app/batid/tests/test_rnbuser.py`

The data migration logic (iterate org → users M2M, assign profile.organization) should be verified. We write the test first, then implement the migration.

- [ ] **Step 1: Write failing test for population logic**

Add this test class to `app/batid/tests/test_rnbuser.py`:

```python
class TestPopulateOrganizationOnProfile(TestCase):
    """
    After data migration: UserProfile.organization is set from M2M.
    - A user in exactly one org gets that org assigned.
    - A user in multiple orgs gets one of them assigned (first by pk).
    - A user in no org keeps organization=None.
    """

    def setUp(self):
        self.org_a = Organization.objects.create(name="Org A", managed_cities=["11000"])
        self.org_b = Organization.objects.create(name="Org B", managed_cities=["22000"])

        self.user_one_org = User.objects.create_user(username="one_org")
        UserProfile.objects.create(user=self.user_one_org)
        self.org_a.users.add(self.user_one_org)

        self.user_multi_org = User.objects.create_user(username="multi_org")
        UserProfile.objects.create(user=self.user_multi_org)
        self.org_a.users.add(self.user_multi_org)
        self.org_b.users.add(self.user_multi_org)

        self.user_no_org = User.objects.create_user(username="no_org")
        UserProfile.objects.create(user=self.user_no_org)

    def test_single_org_user_gets_org_assigned(self):
        populate_organization_on_profiles()
        self.user_one_org.profile.refresh_from_db()
        self.assertEqual(self.user_one_org.profile.organization, self.org_a)

    def test_multi_org_user_gets_first_org_by_pk(self):
        populate_organization_on_profiles()
        self.user_multi_org.profile.refresh_from_db()
        # first org by pk
        self.assertEqual(self.user_multi_org.profile.organization, self.org_a)

    def test_no_org_user_keeps_null(self):
        populate_organization_on_profiles()
        self.user_no_org.profile.refresh_from_db()
        self.assertIsNone(self.user_no_org.profile.organization)
```

Also add the import at the top of the file:

```python
from batid.models import UserProfile
from batid.services.org import populate_organization_on_profiles
```

- [ ] **Step 2: Run the test to verify it fails (function not yet defined)**

```bash
docker exec web python manage.py test batid.tests.test_rnbuser.TestPopulateOrganizationOnProfile
```

Expected: `ImportError` or `ModuleNotFoundError` — `populate_organization_on_profiles` doesn't exist yet.

- [ ] **Step 3: Create `app/batid/services/org.py` with the population function**

```python
from batid.models import Organization, UserProfile


def populate_organization_on_profiles():
    for org in Organization.objects.prefetch_related("users").order_by("pk"):
        for user in org.users.all():
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if profile.organization_id is None:
                profile.organization = org
                profile.save(update_fields=["organization"])
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
docker exec web python manage.py test batid.tests.test_rnbuser.TestPopulateOrganizationOnProfile
```

Expected: all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/batid/tests/test_rnbuser.py app/batid/services/org.py
git commit -m "feat: add populate_organization_on_profiles service + tests"
```

---

## Task 3: Write the data migration

**Files:**
- Create: `app/batid/migrations/0128_populate_userprofile_organization.py`

The migration calls the same logic but via `RunPython`. It must use the apps registry (not direct model imports) to be forwards-compatible.

- [ ] **Step 1: Create the data migration file**

Create `app/batid/migrations/0128_populate_userprofile_organization.py`:

```python
from django.db import migrations


def populate_organization(apps, schema_editor):
    Organization = apps.get_model("batid", "Organization")
    UserProfile = apps.get_model("batid", "UserProfile")

    for org in Organization.objects.prefetch_related("users").order_by("pk"):
        for user in org.users.all():
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if profile.organization_id is None:
                profile.organization = org
                profile.save(update_fields=["organization"])


def reverse_populate(apps, schema_editor):
    UserProfile = apps.get_model("batid", "UserProfile")
    UserProfile.objects.update(organization=None)


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0127_userprofile_organization"),
    ]

    operations = [
        migrations.RunPython(populate_organization, reverse_populate),
    ]
```

- [ ] **Step 2: Run the data migration**

```bash
docker exec web python manage.py migrate batid
```

Expected: `OK` — `0128_populate_userprofile_organization` runs without errors.

- [ ] **Step 3: Verify population in a shell check**

```bash
docker exec web python manage.py shell -c "
from batid.models import UserProfile
total = UserProfile.objects.count()
with_org = UserProfile.objects.filter(organization__isnull=False).count()
print(f'Total profiles: {total}, with org: {with_org}')
"
```

Expected: counts are printed without errors; `with_org` >= number of users that had org memberships.

- [ ] **Step 4: Run the full test suite**

```bash
docker exec web python manage.py test
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/batid/migrations/0128_populate_userprofile_organization.py
git commit -m "feat: data migration to populate UserProfile.organization from M2M"
```

---

## Self-Review

**Spec coverage:**
- ✅ New relation: `organization` FK added to `UserProfile` (Task 1)
- ✅ Migration to populate: data migration reads M2M, writes FK (Task 3)
- ✅ Multi-org users handled deterministically (first by pk wins, Tasks 2–3)
- ✅ M2M left intact — no consumers broken

**Placeholder scan:** None found.

**Type consistency:** `populate_organization_on_profiles` defined in Task 2 Step 3, imported in test in Task 2 Step 1. Migration in Task 3 uses `apps.get_model` (not direct import) — correct pattern for Django data migrations.
