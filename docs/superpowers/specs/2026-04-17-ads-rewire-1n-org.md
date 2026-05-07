# ADS Rewire to 1:N User-Organization — Design Spec

**Goal:** Replace all N:N (`Organization.users` M2M) usages with the new 1:N (`UserProfile.organization` FK) across the ADS feature and user provisioning, then remove the M2M field entirely.

**Architecture:** Single atomic sweep — update all read paths, write paths, and tests in one branch, then drop the M2M. The FK was already populated by migration `0128` so no data is lost. ADS is confirmed to be the only feature that uses the user-org relation for business logic.

---

## 1. Model — Remove M2M

**File:** `app/batid/models/others.py`

Remove from `Organization`:
```python
users = models.ManyToManyField(User, related_name="organizations")
```

The `User` import stays — it is still used by `ADS.creator`, `UserProfile.user`, and other FKs in the same file.

---

## 2. Migration — Drop M2M Join Table

**File:** `app/batid/migrations/0129_remove_organization_users.py` (auto-generated)

Run `makemigrations batid --name remove_organization_users`. Expected: single `RemoveField` operation removing `organization.users`. The historical state in migrations `0127`–`0128` is unaffected — they reference the M2M at its historical point and will continue to work correctly on fresh database setups.

---

## 3. ADS Read Path — `get_managed_insee_codes`

**File:** `app/batid/services/ads.py`

Replace the M2M loop with a single FK lookup:

```python
def get_managed_insee_codes(user: User) -> list:
    profile = getattr(user, "profile", None)
    if not profile or not profile.organization_id:
        return []
    return list(profile.organization.managed_cities or [])
```

No changes needed to `can_manage_ads_in_cities`, `can_manage_ads`, or `can_manage_ads_in_request` — they all consume the list this function returns.

---

## 4. Write Path — `create_token.py`

**File:** `app/api_alpha/endpoints/ads/create_token.py`

Replace:
```python
organization.users.add(user)
organization.save()
```

With:
```python
profile, _ = UserProfile.objects.get_or_create(user=user)
profile.organization = organization
profile.save(update_fields=["organization"])
```

Add import: `from batid.models import UserProfile`

Response shape is unchanged.

---

## 5. Write Path — `create_user.py` (dead code removal)

**File:** `app/api_alpha/endpoints/auth/create_user.py`

Remove the entire organization block (lines 64–87: `organization_serializer`, `organization_name` handling, `organization.users.add(user)`).

Remove now-unused imports: `OrganizationSerializer`, `Organization`.

Simplify response to:
```python
return Response({"user": user_serializer.data}, status=status.HTTP_201_CREATED)
```

`create_user_in_sandbox` still passes `organization_name` in its dict — leave that call unchanged (harmless dead data in the sandbox task).

---

## 6. Service — `org.py`

**File:** `app/batid/services/org.py`

Add a comment block at the top of the file explaining that `populate_organization_on_profiles` relied on the `Organization.users` M2M that was removed when migrating from N:N to 1:N (the function populated `UserProfile.organization` from the M2M as a one-time migration step). Comment out the entire function body.

---

## 7. Tests

### `app/batid/tests/test_rnbuser.py`

- **Remove** the entire `TestPopulateOrganizationOnProfile` class (the function it tested is now commented out).
- **Rewrite** `TestRNBUser.setUp` and `test_user_can_manage_ads`:
  - User belongs to one org (use profile FK: `user.profile.organization = org`)
  - `test_user_can_manage_ads` asserts `get_managed_insee_codes(u)` returns that org's managed cities only

### `app/api_alpha/tests/auth/test_user_creation.py`

- Remove `"organization_name": "Mairie d'Angoulème"` from `julie_data` in `setUp` (the endpoint ignores it — dead code on the client side too)
- Remove all `prefetch_related("organizations", ...)` → replace with `prefetch_related("profile")`
- Remove assertions on `julie.organizations.all()` (lines 51–53, 333)
- Remove `test_create_user_no_orga` entirely — its purpose (creating a user without an org) is now always the default; keeping it would require removing the now-absent `pop("organization_name")` and its name would be misleading
- Remove `"organization_name": None` entries from any remaining data dicts (lines 314, 359)

### `app/api_alpha/tests/test_ads.py` (lines 44, 1297, 1319)

Replace each `org.users.add(user)` with:
```python
user.profile.organization = org
user.profile.save(update_fields=["organization"])
```
Ensure a `UserProfile` exists for the user before each assignment (use `get_or_create` if needed).

### `app/api_alpha/tests/buildings/test_diff.py` (lines 36, 752)

Same replacement as above.

### `app/api_alpha/tests/buildings/test_listing.py` (line 553)

Same replacement — `org.users.add(u)` → profile FK assignment.

### `app/api_alpha/tests/test_history.py` (line 33)

Replace `org.users.set([user])` → profile FK assignment.

---

## 8. Scope Confirmation

ADS is the **only feature** that uses the user-org relation for business logic. Other usages found were:
- User provisioning (`create_user`, `create_token`) — covered above
- `services/org.py` populate function — covered above
- Test setup code — covered above

No other views, serializers, or services query user-org membership.
