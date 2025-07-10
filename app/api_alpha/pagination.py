from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from typing import Any


class BuildingCursorPagination(CursorPagination):
    page_size = 20
    ordering = "id"


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
