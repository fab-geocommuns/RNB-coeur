import gzip
import io
from unittest import mock

import revproxy.views  # type: ignore[import-untyped]
from django.test import TestCase
from urllib3.response import HTTPResponse

HASHED_ASSET_URL = "/metabase/app/dist/app-public.d50ccd0327a1f84d.js"


def upstream_response(*, body, headers=None):
    # decode_content=False mirrors revproxy's real upstream read: the body is
    # passed through as is, never decompressed.
    return HTTPResponse(
        body=io.BytesIO(body),
        headers={"Content-Type": "text/javascript", **(headers or {})},
        status=200,
        preload_content=False,
        decode_content=False,
    )


@mock.patch.object(revproxy.views.HTTP_POOLS, "urlopen")
class MetabaseProxyAcceptEncodingTest(TestCase):
    def test_forwards_accept_encoding_and_gzip_body(self, urlopen):
        """
        Input: browser requests a hashed bundle with `Accept-Encoding: gzip, br`,
        Metabase answers a gzip body without Content-Length (streamed path).
        Expected: Metabase receives `Accept-Encoding: gzip, br`; the browser gets
        the gzip bytes unchanged with `Content-Encoding: gzip`.
        """
        gzip_body = gzip.compress(b"console.log('metabase');")
        urlopen.return_value = upstream_response(
            body=gzip_body, headers={"Content-Encoding": "gzip"}
        )

        response = self.client.get(
            HASHED_ASSET_URL, headers={"Accept-Encoding": "gzip, br"}
        )

        self.assertEqual(
            urlopen.call_args.kwargs["headers"]["Accept-Encoding"], "gzip, br"
        )
        self.assertEqual(response["Content-Encoding"], "gzip")
        self.assertEqual(b"".join(response.streaming_content), gzip_body)

    def test_no_accept_encoding_forwarded_when_absent(self, urlopen):
        """
        Input: browser requests a hashed bundle without Accept-Encoding.
        Expected: no Accept-Encoding header is sent to Metabase.
        """
        urlopen.return_value = upstream_response(body=b"js")

        self.client.get(HASHED_ASSET_URL)

        self.assertNotIn("Accept-Encoding", urlopen.call_args.kwargs["headers"])
