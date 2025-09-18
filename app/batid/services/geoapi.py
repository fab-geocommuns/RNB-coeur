from pygeoapi.provider.base import BaseProvider
from batid.models import Building


class DjangoBuildingProvider(BaseProvider):
    def __init__(self, provider_def):
        super().__init__(provider_def)

    def query(self, **kwargs):
        qs = Building.objects.all()
        # apply filters from kwargs (bbox, limit, offset, etc.)
        return {"type": "FeatureCollection", "features": [b.to_geojson() for b in qs]}

    def get(self, identifier):
        b = Building.objects.get(pk=identifier)
        return b.to_geojson()
