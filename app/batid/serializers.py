from rest_framework import routers, serializers
from batid.models import Building

class BuildingSerializer(serializers.HyperlinkedModelSerializer):

    point = serializers.CharField(source='point_geojson')


    class Meta:
        model = Building
        fields = ['rnb_id', 'source', 'point']