from django.contrib.gis.db import models

class Building(models.Model):
    rnb_id = models.CharField(max_length=6, null=False, unique=True, db_index=True)
    source = models.CharField(max_length=10, null=False)
    point = models.PointField(null=True)
    parents = models.ManyToManyField('self', blank=True, symmetrical=False, related_name='children')

class ExtRef(models.Model):
    building = models.ForeignKey(Building, on_delete=models.CASCADE)
    source = models.CharField(max_length=10, null=False, db_index=True)
    ext_id = models.CharField(max_length=50, null=False, db_index=True)