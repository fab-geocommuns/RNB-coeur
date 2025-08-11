from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from typing import Any
from django.db.models.expressions import RawSQL


class BuildingCursorPagination(CursorPagination):
    page_size = 20
    ordering = "id"

    # We override the `paginate_queryset` method to customize the ordering
    # with a distance operator to force the usage of a `btree_gist` index.
    # Check the original implementation in `rest_framework.pagination.CursorPagination`
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


class BuildingAddressCursorPagination(BuildingCursorPagination):
    def get_paginated_response(
        self, data: list[Any] | None, infos: dict[str, Any]
    ) -> Response:
        return Response(
            {
                "next": self.get_next_link() if data else None,
                "previous": self.get_previous_link() if data else None,
                "status": infos["status"],
                "cle_interop_ban": infos["cle_interop_ban"],
                "score_ban": infos["score_ban"],
                "results": data,
            }
        )
