import unittest
from unittest.mock import patch

from app.security import UnsafeUrlError, validate_public_url


class UrlSecurityTests(unittest.TestCase):
    def test_rejects_non_http_protocols(self):
        with self.assertRaises(UnsafeUrlError):
            validate_public_url("file:///etc/passwd")

    @patch("app.security.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))])
    def test_rejects_private_addresses(self, _resolver):
        with self.assertRaises(UnsafeUrlError):
            validate_public_url("https://localhost/video")

    @patch("app.security.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))])
    def test_accepts_public_https(self, _resolver):
        self.assertEqual(validate_public_url("https://example.com/video"), "https://example.com/video")


if __name__ == "__main__":
    unittest.main()
