from django.contrib.gis.db import models

class Building(models.Model):
    rnb_id = models.CharField(max_length=6, null=False)
    source = models.CharField(max_length=10, null=False)
    point = models.PointField(null=True)

class ExtRef(models.Model):
    building = models.ForeignKey(Building)
    source = models.CharField(max_length=10, null=False, db_index=True)
    ext_id = models.CharField(max_length=50, null=False, db_index=True)

class Lineage(models.Model):
    parent = models.ForeignKey(Building)
    child = models.ForeignKey(Building)