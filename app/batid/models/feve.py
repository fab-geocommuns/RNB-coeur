from django.contrib.auth.models import User
from django.contrib.gis.db import models

from batid.models.others import Department
from batid.models.report import Report


class Feve(models.Model):
    report = models.ForeignKey(
        Report, on_delete=models.PROTECT, null=False, db_index=True
    )
    found_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, db_index=True
    )
    found_at = models.DateTimeField(auto_now=False, null=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, null=False)
