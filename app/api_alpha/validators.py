from batid.models import Building
from rest_framework import serializers


def ads_validate_rnbid(rnb_id):
    if rnb_id == "new":
        return
    if not Building.objects.filter(rnb_id=rnb_id).exists():
        raise serializers.ValidationError(f'Building "{rnb_id}" does not exist.')

    raise serializers.ValidationError('rnb_id must be "new" or an existing RNB ID.')
