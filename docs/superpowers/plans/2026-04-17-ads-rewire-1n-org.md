# ADS Rewire to 1:N User-Organization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every usage of the `Organization.users` M2M with the `UserProfile.organization` FK across ADS authorization, user provisioning, and tests, then drop the M2M field entirely.

**Architecture:** The FK (`UserProfile.organization`) was already populated by migration `0128`. We update the read path first (TDD), then test setups, then write paths, then remove the M2M field. ADS is the only feature using the user-org relation for business logic — no other consumers exist.

**Tech Stack:** Django 6, PostgreSQL, DRF, `batid` app, `api_alpha` app

---

## File Map

| Action | File | What changes |
|--------|------|--------------|
| Modify | `app/batid/services/ads.py` | `get_managed_insee_codes` reads FK instead of M2M |
| Modify | `app/batid/tests/test_rnbuser.py` | Rewrite TestRNBUser; remove TestPopulateOrganizationOnProfile |
| Modify | `app/api_alpha/tests/test_ads.py` | Replace `org.users.add(user)` with FK in 3 setUps |
| Modify | `app/api_alpha/tests/buildings/test_diff.py` | Replace `org.users.add(user)` with FK in 2 setUps |
| Modify | `app/api_alpha/tests/buildings/test_listing.py` | Replace `org.users.add(u)` with FK in setUp |
| Modify | `app/api_alpha/tests/test_history.py` | Replace `org.users.set([user])` with FK; add UserProfile import |
| Modify | `app/api_alpha/tests/auth/test_user_creation.py` | Remove dead org assertions/data; remove test_create_user_no_orga |
| Modify | `app/api_alpha/endpoints/auth/create_user.py` | Remove org block + dead imports; simplify response |
| Modify | `app/api_alpha/endpoints/ads/create_token.py` | Replace M2M write with FK assignment |
| Modify | `app/batid/services/org.py` | Comment out function; add explanation |
| Modify | `app/batid/models/others.py` | Remove `users` ManyToManyField from `Organization` |
| Create | `app/batid/migrations/0129_remove_organization_users.py` | Auto-generated: drops join table |

---

## Task 1: Update `get_managed_insee_codes` (TDD)

Read path: switch from iterating `user.organizations.all()` (M2M) to reading `user.profile.organization` (FK). Write the failing test first.

**Files:**
- Modify: `app/batid/tests/test_rnbuser.py`
- Modify: `app/batid/services/ads.py:12-17`

- [ ] **Step 1: Rewrite `TestRNBUser` and remove `TestPopulateOrganizationOnProfile` in `test_rnbuser.py`**

Replace the entire file content with:

```python
from django.contrib.auth.models import User
from django.test import TestCase

from batid.models import Organization
from batid.models import UserProfile
from batid.services.ads import get_managed_insee_codes


class TestRNBUser(TestCase):
    def setUp(self):
        u = User.objects.create_user(
            first_name="John", last_name="Doe", username="johndoe", email="john@doe.com"
        )
        org = Organization.objects.create(
            name="Test Org", managed_cities=["12345", "67890"]
        )
        profile, _ = UserProfile.objects.get_or_create(user=u)
        profile.organization = org
        profile.save(update_fields=["organization"])

    def test_user_can_manage_ads(self):
        """User with one org gets managed cities from that org only."""
        u = User.objects.get(username="johndoe")
        managed_codes = get_managed_insee_codes(u)
        managed_codes.sort()
        self.assertListEqual(managed_codes, ["12345", "67890"])
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
docker exec web python manage.py test batid.tests.test_rnbuser.TestRNBUser
```

Expected: FAIL — `get_managed_insee_codes` still uses M2M; user has no M2M membership → returns `[]` → assertion fails.

- [ ] **Step 3: Update `get_managed_insee_codes` in `app/batid/services/ads.py`**

Replace lines 12–17:

```python
def get_managed_insee_codes(user: User) -> list:
    profile = getattr(user, "profile", None)
    if not profile or not profile.organization_id:
        return []
    return list(profile.organization.managed_cities or [])
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
docker exec web python manage.py test batid.tests.test_rnbuser.TestRNBUser
```

Expected: PASS — 1 test.

- [ ] **Step 5: Commit**

