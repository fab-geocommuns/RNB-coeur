import json
from django.contrib.postgres.fields import ArrayField
from django.contrib.gis.db import models

class Building(models.Model):

    rnb_id = models.CharField(max_length=6, null=False, unique=True, db_index=True)
    source = models.CharField(max_length=10, null=False)
    point = models.PointField(null=True)
    children = models.ManyToManyField('self', blank=True, symmetrical=False, related_name='parents')
    ext_bdnb_id = models.CharField(max_length=16, null=True, unique=True, db_index=True)
    ext_ban_ids = ArrayField(models.CharField(max_length=16), null=True, blank=True)

    def point_geojson(self):
        # todo : is there a better way to go from a PointField to geojson dict ?
        # We are doing points > dict > json str > dict. It is inefficient.
        return json.loads(self.point.geojson)