from datetime import datetime

from batid.models import ADS
from django.db.models import QuerySet


class ADSSearch:
    def __init__(self, **kwargs):
        self.params = self.ADSSearchParams(**kwargs)
        self.qs = None

    def is_valid(self):
        return self.params.is_valid()

    @property
    def errors(self):
        return self.params.errors

    def get_queryset(self) -> QuerySet:
        # Init
        queryset = ADS.objects.all()

        # Add filters
        if self.params.q:
            queryset = queryset.filter(issue_number__icontains=self.params.q)

        if self.params.since:
            queryset = queryset.filter(issue_date__gte=self.params.since)

        if self.params.sort:
            queryset = queryset.order_by(self.params.sort)

        return queryset

    class ADSSearchParams:
        SINCE_FORMAT = "%Y-%m-%d"

        SORT_DEFAULT = "-issue_date"
        SORT_CHOICES = ["issue_date", "-issue_date"]

        def __init__(self, **kwargs):
            self.q = None
            self.sort = None
            self.since = None

            # Internals
            self.__errors = []

            # ##########
            # Set up filters
            # ##########
            self.set_q_str(kwargs.get("q", None))
            self.set_since_str(kwargs.get("since", None))
            self.set_sort_str(kwargs.get("sort", self.SORT_DEFAULT))

        def is_valid(self) -> bool:
            return len(self.__errors) == 0

        def set_since_str(self, since_str):
            if self.__validate_since_str(since_str):
                self.since = self.__convert_since_str(since_str)

        def __validate_since_str(self, since_str: str) -> bool:
            if since_str is None:
                return False

            try:
                self.__convert_since_str(since_str)
            except ValueError:
                self.__errors.append(
                    "Since date is not valid. It must be in the format YYYY-MM-DD."
                )
                return False

            return True

        def __convert_since_str(self, since_str: str) -> datetime.date:
            return datetime.strptime(since_str, self.SINCE_FORMAT).date()

        def set_q_str(self, q_str):
            self.q = q_str

        def set_sort_str(self, sort_str):
            self.sort = sort_str

        @property
        def errors(self) -> list:
            return self.__errors
