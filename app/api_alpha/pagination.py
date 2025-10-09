from base64 import b64encode
from datetime import datetime
from datetime import timezone

from rest_framework.exceptions import ValidationError
from rest_framework.pagination import BasePagination
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


class OGCApiPagination(BuildingCursorPagination):
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
