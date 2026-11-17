from unittest.mock import patch

from batid.services.tchap import (
    Code,
    TchapLevel,
    notify_if_error,
    notify_tech,
    notify_tech_or_log,
)
from batid.tasks import (
    create_sandbox_user,
    import_cities,
    import_plots,
    remove_light_buildings,
    send_monthly_leaderboard_emails,
)
from django.test import TestCase, override_settings


class Decorator(TestCase):
    def test_function_without_error(self):
        """
        Test that the decorated function returns the correct output without error.
        """

        @notify_if_error
        def test_func():
            return "Success"

        result = test_func()
        self.assertEqual(result, "Success")

    @patch("batid.services.tchap.notify_tech")
    def test_function_with_error(self, notify):
        """
        Input: a decorated function raising Exception("Forced error").
        Expected: the exception is re-raised and one failure notification is sent,
        generic title, the function name as a Code "Fonction" detail, the error
        text in the error block.
        """

        @notify_if_error
        def test_func():
            raise Exception("Forced error")

        with self.assertRaises(Exception) as context:
            test_func()

        self.assertTrue("Forced error" in str(context.exception))

        notify.assert_called_once_with(
            level=TchapLevel.FAILURE,
            title="Échec d'une fonction",
            details=[("Fonction", "test_func")],
            error="Forced error",
        )
        self.assertIsInstance(notify.call_args.kwargs["details"][0][1], Code)


