from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.test import TestCase

from batid.models.building import Building
from batid.models.others import Address
from batid.models.others import UserProfile
from batid.models.report import Report
from batid.services.reports.missing_addresses import generate_missing_addresses_reports
from batid.tests.helpers import create_cenac


class TestReportMissingAddress(TestCase):
    def setUp(self):
        create_cenac()
        self.team_rnb = User.objects.create_user(username="RNB")
        UserProfile.objects.create(user=self.team_rnb)

        # big building without addresse
        self.building_big_1 = Building.create_new(
            user=self.team_rnb,
            event_origin={"source": "contribution"},
            status="constructed",
            ext_ids=[],
            addresses_id=[],
            shape=GEOSGeometry(
                "MULTIPOLYGON (((-0.461835346162282 44.780330739483055, -0.461869398243609 44.78024676706472, -0.461647586080402 44.78017889959611, -0.461571050481471 44.78029213577993, -0.461631513507299 44.7803082703171, -0.461682970250236 44.78032198267502, -0.461737008167366 44.78033651554237, -0.461718353375455 44.78036233139951, -0.461731203726445 44.78036553461921, -0.461653848356848 44.78048600590834, -0.461706734345818 44.78050237714365, -0.461711896658586 44.7805040182115, -0.461810487846199 44.78035855154345, -0.461797471288518 44.78035264998929, -0.461818596387651 44.78032585575459, -0.461835346162282 44.780330739483055)))"
            ),
        )
        # another big building without addresse
        self.building_big_2 = Building.create_new(
            user=self.team_rnb,
            event_origin={"source": "contribution"},
            status="constructed",
            ext_ids=[],
            addresses_id=[],
            shape=GEOSGeometry(
                "MULTIPOLYGON (((-0.461876864672691 44.78024473141581, -0.461869398243609 44.78024676706472, -0.461835346162282 44.780330739483055, -0.461846989040444 44.78033488159562, -0.461736223746844 44.780508665212686, -0.461785598151372 44.78052965202224, -0.461907685198161 44.7803753405331, -0.462018132251471 44.7804223555182, -0.462089229694154 44.780405715080256, -0.462124024674465 44.78037488892027, -0.461876864672691 44.78024473141581)))"
            ),
        )
        self.building_big_3 = Building.create_new(
            user=self.team_rnb,
            event_origin={"source": "contribution"},
            status="constructed",
            ext_ids=[],
            addresses_id=[],
            shape=GEOSGeometry(
                "POLYGON ((-0.4628715893841748 44.779960414994314, -0.4626095317390703 44.77989651083929, -0.4626523116069119 44.77981046302721, -0.4627090936343491 44.77972577994417, -0.4628299083215278 44.779756248843704, -0.4628287562952108 44.77975808720783, -0.4629106440901578 44.779793377364264, -0.4629142026437432 44.779871668737734, -0.4628715893841748 44.779960414994314))"
            ),
        )

        # big building with address
        address = Address.objects.create(id="33118_0032_00011")
        self.building_big_with_address = Building.create_new(
            user=self.team_rnb,
            event_origin={"source": "contribution"},
            status="constructed",
            ext_ids=[],
            addresses_id=[address.id],
            shape=GEOSGeometry(
                "MULTIPOLYGON (((-0.462476883434677 44.78020795838789, -0.462504666596858 44.7802070901377, -0.462503779998349 44.78019269897809, -0.462596024966123 44.78019071736439, -0.46259419630951 44.780161035599434, -0.462604299268587 44.78016071986221, -0.462603123924666 44.78012110470905, -0.462587969496673 44.78012157831438, -0.462587847024005 44.780099052662194, -0.462568903996241 44.78009964466591, -0.46256988979798 44.780095107962026, -0.462293099933925 44.780100153059884, -0.462294152703952 44.780117242563385, -0.46227147646813 44.78011885235481, -0.462251270561168 44.78011948376766, -0.46225016239588 44.780101494816165, -0.462227541573033 44.78010400404616, -0.462209030294825 44.78009106481172, -0.462190142673042 44.780092556198305, -0.4621536417805 44.780116226257135, -0.462153320825416 44.780131556328904, -0.462178379576187 44.78016862280944, -0.462195838131195 44.78016447254454, -0.462211989912607 44.78018018904985, -0.462241700833964 44.78019007477423, -0.462242698181825 44.780206264831136, -0.462279321444546 44.78020512039542, -0.462279808592129 44.780192488665676, -0.462302540266577 44.78019177832008, -0.462303426813576 44.78020616948132, -0.4623110040402 44.78020593269835, -0.462310616174985 44.780199636565335, -0.462476218491074 44.780197165018, -0.462476883434677 44.78020795838789)))"
            ),
        )

        # big building no address demolished
        self.building_big_demolished = Building.create_new(
            user=self.team_rnb,
            event_origin={"source": "contribution"},
            status="demolished",
            ext_ids=[],
            addresses_id=[],
            shape=GEOSGeometry(
                "MULTIPOLYGON (((-0.462476883434677 44.78020795838789, -0.462504666596858 44.7802070901377, -0.462503779998349 44.78019269897809, -0.462596024966123 44.78019071736439, -0.46259419630951 44.780161035599434, -0.462604299268587 44.78016071986221, -0.462603123924666 44.78012110470905, -0.462587969496673 44.78012157831438, -0.462587847024005 44.780099052662194, -0.462568903996241 44.78009964466591, -0.46256988979798 44.780095107962026, -0.462293099933925 44.780100153059884, -0.462294152703952 44.780117242563385, -0.46227147646813 44.78011885235481, -0.462251270561168 44.78011948376766, -0.46225016239588 44.780101494816165, -0.462227541573033 44.78010400404616, -0.462209030294825 44.78009106481172, -0.462190142673042 44.780092556198305, -0.4621536417805 44.780116226257135, -0.462153320825416 44.780131556328904, -0.462178379576187 44.78016862280944, -0.462195838131195 44.78016447254454, -0.462211989912607 44.78018018904985, -0.462241700833964 44.78019007477423, -0.462242698181825 44.780206264831136, -0.462279321444546 44.78020512039542, -0.462279808592129 44.780192488665676, -0.462302540266577 44.78019177832008, -0.462303426813576 44.78020616948132, -0.4623110040402 44.78020593269835, -0.462310616174985 44.780199636565335, -0.462476218491074 44.780197165018, -0.462476883434677 44.78020795838789)))"
            ),
        )

        # big building no address inactive
        self.building_big_inactive = Building.create_new(
            user=self.team_rnb,
            event_origin={"source": "contribution"},
            status="constructed",
            ext_ids=[],
            addresses_id=[],
            shape=GEOSGeometry(
                "MULTIPOLYGON (((-0.462476883434677 44.78020795838789, -0.462504666596858 44.7802070901377, -0.462503779998349 44.78019269897809, -0.462596024966123 44.78019071736439, -0.46259419630951 44.780161035599434, -0.462604299268587 44.78016071986221, -0.462603123924666 44.78012110470905, -0.462587969496673 44.78012157831438, -0.462587847024005 44.780099052662194, -0.462568903996241 44.78009964466591, -0.46256988979798 44.780095107962026, -0.462293099933925 44.780100153059884, -0.462294152703952 44.780117242563385, -0.46227147646813 44.78011885235481, -0.462251270561168 44.78011948376766, -0.46225016239588 44.780101494816165, -0.462227541573033 44.78010400404616, -0.462209030294825 44.78009106481172, -0.462190142673042 44.780092556198305, -0.4621536417805 44.780116226257135, -0.462153320825416 44.780131556328904, -0.462178379576187 44.78016862280944, -0.462195838131195 44.78016447254454, -0.462211989912607 44.78018018904985, -0.462241700833964 44.78019007477423, -0.462242698181825 44.780206264831136, -0.462279321444546 44.78020512039542, -0.462279808592129 44.780192488665676, -0.462302540266577 44.78019177832008, -0.462303426813576 44.78020616948132, -0.4623110040402 44.78020593269835, -0.462310616174985 44.780199636565335, -0.462476218491074 44.780197165018, -0.462476883434677 44.78020795838789)))"
            ),
        )
        self.building_big_inactive.deactivate(self.team_rnb, {"source": "contribution"})

        # small building without address
        self.building_small = Building.create_new(
            user=self.team_rnb,
            event_origin={"source": "contribution"},
            status="constructed",
            ext_ids=[],
            addresses_id=[],
            shape=GEOSGeometry(
                "MULTIPOLYGON (((-0.461336387675506 44.78011833010794, -0.461351586317342 44.780098029364254, -0.46137992338583 44.78010615587617, -0.46136483554025 44.78012825551985, -0.461336387675506 44.78011833010794)))"
            ),
        )

    def test_create_reports(self):
        reports = Report.objects.all()
        self.assertEqual(len(reports), 0)

        generate_missing_addresses_reports(2, "33118")

        reports = Report.objects.all()
        self.assertEqual(len(reports), 2)

        [report_1, report_2] = reports
        self.assertEqual(report_1.status, "pending")
        self.assertEqual(report_1.created_by_user, self.team_rnb)
        self.assertEqual(report_1.messages.count(), 1)  # type: ignore
        self.assertEqual(report_1.messages.first().text, "Ce bâtiment d'une surface supérieure à 50m² n'a pas d'adresse associée.")  # type: ignore

        self.assertEqual(report_2.status, "pending")
        self.assertEqual(report_2.created_by_user, self.team_rnb)
        self.assertEqual(report_2.messages.count(), 1)  # type: ignore
        self.assertEqual(report_2.messages.first().text, "Ce bâtiment d'une surface supérieure à 50m² n'a pas d'adresse associée.")  # type: ignore

        self.assertEqual(report_1.creation_batch_uuid, report_2.creation_batch_uuid)

        rnb_ids_reported = {report.building.rnb_id for report in reports}
        missing_report = {
            self.building_big_1.rnb_id,
            self.building_big_2.rnb_id,
            self.building_big_3.rnb_id,
        } - rnb_ids_reported
        missing_report = missing_report.pop()

        generate_missing_addresses_reports(2, "33118")

        reports = Report.objects.all().order_by("created_at")
        self.assertEqual(len(reports), 3)

        new_report = reports[2]
        self.assertEqual(new_report.building.rnb_id, missing_report)
        self.assertEqual(new_report.created_by_user, self.team_rnb)
        self.assertEqual(new_report.messages.count(), 1)  # type: ignore
        self.assertEqual(
            new_report.messages.first().text,
            "Ce bâtiment d'une surface supérieure à 50m² n'a pas d'adresse associée.",
        )
