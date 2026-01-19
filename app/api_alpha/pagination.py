from datetime import datetime
from datetime import timezone

from django.db.models import BooleanField
from django.db.models.expressions import RawSQL
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import BasePagination
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param


class BuildingCursorPagination(BasePagination):

    cursor_query_param = "cursor"

    def __init__(self):
        self.base_url = None
        self.current_page = None

        self.has_next = False
        self.has_previous = False

        self.page = None

        self.page_size = 20

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "next": {
                    "type": "string",
                    "nullable": True,
                },
                "previous": {
                    "type": "string",
                    "nullable": True,
                },
                "results": schema,
            },
        }

    def get_html_context(self):
        return {
            "previous_url": self.get_previous_link(),
            "next_url": self.get_next_link(),
        }

    def get_paginated_response(self, data):

        return Response(
            {
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )

    def get_next_link(self):

        if self.has_next:
            next_cursor = str(self.current_page + 1)
            return replace_query_param(
                self.base_url, self.cursor_query_param, next_cursor
            )

        return None

    def get_previous_link(self):

        if self.has_previous:
            previous_cursor = str(self.current_page - 1)
            return replace_query_param(
                self.base_url, self.cursor_query_param, previous_cursor
            )

        return None

    def paginate_queryset(self, queryset, request, view=None):

        # Add a limit query param
        limit_param = request.query_params.get("limit", None)
        if limit_param:
            try:
                # This str to int conversion can raise ValueError
                limit = int(limit_param)

                if limit < 1 or limit > 100:
                    raise ValueError()

                self.page_size = limit

            except ValueError:
                raise ValidationError(
                    "The limit parameter must be an integer between 1 and 100"
                )

        # Get the current URL with all parameters
        self.base_url = request.build_absolute_uri()

        self.current_page = self.get_page(request)
        if self.current_page is None:
            self.current_page = 1

        offset = (self.current_page - 1) * self.page_size

        # If we have an offset cursor then offset the entire page by that amount.
        # We also always fetch an extra item in order to determine if there is a
        # page following on from this one.
        results = queryset[offset : offset + self.page_size + 1]

        if len(results) > self.page_size:
            self.has_next = True

        if self.current_page > 1:
            self.has_previous = True

        return results[: self.page_size]

    def get_page(self, request):

        request_page = request.query_params.get(self.cursor_query_param)
        if request_page:
            try:
                return int(request_page)
            except ValueError:
                return None

        return None

    def encode_cursor(self, cursor):
        return b64encode(cursor.encode("ascii")).decode("ascii")


class BuildingListingCursorPagination(CursorPagination):
    ordering = "id"

    def get_page_size(self, request):
        limit_param = request.query_params.get("limit", 20)
        try:
            # This str to int conversion can raise ValueError
            limit = int(limit_param)

            if limit < 1 or limit > 100:
                raise ValueError(
                    "The limit parameter must be an integer between 1 and 100"
                )

            return limit

        except ValueError:
            raise ValueError("The limit parameter must be an integer between 1 and 100")

    def paginate_queryset(self, queryset, request, view=None):
        self.request = request
        self.page_size = self.get_page_size(request)
        if not self.page_size:
            return None

        self.base_url = request.build_absolute_uri()
        self.ordering = self.get_ordering(request, queryset, view)
        if self.ordering[0] != "id" or len(self.ordering) > 1:
            raise NotImplementedError(
                "Only id ordering is supported for BuildingCursorPagination"
            )

        self.cursor = self.decode_cursor(request)
        if self.cursor is None:
            offset, reverse, current_position = (0, False, None)
        else:
            offset, reverse, current_position = self.cursor

        current_id = int(current_position) if current_position else 0

        queryset = queryset.order_by(
            RawSQL('point("batid_building"."id", 0.) <-> point(%s, 0.)', [current_id])
        )

        if current_position is not None:
            order = "id"
            is_reversed = order.startswith("-")

            # we create a query that leverages the strange gist index on (point, poin(id, 0))
            # for better performance
            # >> means right of, so "point(id, 0) >> point(XXX, 0.) means id > XXX
            if self.cursor.reverse != is_reversed:
                queryset = queryset.filter(
                    RawSQL(
                        "point(id, 0) << point(%s, 0.)",
                        (current_position,),
                        output_field=BooleanField(),
                    )
                )
            else:
                queryset = queryset.filter(
                    RawSQL(
                        "point(id, 0) >> point(%s, 0.)",
                        (current_position,),
                        output_field=BooleanField(),
                    )
                )

        # If we have an offset cursor then offset the entire page by that amount.
        # We also always fetch an extra item in order to determine if there is a
        # page following on from this one.
        results = list(queryset[offset : offset + self.page_size + 1])
        self.page = list(results[: self.page_size])

        # Determine the position of the final item following the page.
        if len(results) > len(self.page):
            has_following_position = True
            following_position = self._get_position_from_instance(
                results[-1], self.ordering
            )
        else:
            has_following_position = False
            following_position = None

        if reverse:
            # If we have a reverse queryset, then the query ordering was in reverse
            # so we need to reverse the items again before returning them to the user.
            self.page = list(reversed(self.page))

            # Determine next and previous positions for reverse cursors.
            self.has_next = (current_position is not None) or (offset > 0)
            self.has_previous = has_following_position
            if self.has_next:
                self.next_position = current_position
            if self.has_previous:
                self.previous_position = following_position
        else:
            # Determine next and previous positions for forward cursors.
            self.has_next = has_following_position
            self.has_previous = (current_position is not None) or (offset > 0)
            if self.has_next:
                self.next_position = following_position
            if self.has_previous:
                self.previous_position = current_position

        # Display page controls in the browsable API if there is more
        # than one page.
        if (self.has_previous or self.has_next) and self.template is not None:
            self.display_page_controls = True

        return self.page


class OGCApiPagination(BuildingListingCursorPagination):
    def get_paginated_response(self, data):
        links = []

        # self link
        links.append(
            {
                "rel": "self",
                "title": "Current page of results",
                "type": "application/geo+json",
                "href": self.base_url,
            }
        )

        # next link
        next_link = self.get_next_link()
        if next_link:
            links.append(
                {
                    "rel": "next",
                    "title": "Next page of results",
                    "type": "application/geo+json",
                    "href": next_link,
                }
            )

        # previous link
        prev_link = self.get_previous_link()
        if prev_link:
            links.append(
                {
                    "rel": "prev",
                    "title": "Previous page of results",
                    "type": "application/geo+json",
                    "href": prev_link,
                }
            )

        data["links"] = links
        data["numberReturned"] = len(data["features"])
        data["timeStamp"] = (
            datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

        return Response(data)


class BuildingAddressCursorPagination(BuildingCursorPagination):
    def get_paginated_response(self, data, infos):
        return Response(
            {
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "status": infos["status"],
                "cle_interop_ban": infos["cle_interop_ban"],
                "score_ban": infos["score_ban"],
                "results": data,
            }
        )