class NotifyTaskFailure(TestCase):
    @patch("batid.services.tchap.notify_tech")
    @patch("batid.tasks.import_etalab_plots_job", side_effect=Exception("boom"))
    def test_final_failure_notifies_once(self, job, notify):
        """
        Input: import_plots (max_retries=3) raises on every attempt, run through
        Celery with its retries.
        Expected: 4 attempts, the task ends in FAILURE and one single failure
        notification is sent: generic title, task name as "Tâche", task id as
        "Identifiant" and task arguments as "Arguments" details, all Code, "boom"
        as error.
        """
        result = import_plots.apply(args=["75", "2026-01-01"])

        self.assertEqual(result.state, "FAILURE")
        self.assertEqual(job.call_count, 4)
        notify.assert_called_once_with(
            level=TchapLevel.FAILURE,
            title="Échec de la tâche",
            details=[
                ("Tâche", "batid.tasks.import_plots"),
                ("Identifiant", result.id),
                ("Arguments", "'75', '2026-01-01'"),
            ],
            error="boom",
        )
        for _label, value in notify.call_args.kwargs["details"]:
            self.assertIsInstance(value, Code)

    @patch("batid.services.tchap.notify_tech")
    @patch("batid.tasks.import_etalab_cities", side_effect=Exception("boom"))
    def test_failure_shows_the_department(self, job, notify):
        """
        Input: import_cities fails for good on department "2A".
        Expected: one failure message whose "Arguments" detail is the Code "'2A'".
        """
        result = import_cities.apply(args=["2A"])

        notify.assert_called_once_with(
            level=TchapLevel.FAILURE,
            title="Échec de la tâche",
            details=[
                ("Tâche", "batid.tasks.import_cities"),
                ("Identifiant", result.id),
                ("Arguments", "'2A'"),
            ],
            error="boom",
        )
        self.assertIsInstance(notify.call_args.kwargs["details"][2][1], Code)

    @patch("batid.services.tchap.notify_tech")
    @patch("batid.tasks.import_etalab_cities", side_effect=Exception("boom"))
    def test_long_arguments_are_cut(self, job, notify):
        """
        Input: import_cities fails for good with a 600-character argument.
        Expected: the "Arguments" detail is cut to 500 characters ending with "…".
        """
        result = import_cities.apply(args=["x" * 600])

        notify.assert_called_once_with(
            level=TchapLevel.FAILURE,
            title="Échec de la tâche",
            details=[
                ("Tâche", "batid.tasks.import_cities"),
                ("Identifiant", result.id),
                ("Arguments", "'" + "x" * 498 + "…"),
            ],
            error="boom",
        )

    @patch("batid.services.tchap.notify_tech")
    @patch("batid.tasks.SandboxClient")
    def test_sandbox_user_arguments_are_masked(self, client, notify):
        """
        Input: create_sandbox_user fails for good on a user with the e-mail a@b.fr.
        Expected: the "Arguments" detail is "masqués" and the e-mail is in no detail.
        """
        client.return_value.create_user.side_effect = Exception("boom")

        result = create_sandbox_user.apply(args=[{"email": "a@b.fr"}])

        notify.assert_called_once_with(
            level=TchapLevel.FAILURE,
            title="Échec de la tâche",
            details=[
                ("Tâche", "batid.tasks.create_sandbox_user"),
                ("Identifiant", result.id),
                ("Arguments", "masqués"),
            ],
            error="boom",
        )
        for _label, value in notify.call_args.kwargs["details"]:
            self.assertNotIn("a@b.fr", value)

    @patch("batid.services.tchap.notify_tech")
    @patch("batid.tasks.remove_light_buildings_job", side_effect=Exception("boom"))
    def test_light_buildings_arguments_are_masked(self, job, notify):
        """
        Input: remove_light_buildings fails for good for the username "jdupont".
        Expected: the "Arguments" detail is "masqués" and the username is in no
        detail.
        """
        result = remove_light_buildings.apply(args=["folder", "jdupont", 1])

        notify.assert_called_once_with(
            level=TchapLevel.FAILURE,
            title="Échec de la tâche",
            details=[
                ("Tâche", "batid.tasks.remove_light_buildings"),
                ("Identifiant", result.id),
                ("Arguments", "masqués"),
            ],
            error="boom",
        )
        for _label, value in notify.call_args.kwargs["details"]:
            self.assertNotIn("jdupont", value)

    @patch("batid.services.tchap.notify_tech")
    @patch("batid.tasks.import_etalab_plots_job", side_effect=[Exception("boom"), None])
    def test_success_after_retry_does_not_notify(self, job, notify):
        """
        Input: import_plots fails on its first attempt and succeeds on the retry.
        Expected: the task ends in SUCCESS and no notification is sent.
        """
        result = import_plots.apply(args=["75", "2026-01-01"])

        self.assertEqual(result.state, "SUCCESS")
        notify.assert_not_called()

    @patch("batid.services.tchap.notify_tech")
    @patch("batid.tasks.import_etalab_cities", side_effect=Exception("boom"))
    def test_any_task_notifies(self, job, notify):
        """
        Input: import_cities, a task that never carried a notification decorator,
        fails for good.
        Expected: the task ends in FAILURE and one notification is sent.
        """
        result = import_cities.apply(args=["75"])

        self.assertEqual(result.state, "FAILURE")
        notify.assert_called_once()

    @patch("batid.services.tchap.notify_tech", side_effect=Exception("tchap down"))
    @patch("batid.tasks.import_etalab_plots_job", side_effect=Exception("boom"))
    def test_tchap_down_does_not_change_task_state(self, job, notify):
        """
        Input: import_plots fails for good and sending the notification raises.
        Expected: the task still ends in FAILURE with its own error, the notification
        was attempted once and Celery logs the receiver error.
        """
        with self.assertLogs("celery.utils.dispatch.signal", level="ERROR") as logs:
            result = import_plots.apply(args=["75", "2026-01-01"])

        self.assertEqual(result.state, "FAILURE")
        self.assertEqual(str(result.result), "boom")
        notify.assert_called_once()
        self.assertEqual(len(logs.records), 1)

    @patch("batid.services.tchap.notify_tech")
    @patch("batid.tasks.notify_tech", side_effect=Exception("tchap down"))
    @patch(
        "batid.services.leaderboard.send_monthly_leaderboard_emails",
        return_value="3 envois pour octobre 2026",
    )
    def test_tchap_down_does_not_resend_leaderboard_emails(
        self, send, notify, receiver_notify
    ):
        """
        Input: the leaderboard emails are sent, then the Tchap report raises.
        Expected: the task ends in SUCCESS with the send summary, the emails are
        sent once, the Tchap report was attempted once with the summary as "Bilan"
        detail, the error is logged and no failure alert is sent.
        """
        with self.assertLogs("batid.tasks", level="ERROR"):
            result = send_monthly_leaderboard_emails.apply()

        self.assertEqual(result.state, "SUCCESS")
        self.assertEqual(result.result, "3 envois pour octobre 2026")
        send.assert_called_once()
        notify.assert_called_once_with(
            level=TchapLevel.SUCCESS,
            title="Mail mensuel du classement",
            details=[("Bilan", "3 envois pour octobre 2026")],
        )
        receiver_notify.assert_not_called()

    def test_delay_on_former_decorated_task(self):
        """
        Input: .delay on import_plots, a task that used to carry @notify_if_error
        above @shared_task.
        Expected: the call is sent to Celery through apply_async with the task
        arguments.
        """
        with patch.object(import_plots, "apply_async") as apply_async:
            import_plots.delay("75", "2026-01-01")

        apply_async.assert_called_once_with(("75", "2026-01-01"), {})


