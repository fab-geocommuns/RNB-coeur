from api_alpha.pagination import BuildingCursorPagination
from batid.models import Building
from django.test import TestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory


class BuildingCursorPaginationTest(TestCase):
    def _paginate(self, cursor: str):
        request = Request(APIRequestFactory().get("/", {"cursor": cursor}))
        paginator = BuildingCursorPagination()
        paginator.paginate_queryset(Building.objects.all(), request)
        return paginator

    def test_cursor_below_1_falls_back_to_first_page(self):
        """
        Input: a cursor of 0, then -1, on a real Building queryset.
        Expected: no error (it used to raise "Negative indexing is not supported",
        a 500 on every endpoint using this paginator); the first page is served,
        without a previous link.
        """
        for cursor in ("0", "-1"):
            with self.subTest(cursor=cursor):
                paginator = self._paginate(cursor)
                self.assertEqual(paginator.current_page, 1)
                self.assertIsNone(paginator.get_previous_link())

    def test_valid_cursor_is_kept(self):
        """
        Input: a cursor of 2.
        Expected: the second page is served, with a link to the first one.
        """
        paginator = self._paginate("2")
        self.assertEqual(paginator.current_page, 2)
        self.assertIn("cursor=1", paginator.get_previous_link())
