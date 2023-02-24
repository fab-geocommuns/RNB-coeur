from pprint import pprint

from batid.utils.misc import is_float
from batid.models import Building
from django.contrib.gis.geos import Polygon

class BuildingSearch:

    def __init__(self, **kwargs):

        self.params = self.BuildingSearchParams(**kwargs)
        self.qs = None

    def get_queryset(self):

        # Init
        queryset = Building.objects.all()

        # Add filters
        if self.params.bb:
            queryset = queryset.filter(point__intersects=self.params.bb)

        return queryset


    def is_valid(self):
        return self.params.is_valid()

    @property
    def errors(self):
        return self.params.errors


    class BuildingSearchParams:

        SORT_DEFAULT = 'rnb_id'
        SORT_CHOICES = ['rnb_id', 'distance']

        PARAM_SPLITTER = '-'

        def __init__(self, **kwargs):

            # ##########
            # Init properties
            # ##########

            # Filters
            self.bb = None
            self.circle = None
            self.ban_id = None
            self.sort = None

            # Internals
            self.__errors = []


            # ##########
            # Set up filters
            # ##########

            self.set_bb_str(kwargs.get('bb', None))
            # todo : self.set_circle_str(kwargs.get('circle', None))
            # todo : self.set_ban_id_str(kwargs.get('ban_id', None))
            self.set_sort_str(kwargs.get('sort', self.SORT_DEFAULT))

        @property
        def errors(self):
            return self.__errors

        def is_valid(self) -> bool:
            return len(self.__errors) == 0

        def set_sort_str(self, sort_str: str) -> None:

            if self.__validate_sort_str(sort_str):
                self.sort = sort_str

        def __validate_sort_str(self, sort_str: str) -> bool:

                if sort_str not in self.SORT_CHOICES:
                    self.__errors.append(f"sort : sort parameter must be one of {self.SORT_CHOICES}")
                    return False

                return True

        def set_bb_str(self, bb_str: str) -> None:

            print('---------')
            print(bb_str)
            print('---------')

            if self.__validate_bb_str(bb_str):
                self.bb = self.__convert_bb_str(bb_str)

        # The bb property is a Polygon object
        def __convert_bb_str(self, bb_str: str) -> Polygon:

            nw_lat, nw_lng, se_lat, se_lng = [float(coord) for coord in bb_str.split(self.PARAM_SPLITTER)]

            poly_coords = ((nw_lng, nw_lat), (nw_lng, se_lat), (se_lng, se_lat), (se_lng, nw_lat), (nw_lng, nw_lat))

            return Polygon(poly_coords, srid=4326)


        def __validate_bb_str(self, bb_str: str) -> bool:



            format_msg = "bb : bounding box parameter must be a string of 4 floats separated by a dash"

            if not bb_str:
                return

            coords = bb_str.split(self.PARAM_SPLITTER)

            if len(coords) != 4:
                self.__errors.append(format_msg)
                return False

            for coord in coords:
                if not is_float(coord):
                    self.__errors.append(format_msg)
                    return False

            # Convert all params to floats and dispatch them to the right property
            nw_lat, nw_lng, se_lat, se_lng = [float(coord) for coord in coords]

            # Check that the bounding box is valid
            if nw_lat <= se_lat:
                self.__errors.append("bb : north-west latitude must be greater than south-east latitude")
                return False

            if nw_lng >= se_lng:
                self.__errors.append("bb : south-east longitude must be greater than north-west longitude")
                return False

            return True