```bash
git add app/batid/tests/test_rnbuser.py app/batid/services/ads.py
git commit -m "feat: switch get_managed_insee_codes to use UserProfile.organization FK"
```

---

## Task 2: Update ADS-related test setups

After Task 1, `get_managed_insee_codes` uses the FK. All test setups that used `org.users.add(user)` must switch to FK assignment — otherwise those tests will fail (user has no FK org, permission check returns False).

**Files:**
- Modify: `app/api_alpha/tests/test_ads.py:43-44`, `1296-1297`, `1319`
- Modify: `app/api_alpha/tests/buildings/test_diff.py:35-36`, `751-752`
- Modify: `app/api_alpha/tests/buildings/test_listing.py:552-553`
- Modify: `app/api_alpha/tests/test_history.py:32-33`

- [ ] **Step 1: Update `test_ads.py` setUp at line 43–44**

`test_ads.py` imports `Organization` but not `UserProfile`. Add the import at the top:

```python
from batid.models import UserProfile
```

Then replace lines 43–44:
```python
# Before:
org = Organization.objects.create(name="Test Org", managed_cities=["38185"])
org.users.add(user)

# After:
org = Organization.objects.create(name="Test Org", managed_cities=["38185"])
profile, _ = UserProfile.objects.get_or_create(user=user)
profile.organization = org
profile.save(update_fields=["organization"])
```

- [ ] **Step 2: Update `test_ads.py` setUp at lines 1296–1297 and 1319**

Replace the block around line 1296:
```python
# Before:
org = Organization.objects.create(name="Test Org", managed_cities=["38185"])
org.users.add(self.user)

# After:
org = Organization.objects.create(name="Test Org", managed_cities=["38185"])
profile, _ = UserProfile.objects.get_or_create(user=self.user)
profile.organization = org
profile.save(update_fields=["organization"])
```

Replace line 1319:
```python
# Before:
org.users.add(self.superuser)

# After:
profile, _ = UserProfile.objects.get_or_create(user=self.superuser)
profile.organization = org
profile.save(update_fields=["organization"])
```

- [ ] **Step 3: Run `test_ads.py` to verify it passes**

```bash
docker exec web python manage.py test api_alpha.tests.test_ads
```

Expected: all tests pass (same count as before).

- [ ] **Step 4: Update `test_diff.py` setUp at lines 35–36**

`UserProfile` is already imported. Replace:
```python
# Before:
UserProfile.objects.create(user=user)
org = Organization.objects.create(name="Mairie Marseille")
org.users.add(user)

# After:
profile = UserProfile.objects.create(user=user)
org = Organization.objects.create(name="Mairie Marseille")
profile.organization = org
profile.save(update_fields=["organization"])
```

- [ ] **Step 5: Update `test_diff.py` setUp at lines 750–752**

Replace:
```python
# Before:
UserProfile.objects.create(user=user)
org = Organization.objects.create(name="Test Org")
org.users.add(user)

# After:
profile = UserProfile.objects.create(user=user)
org = Organization.objects.create(name="Test Org")
profile.organization = org
profile.save(update_fields=["organization"])
```

- [ ] **Step 6: Run `test_diff.py` to verify it passes**

```bash
docker exec web python manage.py test api_alpha.tests.buildings.test_diff
```

Expected: all tests pass.

- [ ] **Step 7: Update `test_listing.py` setUp at lines 552–553**

`UserProfile` is already imported. Replace:
```python
# Before:
u = User.objects.create_user(
    first_name="John", last_name="Doe", username="johndoe"
)
org = Organization.objects.create(name="Test Org", managed_cities=["38185"])
org.users.add(u)

# After:
u = User.objects.create_user(
    first_name="John", last_name="Doe", username="johndoe"
)
org = Organization.objects.create(name="Test Org", managed_cities=["38185"])
profile, _ = UserProfile.objects.get_or_create(user=u)
profile.organization = org
profile.save(update_fields=["organization"])
```

- [ ] **Step 8: Run `test_listing.py` to verify it passes**

```bash
docker exec web python manage.py test api_alpha.tests.buildings.test_listing
```

Expected: all tests pass.

- [ ] **Step 9: Update `test_history.py` at lines 32–33**

Add `UserProfile` import (not currently present):
```python
from batid.models import UserProfile
```