class NotifyTechOrLog(TestCase):
    @patch("batid.services.tchap.notify_tech", side_effect=Exception("tchap down"))
    def test_tchap_down_is_logged(self, notify):
        """
        Input: notify_tech_or_log with a success message, notify_tech raising.
        Expected: no exception, the message was attempted once with the same
        arguments and one ERROR record with the stack trace is logged.
        """
        with self.assertLogs("batid.services.tchap", level="ERROR") as logs:
            notify_tech_or_log(
                level=TchapLevel.SUCCESS, title="hello", details=[("Zone", "01")]
            )

        notify.assert_called_once_with(
            level=TchapLevel.SUCCESS,
            title="hello",
            details=[("Zone", "01")],
            error=None,
        )
        self.assertEqual(len(logs.records), 1)
        self.assertIsNotNone(logs.records[0].exc_info)


class NotifyTech(TestCase):
    @override_settings(TCHAP_NOTIFICATIONS=False)
    @patch("batid.services.tchap.requests.put")
    def test_inactive_notifications(self, put_mock):
        """
        Input: notifications are disabled in settings.
        Expected: no HTTP request is made.
        """
        notify_tech(level=TchapLevel.SUCCESS, title="hello")
        put_mock.assert_not_called()

    @override_settings(TCHAP_NOTIFICATIONS=True)
    @patch.dict(
        "os.environ",
        {
            "TCHAP_HOMESERVER_URL": "https://matrix.example.gouv.fr/",
            "TCHAP_ACCESS_TOKEN": "syt_secret",
            "TCHAP_ROOM_ID": "!room:example.gouv.fr",
        },
    )
    @patch("batid.services.tchap.requests.put")
    def test_message_is_sent_to_the_room(self, put_mock):
        """
        Input: notifications are enabled and the Tchap env vars are set, two
        launch messages titled "hello" with one "Départements" detail.
        Expected: one PUT per message on the Matrix send endpoint of the room, with
        the bearer token, a unique transaction id and a m.text payload: plain text
        body and HTML formatted_body, level dot then bold title, one line per detail.
        """
        put_mock.return_value.status_code = 200

        for _ in range(2):
            notify_tech(
                level=TchapLevel.LAUNCH,
                title="hello",
                details=[("Départements", "01 à 976")],
            )

        self.assertEqual(put_mock.call_count, 2)
        first, second = put_mock.call_args_list

        url = first.args[0]
        self.assertTrue(
            url.startswith(
                "https://matrix.example.gouv.fr/_matrix/client/v3/rooms/%21room%3Aexample.gouv.fr/send/m.room.message/"
            )
        )
        self.assertNotEqual(url, second.args[0])
        self.assertEqual(
            first.kwargs["json"],
            {
                "msgtype": "m.text",
                "body": "🔵 hello\nDépartements : 01 à 976",
                "format": "org.matrix.custom.html",
                "formatted_body": "<b>🔵 hello</b><br>Départements : 01 à 976",
            },
        )
        self.assertEqual(
            first.kwargs["headers"], {"Authorization": "Bearer syt_secret"}
        )

    @override_settings(TCHAP_NOTIFICATIONS=True)
    @patch.dict(
        "os.environ",
        {
            "TCHAP_HOMESERVER_URL": "https://matrix.example.gouv.fr",
            "TCHAP_ACCESS_TOKEN": "syt_secret",
            "TCHAP_ROOM_ID": "!room:example.gouv.fr",
        },
    )
    @patch("batid.services.tchap.requests.put")
    def test_matrix_error_raises(self, put_mock):
        """
        Input: the Matrix API answers with a 401 (e.g. revoked token).
        Expected: an exception is raised, mentioning the status code.
        """
        put_mock.return_value.status_code = 401
        put_mock.return_value.text = '{"errcode":"M_UNKNOWN_TOKEN"}'

        with self.assertRaises(Exception) as context:
            notify_tech(level=TchapLevel.SUCCESS, title="hello")
        self.assertIn("401", str(context.exception))
        self.assertIn("M_UNKNOWN_TOKEN", str(context.exception))

    @override_settings(TCHAP_NOTIFICATIONS=True)
    @patch.dict(
        "os.environ",
        {"TCHAP_HOMESERVER_URL": "", "TCHAP_ACCESS_TOKEN": "", "TCHAP_ROOM_ID": ""},
    )
    @patch("batid.services.tchap.requests.put")
    def test_missing_configuration_raises(self, put_mock):
        """
        Input: notifications are enabled but the Tchap env vars are empty.
        Expected: an explicit exception, no HTTP request.
        """
        with self.assertRaises(Exception) as context:
            notify_tech(level=TchapLevel.SUCCESS, title="hello")
        self.assertIn("TCHAP_", str(context.exception))
        put_mock.assert_not_called()

    @override_settings(TCHAP_NOTIFICATIONS=True)
    @patch.dict(
        "os.environ",
        {
            "TCHAP_HOMESERVER_URL": "https://matrix.example.gouv.fr",
            "TCHAP_ACCESS_TOKEN": "syt_secret",
            "TCHAP_ROOM_ID": "!room:example.gouv.fr",
        },
    )
    @patch("batid.services.tchap.requests.put")
    def test_error_block_and_escaping(self, put_mock):
        """
        Input: failure message whose title, detail and two-line error contain
        "<script>" and "&".
        Expected: body keeps the raw text and the newline; formatted_body escapes
        every value, holds the error in a <pre><code> block with its newline, and
        contains no raw "<script>".
        """
        put_mock.return_value.status_code = 200

        notify_tech(
            level=TchapLevel.FAILURE,
            title="<script>title</script>",
            details=[("Zone", "a & b")],
            error="line 1 <script>\nline 2 & co",
        )

        payload = put_mock.call_args.kwargs["json"]
        self.assertEqual(
            payload["body"],
            "🔴 <script>title</script>\nZone : a & b\nline 1 <script>\nline 2 & co",
        )
        self.assertEqual(
            payload["formatted_body"],
            "<b>🔴 &lt;script&gt;title&lt;/script&gt;</b><br>Zone : a &amp; b"
            "<pre><code>line 1 &lt;script&gt;\nline 2 &amp; co</code></pre>",
        )
        self.assertNotIn("<script>", payload["formatted_body"])

    @override_settings(TCHAP_NOTIFICATIONS=True)
    @patch.dict(
        "os.environ",
        {
            "TCHAP_HOMESERVER_URL": "https://matrix.example.gouv.fr",
            "TCHAP_ACCESS_TOKEN": "syt_secret",
            "TCHAP_ROOM_ID": "!room:example.gouv.fr",
        },
    )
    @patch("batid.services.tchap.requests.put")
    def test_error_truncated(self, put_mock):
        """
        Input: a 1 500-char error, "a" * 998 + "<" + "b" * 501, so that "<" is the
        last kept character.
        Expected: the error part of body is 1 000 chars ending with "<…";
        formatted_body ends with "a&lt;…</code></pre>" (cut before escaping, no
        split entity).
        """
        put_mock.return_value.status_code = 200

        notify_tech(
            level=TchapLevel.FAILURE,
            title="hello",
            error="a" * 998 + "<" + "b" * 501,
        )

        payload = put_mock.call_args.kwargs["json"]
        error_part = payload["body"].split("\n", 1)[1]
        self.assertEqual(len(error_part), 1000)
        self.assertTrue(error_part.endswith("<…"))
        self.assertTrue(payload["formatted_body"].endswith("a&lt;…</code></pre>"))

    @override_settings(TCHAP_NOTIFICATIONS=True)
    @patch.dict(
        "os.environ",
        {
            "TCHAP_HOMESERVER_URL": "https://matrix.example.gouv.fr",
            "TCHAP_ACCESS_TOKEN": "syt_secret",
            "TCHAP_ROOM_ID": "!room:example.gouv.fr",
        },
    )
    @patch("batid.services.tchap.requests.put")
    def test_code_detail(self, put_mock):
        """
        Input: success message with a Code detail "a<b>&c" and a plain detail "x<y".
        Expected: body shows both values as raw text; formatted_body wraps only the
        Code value in <code>, escaped, and escapes the plain value without <code>.
        """
        put_mock.return_value.status_code = 200

        notify_tech(
            level=TchapLevel.SUCCESS,
            title="hello",
            details=[("Nom", Code("a<b>&c")), ("Zone", "x<y")],
        )

        payload = put_mock.call_args.kwargs["json"]
        self.assertEqual(payload["body"], "🟢 hello\nNom : a<b>&c\nZone : x<y")
        self.assertEqual(
            payload["formatted_body"],
            "<b>🟢 hello</b><br>Nom : <code>a&lt;b&gt;&amp;c</code><br>Zone : x&lt;y",
        )
