from datetime import datetime

from django.db.models.expressions import RawSQL
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response


class BuildingCursorPagination(CursorPagination):
    ordering = "id"

    def get_page_size(self, request):
        limit_param = request.query_params.get("limit", 20)
        try:
            # This str to int conversion can raise ValueError
            limit = int(limit_param)

            if limit < 1 or limit > 100:
                raise ValueError()

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
            (offset, reverse, current_position) = (0, False, None)
        else:
            (offset, reverse, current_position) = self.cursor

        current_id = int(current_position) if current_position else 0

        queryset = queryset.order_by(
            RawSQL('"batid_building"."id" <-> %s', [current_id])
        )

        # If we have a cursor with a fixed position then filter by that.
        if current_position is not None:
            order = self.ordering[0]
            is_reversed = order.startswith("-")
            order_attr = order.lstrip("-")

            # Test for: (cursor reversed) XOR (queryset reversed)
            if self.cursor.reverse != is_reversed:
                kwargs = {order_attr + "__lt": current_position}
            else:
                kwargs = {order_attr + "__gt": current_position}

            queryset = queryset.filter(**kwargs)

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


class OGCApiPagination(BuildingCursorPagination):
    def get_paginated_response(self, data):
        links = []

        # self link
        links.append(
            {
                "rel": "self",
                "title": "Current page of results",
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
                    "href": prev_link,
                }
            )

        data["links"] = links
        data["numberReturned"] = len(data["features"])
        data["timeStamp"] = datetime.now().isoformat()

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