Replace lines 32–33:
```python
# Before:
org = Organization.objects.create(name="Mairie de Dreux")
org.users.set([user])

# After:
org = Organization.objects.create(name="Mairie de Dreux")
user.profile.organization = org
user.profile.save(update_fields=["organization"])
```

(`ContributorUserFactory` creates a `UserProfile` via `UserProfileFactory`, so `user.profile` exists.)

- [ ] **Step 10: Run `test_history.py` to verify it passes**

```bash
docker exec web python manage.py test api_alpha.tests.test_history
```

Expected: all tests pass.

- [ ] **Step 11: Commit**

```bash
git add app/api_alpha/tests/test_ads.py \
        app/api_alpha/tests/buildings/test_diff.py \
        app/api_alpha/tests/buildings/test_listing.py \
        app/api_alpha/tests/test_history.py
git commit -m "test: switch ADS test setups from M2M to UserProfile.organization FK"
```

---

## Task 3: Clean up `test_user_creation.py`

Remove dead `organization_name` data and `organizations.all()` assertions. The `create_user` endpoint never used `organization_name` in practice.

**Files:**
- Modify: `app/api_alpha/tests/auth/test_user_creation.py`

- [ ] **Step 1: Remove `organization_name` from `setUp`'s `julie_data`**

In `setUp` (class `UserCreation`), `julie_data` currently has:
```python
"organization_name": "Mairie d'Angoulème",
```
Remove that line entirely.

- [ ] **Step 2: Fix `test_create_user` — remove org assertions and fix prefetch**

In `test_create_user`, change:
```python
# Before:
julie = User.objects.prefetch_related("organizations", "profile").get(
    first_name="Julie"
)
...
self.assertEqual(len(julie.organizations.all()), 1)
orgas = julie.organizations.all()
self.assertEqual(orgas[0].name, "Mairie d'Angoulème")

# After:
julie = User.objects.prefetch_related("profile").get(
    first_name="Julie"
)
# (remove the three organization assertions entirely)
```

- [ ] **Step 3: Remove `test_create_user_no_orga` entirely**

Delete the whole method (lines 104–109):
```python
@mock.patch("api_alpha.endpoints.auth.create_user.validate_captcha")
def test_create_user_no_orga(self, mock_validate_captcha):
    # come as you are: someone can create an account without having a job or an organization
    self.julie_data.pop("organization_name")
    response = self.client.post("/api/alpha/auth/users/", self.julie_data)
    self.assertEqual(response.status_code, 201)
```

- [ ] **Step 4: Fix `prefetch_related` calls in remaining tests**

The following tests have `prefetch_related("organizations", "profile")` — change each to `prefetch_related("profile")`:
- `test_full_account_activation_scenario` (line 134)
- `test_dont_mess_with_activation_to` (line 177)

- [ ] **Step 5: Clean up `test_works_with_empty_organization_name_and_job_title`**

This test overrides `self.julie_data` with a local dict that has `"organization_name": None`. Remove that key:

```python
# Before:
self.julie_data = {
    "last_name": "B",
    "first_name": "Julie",
    "email": "julie.b+test@exemple.com",
    "username": "juju",
    "password": "tajine1234!",
    "organization_name": None,
    "job_title": None,
}

# After:
self.julie_data = {
    "last_name": "B",
    "first_name": "Julie",
    "email": "julie.b+test@exemple.com",
    "username": "juju",
    "password": "tajine1234!",
    "job_title": None,
}
```

Also fix in the same test:
```python
# Before:
julie = User.objects.prefetch_related("organizations", "profile").get(...)
...
self.assertEqual(len(julie.organizations.all()), 0)

# After:
julie = User.objects.prefetch_related("profile").get(...)
# (remove the organizations.all() assertion)
```

- [ ] **Step 6: Clean up `test_password_requirements`**

Remove `"organization_name": None` from its local `julie_data` dict (line 359):

```python
# Before:
self.julie_data = {
    "last_name": "Beach",
    "first_name": "Julie",
    "email": "Superjuju+test@exemple.com",
    "username": "juju",
    "password": "Superjuju+test@exemple.com",
    "organization_name": None,
    "job_title": None,
}

# After:
self.julie_data = {
    "last_name": "Beach",
    "first_name": "Julie",
    "email": "Superjuju+test@exemple.com",
    "username": "juju",
    "password": "Superjuju+test@exemple.com",
    "job_title": None,
}
```

