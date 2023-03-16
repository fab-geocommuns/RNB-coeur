from pprint import pprint

from django.core.management import BaseCommand

from batid.models import Candidate, Building
from django.conf import settings
from django.db import connections
from django.utils.timezone import now
from batid.logic.building import generate_id


class Command(BaseCommand):

    BATCH_SIZE = 200000

    def __init__(self):
        super().__init__()

        self.stats = {
            'created': 0,
            'updated': 0,
            'refused': 0,
            'multiple_matches': 0,
        }

    def handle(self, *args, **options):

        # get some candidates not inspected yet
        candidates = self.__get_candidates()

        for idx, c in enumerate(candidates):
            print(idx)
            self.__inspect(c)

        pprint(self.stats)

    def __get_candidates(self):

        return Candidate.objects.filter(inspected_at__isnull=True).order_by('created_at')[:self.BATCH_SIZE]

    def __inspect(self, c):

        area = c.shape.area
        if area < settings.MIN_BDG_AREA:
            self.__refuse(c)
            print('too small')

        matches = self.__get_matches(c)

        if len(matches) == 0:
            self.__create_new_building(c)

            # print('create new building')

        if len(matches) == 1:
            self.__update_building(c)
            print('update building')

        if len(matches) > 1:
            self.stats['multiple_matches'] += 1
            print('too many matches')

    def __get_matches(self, c):

        q = "SELECT b.id as b_id " \
            "FROM batid_building b " \
            "WHERE ST_Intersects(b.shape, %(c_shape)s) AND ST_Area(ST_Intersection(b.shape, %(c_shape)s)) / %(c_area)s >= %(min_intersect_ratio)s " \

        params = {
            "c_shape": f"{c.shape}",
            "c_area": c.shape.area,
            "min_intersect_ratio": 0.85
        }

        with connections['default'].cursor() as cursor:
            cursor.execute(q, params)
            return cursor.fetchall()

    def __create_new_building(self, c: Candidate):

        bdg = Building()
        bdg.shape = c.shape
        bdg.rnb_id = generate_id()
        bdg.point = c.shape.point_on_surface
        bdg.source = c.source
        bdg.save()

        c.inspected_at = now()
        c.inspect_result = 'created_bdg'
        c.save()

        self.stats['created'] += 1

    def __update_building(self, c: Candidate):

        c.inspected_at = now()
        c.inspect_result = 'updated_bdg'
        c.save()

        self.stats['updated'] += 1

    def __refuse(self, c: Candidate):

        c.inspected_at = now()
        c.inspect_result = 'refused'
        c.save()

        self.stats['refused'] += 1
