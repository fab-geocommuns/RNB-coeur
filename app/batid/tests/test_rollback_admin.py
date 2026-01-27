from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.test import override_settings
from django.test import TransactionTestCase

from batid.models.building import Building
from batid.models.others import DataFix
from batid.models.others import UserProfile


class RollbackAdminTestCase(TransactionTestCase):
    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def setUp(self):
        # Create Rollback group
        self.rollback_group = Group.objects.create(name="Rollback")

        # Staff user with Rollback group (has access)
        self.rollback_user = User.objects.create_user(
            username="rollback_staff",
            email="rollback@test.com",
            password="password",
            is_staff=True,
        )
        self.rollback_user.groups.add(self.rollback_group)
        UserProfile.objects.create(user=self.rollback_user)

        # Regular user (non-staff, no group)
        self.regular_user = User.objects.create_user(
            username="regular", email="regular@test.com", password="password"
        )
        UserProfile.objects.create(user=self.regular_user)

        # Staff user without Rollback group (no access)
        self.staff_no_group = User.objects.create_user(
            username="staff_no_group",
            email="staff@test.com",
            password="password",
            is_staff=True,
        )
        UserProfile.objects.create(user=self.staff_no_group)

        # Contributor user whose events will be rolled back
        self.contributor = User.objects.create_user(
            username="contributor", email="contributor@test.com", password="password"
        )
        UserProfile.objects.create(user=self.contributor)

        # RNB user for reverts
        self.team_rnb = User.objects.create_user(username="RNB")
        UserProfile.objects.create(user=self.team_rnb)

        # Create buildings for tests
        self.shape = GEOSGeometry("POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))")
        self.building = Building.create_new(
            user=self.contributor,
            event_origin={"source": "contribution", "contribution_id": 1},
            status="constructed",
            addresses_id=[],
            shape=self.shape,
            ext_ids=[],
        )