- [ ] **Step 7: Run `test_user_creation.py` to verify it passes**

```bash
docker exec web python manage.py test api_alpha.tests.auth.test_user_creation
```

Expected: all tests pass (one fewer test — `test_create_user_no_orga` removed).

- [ ] **Step 8: Commit**

```bash
git add app/api_alpha/tests/auth/test_user_creation.py
git commit -m "test: remove dead organization assertions from test_user_creation"
```

---

## Task 4: Update `create_user.py` (dead code removal)

Remove the organization block that never ran in practice.

**Files:**
- Modify: `app/api_alpha/endpoints/auth/create_user.py`

- [ ] **Step 1: Remove the organization block and clean up imports**

Replace the full file with:

```python
import private_captcha
from django.conf import settings
from django.db import transaction
from django.http import QueryDict
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api_alpha.exceptions import BadRequest
from api_alpha.serializers.serializers import UserSerializer
from batid.tasks import create_sandbox_user


def create_user_in_sandbox(user_data: dict) -> None:
    user_data_without_password = {
        "first_name": user_data["first_name"],
        "last_name": user_data["last_name"],
        "email": user_data["email"],
        "username": user_data["username"],
        "job_title": user_data.get("job_title", None),
    }
    create_sandbox_user.delay(user_data_without_password)


def is_captcha_valid(captcha_solution: str) -> bool:
    if (
        settings.PRIVATE_CAPTCHA_API_KEY is None
        or settings.PRIVATE_CAPTCHA_SITEKEY is None
    ):
        raise AssertionError(
            "PRIVATE_CAPTCHA_API_KEY or PRIVATE_CAPTCHA_SITEKEY is not set but ENABLE_CAPTCHA is True. Please check your settings."
        )
    client = private_captcha.Client(api_key=settings.PRIVATE_CAPTCHA_API_KEY)
    result = client.verify(
        solution=captcha_solution, sitekey=settings.PRIVATE_CAPTCHA_SITEKEY
    )
    return result.ok()


def validate_captcha(captcha_solution: str) -> None:
    if not settings.ENABLE_CAPTCHA:
        return

    if not is_captcha_valid(captcha_solution):
        raise BadRequest(detail="Captcha verification failed")


class CreateUserView(APIView):
    throttle_scope = "create_user"

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        request_data = request.data
        if isinstance(request_data, QueryDict):
            request_data = request_data.dict()
        validate_captcha(request_data.get("captcha_solution"))
        user_serializer = UserSerializer(data=request_data)
        user_serializer.is_valid(raise_exception=True)
        user = user_serializer.save()

        if settings.HAS_SANDBOX:
            create_user_in_sandbox(request_data)

        return Response(
            {"user": user_serializer.data},
            status=status.HTTP_201_CREATED,
        )
```

Key changes vs. original:
- Removed imports: `OrganizationSerializer`, `Organization`, `QueryDict` (moved to inside if-block originally — still needed, keep it)
- Actually keep `QueryDict` import — it's used in the view
- Removed `organization_name` from `create_user_in_sandbox`'s dict
- Removed the org block (lines 64–87) from `post()`
- Response now just `{"user": user_serializer.data}`

- [ ] **Step 2: Run `test_user_creation.py` to verify it still passes**

```bash
docker exec web python manage.py test api_alpha.tests.auth.test_user_creation
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add app/api_alpha/endpoints/auth/create_user.py
git commit -m "feat: remove dead organization block from create_user endpoint"
```

---

## Task 5: Update `create_token.py` and comment out `org.py`

**Files:**
- Modify: `app/api_alpha/endpoints/ads/create_token.py`
- Modify: `app/batid/services/org.py`

- [ ] **Step 1: Update `create_token.py` to assign FK instead of M2M**

Replace the full file with:

