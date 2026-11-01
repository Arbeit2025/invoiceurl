import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as app_module  # noqa: E402


class InvoiceUrlTest(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_healthz(self):
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "ok")

    def test_index_ok(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("請求書URL共有メーカー", body)
        self.assertIn("サーバーに保存されません", body)
        # リンク生成用の JS が入っている
        self.assertIn("encodePayload", body)
        self.assertIn("/view#", body)

    def test_payload_roundtrip(self):
        data = {
            "issuer": "山田商店",
            "issuer_addr": "〒100-0001 東京都千代田区1-1",
            "client": "株式会社テスト",
            "inv_date": "2026-11-01",
            "due_date": "2026-11-30",
            "tax_rate": 10,
            "items": [
                {"name": "デザイン料", "qty": 1, "price": 50000},
                {"name": "サーバー代", "qty": 3, "price": 1200},
            ],
        }
        encoded = app_module.encode_payload(data)
        # URL フラグメントに使える文字だけ（+ / = を含まない）
        self.assertNotIn("+", encoded)
        self.assertNotIn("/", encoded)
        self.assertNotIn("=", encoded)
        decoded = app_module.decode_payload(encoded)
        self.assertEqual(decoded, data)

    def test_payload_roundtrip_ascii(self):
        data = {"issuer": "ABC", "items": []}
        self.assertEqual(app_module.decode_payload(app_module.encode_payload(data)), data)

    def test_view_page_has_decode_script(self):
        res = self.client.get("/view")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("decodePayload", body)
        self.assertIn("location.hash", body)
        self.assertIn("印刷する", body)
        self.assertIn("請求書", body)

    def test_no_database_file_created(self):
        # DB を持たない設計：プロジェクト内に .db ファイルが作られない
        proj = os.path.join(os.path.dirname(__file__), "..")
        dbs = [f for f in os.listdir(proj) if f.endswith(".db")]
        self.assertEqual(dbs, [])


if __name__ == "__main__":
    unittest.main()