class RollbackAdminPermissionsTest(RollbackAdminTestCase):
    def test_rollback_view_anonymous_redirects(self):
        """An unauthenticated user is redirected to login"""
        response = self.client.get("/admin/rollback/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_rollback_view_regular_user_forbidden(self):
        """A regular user (non-staff) receives 302 (redirect to login)"""
        self.client.force_login(self.regular_user)
        response = self.client.get("/admin/rollback/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_rollback_view_staff_without_group_forbidden(self):
        """A staff user without Rollback group receives 302 (redirect to login)"""
        self.client.force_login(self.staff_no_group)
        response = self.client.get("/admin/rollback/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_rollback_view_staff_with_rollback_group_access(self):
        """A staff user with Rollback group can access the page"""
        self.client.force_login(self.rollback_user)
        response = self.client.get("/admin/rollback/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Utilisateur")

    def test_rollback_confirm_anonymous_redirects(self):
        """An unauthenticated user is redirected to login"""
        response = self.client.get("/admin/rollback/confirm/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_rollback_confirm_regular_user_forbidden(self):
        """A regular user receives 302 (redirect to login)"""
        self.client.force_login(self.regular_user)
        response = self.client.get("/admin/rollback/confirm/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_rollback_confirm_staff_without_group_forbidden(self):
        """A staff user without Rollback group receives 302 (redirect to login)"""
        self.client.force_login(self.staff_no_group)
        response = self.client.get("/admin/rollback/confirm/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)


class RollbackFormTest(RollbackAdminTestCase):
    def test_rollback_form_displays_fields(self):
        """Verify presence of user, start_time, end_time fields"""
        self.client.force_login(self.rollback_user)
        response = self.client.get("/admin/rollback/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Utilisateur")
        self.assertContains(response, "start_time")
        self.assertContains(response, "end_time")

    def test_rollback_form_has_dry_run_button(self):
        """Verify Dry Run button"""
        self.client.force_login(self.rollback_user)
        response = self.client.get("/admin/rollback/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dry_run")

    def test_rollback_form_has_rollback_button(self):
        """Verify Rollback button"""
        self.client.force_login(self.rollback_user)
        response = self.client.get("/admin/rollback/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rollback")


class RollbackDryRunTest(RollbackAdminTestCase):
    def test_dry_run_without_dates(self):
        """Dry run returns results without modifying the database"""
        self.client.force_login(self.rollback_user)

        # Count buildings before
        buildings_count_before = Building.objects.count()
        active_buildings_before = Building.objects.filter(is_active=True).count()

        response = self.client.post(
            "/admin/rollback/",
            {
                "user": self.contributor.id,
                "dry_run": "dry_run",
            },
        )

        self.assertEqual(response.status_code, 200)

        # Verify no modifications were made
        self.assertEqual(Building.objects.count(), buildings_count_before)
        self.assertEqual(
            Building.objects.filter(is_active=True).count(), active_buildings_before
        )

        # Verify results are displayed
        self.assertContains(response, "events")
        self.assertContains(response, "revertable")
        self.assertContains(response, self.contributor.username)

    def test_dry_run_with_date_range(self):
        """Dry run correctly filters by time period"""
        self.client.force_login(self.rollback_user)

        self.building.refresh_from_db()
        start_time = self.building.sys_period.lower

        response = self.client.post(
            "/admin/rollback/",
            {
                "user": self.contributor.id,
                "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "dry_run": "dry_run",
            },
        )

        self.assertEqual(response.status_code, 200)
        # 1 event found
        self.assertContains(response, "1 events trouv")

    def test_dry_run_no_database_changes(self):
        """Verify no database modifications are made"""
        self.client.force_login(self.rollback_user)

        # Save initial state
        self.building.refresh_from_db()
        building_sys_period_before = self.building.sys_period

        self.client.post(
            "/admin/rollback/",
            {
                "user": self.contributor.id,
                "dry_run": "dry_run",
            },
        )

        # Verify building has not changed
        self.building.refresh_from_db()
        self.assertEqual(self.building.sys_period, building_sys_period_before)

    def test_dry_run_user_not_found(self):
        """Non-existent user selected - validation error"""
        self.client.force_login(self.rollback_user)

        response = self.client.post(
            "/admin/rollback/",
            {
                "user": 99999,
                "dry_run": "dry_run",
            },
        )

        # Form should return a validation error
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].errors,
            {
                "user": [
                    "Sélectionnez un choix valide. Ce choix ne fait pas partie de ceux disponibles."
                ]
            },
        )


class RollbackConfirmTest(RollbackAdminTestCase):
    def test_rollback_redirects_to_confirm(self):
        """Rollback button redirects to confirmation page"""
        self.client.force_login(self.rollback_user)

        response = self.client.post(
            "/admin/rollback/",
            {
                "user": self.contributor.id,
                "rollback": "rollback",
            },
        )

        # Should redirect to confirmation page
        self.assertEqual(response.status_code, 302)
        self.assertIn("confirm", response.url)

    def test_confirm_page_requires_session(self):
        """Confirmation page without session redirects to form"""
        self.client.force_login(self.rollback_user)

        response = self.client.get("/admin/rollback/confirm/")

        # Without session, should redirect to rollback
        self.assertEqual(response.status_code, 302)

    def test_confirm_cancel_returns_to_form(self):
        """Cancel button returns to form"""
        self.client.force_login(self.rollback_user)

        # Configure session
        session = self.client.session
        session["rollback_user_id"] = self.contributor.id
        session["rollback_start_time"] = None
        session["rollback_end_time"] = None
        session.save()

        response = self.client.post(
            "/admin/rollback/confirm/",
            {
                "cancel": "true",
            },
        )

        # Should redirect to form
        self.assertEqual(response.status_code, 302)
        self.assertEqual("/admin/rollback/", response.url)

    @override_settings(BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_confirm_executes_rollback(self):
        """Confirmation executes the rollback"""
        self.client.force_login(self.rollback_user)

        # Configure session with rollback parameters
        session = self.client.session
        session["rollback_user_id"] = self.contributor.id
        session["rollback_start_time"] = None
        session["rollback_end_time"] = None
        session.save()

        response = self.client.post(
            "/admin/rollback/confirm/",
            {
                "confirm": "true",
            },
        )

        self.assertEqual(response.status_code, 200)

        # Verify building has been reverted
        self.building.refresh_from_db()
        self.assertFalse(self.building.is_active)
        self.assertEqual(self.building.event_type, "revert_creation")

    @override_settings(BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_rollback_creates_datafix(self):
        """Rollback creates a DataFix"""
        self.client.force_login(self.rollback_user)

        datafix_count_before = DataFix.objects.count()

        session = self.client.session
        session["rollback_user_id"] = self.contributor.id
        session["rollback_start_time"] = None
        session["rollback_end_time"] = None
        session.save()

        self.client.post(
            "/admin/rollback/confirm/",
            {
                "confirm": "true",
            },
        )

        self.assertEqual(DataFix.objects.count(), datafix_count_before + 1)

        datafix = DataFix.objects.latest("id")
        self.assertIn(self.contributor.username, datafix.text)


class RollbackFlowTest(RollbackAdminTestCase):
    @override_settings(BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_full_rollback_flow(self):
        """Test complete flow: form -> confirmation -> execution"""
        self.client.force_login(self.rollback_user)

        # Step 1: Submit form with rollback action
        response = self.client.post(
            "/admin/rollback/",
            {
                "user": self.contributor.id,
                "rollback": "rollback",
            },
        )

        # Should redirect to confirmation
        self.assertEqual(response.status_code, 302)
        self.assertIn("confirm", response.url)

        # Step 2: Confirm the rollback
        response = self.client.post(
            "/admin/rollback/confirm/",
            {
                "confirm": "true",
            },
        )

        self.assertEqual(response.status_code, 200)

        # Verify building has been reverted
        self.building.refresh_from_db()
        self.assertFalse(self.building.is_active)
        self.assertEqual(self.building.event_type, "revert_creation")

        # Verify a DataFix has been created
        datafix = DataFix.objects.latest("id")
        self.assertIn(self.contributor.username, datafix.text)

    @override_settings(BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_dry_run_then_rollback(self):
        """Test: dry run then actual rollback"""
        self.client.force_login(self.rollback_user)

        # Step 1: Dry run
        response = self.client.post(
            "/admin/rollback/",
            {
                "user": self.contributor.id,
                "dry_run": "dry_run",
            },
        )
        self.assertEqual(response.status_code, 200)

        # Building should not be modified
        self.building.refresh_from_db()
        self.assertTrue(self.building.is_active)

        # Step 2: Actual rollback
        response = self.client.post(
            "/admin/rollback/",
            {
                "user": self.contributor.id,
                "rollback": "rollback",
            },
        )
        self.assertEqual(response.status_code, 302)

        # Step 3: Confirm
        response = self.client.post(
            "/admin/rollback/confirm/",
            {
                "confirm": "true",
            },
        )
        self.assertEqual(response.status_code, 200)

        # Building should be reverted
        self.building.refresh_from_db()
        self.assertFalse(self.building.is_active)


class RollbackWithDatesTest(RollbackAdminTestCase):
    @override_settings(MAX_BUILDING_AREA=float("inf"), BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_rollback_with_start_date(self):
        """Rollback with start date"""
        self.client.force_login(self.rollback_user)

        # Create a second building after
        building_2 = Building.create_new(
            user=self.contributor,
            event_origin={"source": "contribution", "contribution_id": 2},
            status="constructed",
            addresses_id=[],
            shape=GEOSGeometry("POLYGON((2 0, 2 1, 3 1, 3 0, 2 0))"),
            ext_ids=[],
        )
        building_2.refresh_from_db()
        start_time = building_2.sys_period.lower

        # Configure session with start_time
        session = self.client.session
        session["rollback_user_id"] = self.contributor.id
        session["rollback_start_time"] = start_time.isoformat()
        session["rollback_end_time"] = None
        session.save()

        response = self.client.post(
            "/admin/rollback/confirm/",
            {
                "confirm": "true",
            },
        )

        self.assertEqual(response.status_code, 200)

        # One building only should be reverted
        self.building.refresh_from_db()
        self.assertTrue(self.building.is_active)
        self.assertEqual(self.building.event_type, "creation")

        building_2.refresh_from_db()
        self.assertFalse(building_2.is_active)
        self.assertEqual(building_2.event_type, "revert_creation")

    @override_settings(MAX_BUILDING_AREA=float("inf"), BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_rollback_with_end_date(self):
        """Rollback with end date (excludes events after)"""
        self.client.force_login(self.rollback_user)

        self.building.refresh_from_db()
        end_time = self.building.sys_period.lower

        # Create a second building after
        building_2 = Building.create_new(
            user=self.contributor,
            event_origin={"source": "contribution", "contribution_id": 2},
            status="constructed",
            addresses_id=[],
            shape=GEOSGeometry("POLYGON((2 0, 2 1, 3 1, 3 0, 2 0))"),
            ext_ids=[],
        )

        # Configure session with end_time (before building_2)
        session = self.client.session
        session["rollback_user_id"] = self.contributor.id
        session["rollback_start_time"] = None
        session["rollback_end_time"] = end_time.isoformat()
        session.save()

        response = self.client.post(
            "/admin/rollback/confirm/",
            {
                "confirm": "true",
            },
        )

        self.assertEqual(response.status_code, 200)

        # Only the first building should be reverted
        self.building.refresh_from_db()
        self.assertFalse(self.building.is_active)

        # Second building is not affected
        building_2.refresh_from_db()
        self.assertTrue(building_2.is_active)