```python
import json
from typing import Any

from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponse
from django.http import JsonResponse
from drf_spectacular.utils import extend_schema
from rest_framework.authtoken.models import Token
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from batid.models import Organization
from batid.models import UserProfile
from batid.utils.constants import ADS_GROUP_NAME


class IsSuperUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)


@extend_schema(exclude=True)
class CreateAdsTokenView(APIView):
    permission_classes = [IsSuperUser]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> HttpResponse:
        try:
            with transaction.atomic():
                json_users = json.loads(request.body)
                users = []

                for json_user in json_users:
                    user, created = User.objects.get_or_create(
                        username=json_user["username"],
                        defaults={
                            "email": json_user.get("email", None),
                        },
                    )

                    group, created = Group.objects.get_or_create(name=ADS_GROUP_NAME)
                    user.groups.add(group)
                    user.set_unusable_password()
                    user.save()

                    organization, created = Organization.objects.get_or_create(
                        name=json_user["organization_name"],
                        defaults={
                            "managed_cities": json_user["organization_managed_cities"]
                        },
                    )

                    profile, _ = UserProfile.objects.get_or_create(user=user)
                    profile.organization = organization
                    profile.save(update_fields=["organization"])

                    token, created = Token.objects.get_or_create(user=user)

                    users.append(
                        {
                            "username": user.username,
                            "organization_name": json_user["organization_name"],
                            "email": user.email,
                            "token": token.key,
                        }
                    )

                return JsonResponse({"created_users": users})
        except json.JSONDecodeError:
            return HttpResponse("Invalid JSON", status=400)
```

- [ ] **Step 2: Update `app/batid/services/org.py` — comment out function**

Replace the file with:

```python
# populate_organization_on_profiles was a one-time helper that populated
# UserProfile.organization from the Organization.users M2M relation.
# The M2M was removed when migrating from N:N to 1:N user-org membership
# (migration 0129). The function is kept here for reference only.

# from batid.models import Organization, UserProfile
#
#
# def populate_organization_on_profiles():
#     for org in Organization.objects.prefetch_related("users").order_by("pk"):
#         for user in org.users.all():
#             profile, _ = UserProfile.objects.get_or_create(user=user)
#             if profile.organization_id is None:
#                 profile.organization = org
#                 profile.save(update_fields=["organization"])
```

- [ ] **Step 3: Run full test suite to verify everything still passes**

```bash
docker exec web python manage.py test
```

Expected: all tests pass (same count minus the removed test).

- [ ] **Step 4: Commit**

```bash
git add app/api_alpha/endpoints/ads/create_token.py app/batid/services/org.py
git commit -m "feat: switch create_token to use UserProfile.organization FK; archive org service"
```

---

## Task 6: Remove M2M field and migration

**Files:**
- Modify: `app/batid/models/others.py`
- Create: `app/batid/migrations/0129_remove_organization_users.py` (auto-generated)

- [ ] **Step 1: Remove the M2M field from `Organization`**

In `app/batid/models/others.py`, remove this line from the `Organization` class:

```python
users = models.ManyToManyField(User, related_name="organizations")
```

The `User` import stays — it is still used by `ADS.creator`, `UserProfile.user`, and other FK fields in the same file.

- [ ] **Step 2: Generate the migration**

```bash
docker exec web python manage.py makemigrations batid --name remove_organization_users
```

Expected output:
```
Migrations for 'batid':
  batid/migrations/0129_remove_organization_users.py
    - Remove field users from organization
```

The generated migration will contain a single `RemoveField` operation. Migrations `0127`–`0128` reference the M2M at their historical point and are unaffected.

- [ ] **Step 3: Apply the migration**

```bash
docker exec web python manage.py migrate batid
```

Expected: `OK`.

- [ ] **Step 4: Run the full test suite**

```bash
docker exec web python manage.py test
```

Expected: all tests pass. No reference to `organizations` M2M remains in production code or test setups.

- [ ] **Step 5: Commit**

```bash
git add app/batid/models/others.py app/batid/migrations/0129_remove_organization_users.py
git commit -m "feat: remove Organization.users M2M — 1:N user-org migration complete"
```

---

## Self-Review

**Spec coverage:**
- ✅ Section 1 (Remove M2M): Task 6
- ✅ Section 2 (Migration): Task 6
- ✅ Section 3 (`get_managed_insee_codes`): Task 1
- ✅ Section 4 (`create_token.py`): Task 5
- ✅ Section 5 (`create_user.py`): Task 4
- ✅ Section 6 (`org.py` comment): Task 5
- ✅ Section 7 (all test files): Tasks 1, 2, 3

**Placeholder scan:** None found.

**Type consistency:** `UserProfile.organization` used consistently throughout. `profile.save(update_fields=["organization"])` pattern used identically in all tasks.
