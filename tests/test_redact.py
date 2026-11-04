import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills/bogusz/scripts"))

from redact import redact, redact_text  # noqa: E402


class RedactTextTest(unittest.TestCase):
    def test_jwt(self):
        out = redact_text("tok eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijk")
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", out)

    def test_bearer_in_escaped_json(self):
        out = redact_text('{\\"Authorization\\": \\"Bearer abcdefgh12345678\\"}')
        self.assertNotIn("abcdefgh12345678", out)
        self.assertIn("[REDACTED:", out)

    def test_github_and_aws(self):
        for s in ["ghp_" + "a" * 36, "github_pat_" + "b" * 40, "AKIA" + "C" * 16]:
            self.assertNotIn(s, redact_text(f"x {s} y"))

    def test_env_assignments(self):
        out = redact_text("CLIENT_SECRET=s3cr3t TEST_USER_PASSWORD='p w' BUF_API_TOKEN: tkn go test ./...")
        for s in ["s3cr3t", "p w", "tkn"]:
            self.assertNotIn(s, out)
        self.assertIn("go test ./...", out)

    def test_cookie_header(self):
        self.assertNotIn("sid=abc", redact_text("Cookie: sid=abc; x=y"))

    def test_private_key_block(self):
        out = redact_text("-----BEGIN RSA PRIVATE KEY-----\nMIIEabc\n-----END RSA PRIVATE KEY-----")
        self.assertNotIn("MIIE", out)

    def test_kubeconfig_and_url_creds(self):
        out = redact_text("client-key-data: LS0tQUJD\nhttps://user:pa55@minio.local/bucket")
        self.assertNotIn("LS0tQUJD", out)
        self.assertNotIn("pa55", out)
        self.assertIn("minio.local/bucket", out)

    def test_mc_alias_positional_creds(self):
        out = redact_text("sh -c 'mc alias set local http://127.0.0.1:9000 minioadmin s3cretPw && mc ls local'")
        self.assertNotIn("s3cretPw", out)
        self.assertNotIn("minioadmin", out)
        self.assertIn("mc ls local", out)

    def test_aws_arn(self):
        out = redact_text('"Arn": "arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_Dev/jane@example.com"')
        self.assertNotIn("123456789012", out)
        self.assertNotIn("jane@example.com", out)

    def test_review_leak_table(self):
        cases = [
            ('{"password": "hunter2"}', "hunter2"),
            ('{\\"client_secret\\":\\"abc123\\"}', "abc123"),
            ('"refresh_token": "rt-9f8e7d"', "rt-9f8e7d"),
            ("curl -u admin:pw123 https://x", "pw123"),
            ("Authorization: Basic YWRtaW46cHc=", "YWRtaW46cHc="),
            ("Authorization: Token tok-777", "tok-777"),
            ("X-API-Key: key-555", "key-555"),
            ("cli --password pw456 --other", "pw456"),
            ("cli --client-secret cs789", "cs789"),
            ("docker login -u bob -p dpw321 registry", "dpw321"),
            ("mysql -uroot -pmpw654 db", "mpw654"),
            ("machine buf.build login bob password npw111", "npw111"),
            ("DB_PASS=dbp222", "dbp222"),
            ("DefaultEndpointsProtocol=https;AccountName=a;AccountKey=akey333==;", "akey333"),
            ("redis://:rpw444@cache:6379", "rpw444"),
            ("postgres://u:p@ss@db:5432/x", "p@ss"),
        ]
        for text, secret in cases:
            with self.subTest(text=text):
                self.assertNotIn(secret, redact_text(text))

    def test_quoted_value_with_backslashes(self):
        for text in ['{"password": "ab\\\\cdSECRETX"}', '{\\"token\\":\\"ab\\\\\\"cdSECRETX\\"}']:
            with self.subTest(text=text):
                self.assertNotIn("SECRETX", redact_text(text))

    def test_prefixed_keys_and_unterminated_quote(self):
        cases = [
            ("X-Foo-Authorization: Basic YWJjZGVmZ2g=", "YWJjZGVmZ2g="),
            ("X-Authtoken: Basic c2VjcmV0dG9r", "c2VjcmV0dG9r"),
            ("Apikey: plainkey999", "plainkey999"),
            ('curl --header "X-Vault-Key: vaultv1" https://v', "vaultv1"),
            ("sent X-Auth-Token: Basic midline77", "midline77"),
            ('sent X-Auth-Token: "quotedtok1"', "quotedtok1"),
            ("x-api-key: 'quotedkey2'", "quotedkey2"),
            ("A" * 80 + "_TOKEN=longprefixtok", "longprefixtok"),
            ("password='unterminated secretvalue", "secretvalue"),
        ]
        for text, secret in cases:
            with self.subTest(text=text[:40]):
                self.assertNotIn(secret, redact_text(text))

    def test_probe_leaks(self):
        cases = [
            ("-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\nAAAAtruncated", "b3BlbnNzaC1rZXktdjEAAAAA"),
            ('{"auths": {"ghcr.io": {"auth": "dXNlcjpkb2NrZXJwdw=="}}}', "dXNlcjpkb2NrZXJwdw=="),
            ("key sk_live_51HxAbCdEfGhIjKlMnOp end", "sk_live_51HxAbCdEfGhIjKlMnOp"),
            ("//registry.npmjs.org/:_authToken=npm_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "npm_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"),
            ("access ya29.a0AfH6SMBxYzAbCdEfGhIjKlMn end", "ya29.a0AfH6SMBxYzAbCdEfGhIjKlMn"),
            ("curl https://hooks.slack.com/services/T0001/B0002/XyZsecretHook1", "XyZsecretHook1"),
            ("https://acct.blob.core.windows.net/c/f?sv=2022-11-02&sig=AbC%2Bsas123%3D&se=x", "AbC%2Bsas123%3D"),
            ("sshpass -p sshpw77 ssh host", "sshpw77"),
            ("redis-cli -h cache -a redispw88 ping", "redispw88"),
        ]
        for text, secret in cases:
            with self.subTest(text=text[:30]):
                self.assertNotIn(secret, redact_text(text))

    def test_pytest_node_ids_not_mangled(self):
        for s in ["pytest tests/test_token.py::test_refresh", "FAILED tests/unit/test_password.py::TestReset::test_x"]:
            with self.subTest(s=s):
                self.assertEqual(redact_text(s), s)

    def test_long_line_is_fast(self):
        import time
        for s in ["a" * 50000, "a-" * 25000 + "token", ".".join(["x"] * 25000), "sshpass " + "x " * 25000,
                  "redis-cli " + "x " * 25000, "-----BEGIN RSA PRIVATE KEY-----" + "a" * 50000]:
            start = time.monotonic()
            redact_text(s)
            self.assertLess(time.monotonic() - start, 1.0)

    def test_test_output_not_mangled(self):
        s = "--- PASS: TestA (0.01s)\nok: 12 passed, 0 failed, 0 build-failed, 0 skipped (1 packages)"
        self.assertEqual(redact_text(s), s)

    def test_vendor_tokens(self):
        for tok in ["sk-proj-AbCdEf0123456789AbCdEf0123456789", "sk-ant-api03-AbCdEf0123456789AbCdEf01",
                    "xoxb-1234567890-abcdefghij", "AIzaSyA1234567890abcdefghijklmnopqrstuv",
                    "glpat-abcdefghij0123456789", "hf_abcdefghijklmnopqrstuvwxyz0123456"]:
            with self.subTest(tok=tok[:8]):
                self.assertNotIn(tok, redact_text(f"value {tok} end"))

    def test_file_line_not_mangled(self):
        s = "    token_test.go:42: expected 3, got 2"
        self.assertEqual(redact_text(s), s)
        self.assertNotIn("dbpw9", redact_text("spring.datasource.password: dbpw9"))

    def test_dash_u_only_for_credentials(self):
        for s in ["git push -u origin ah/feature", "sort -u file.txt", "docker run -u 1000 img"]:
            self.assertEqual(redact_text(s), s)
        self.assertNotIn("pw123", redact_text("curl -u admin:pw123 https://x"))
        self.assertNotIn("pw124", redact_text("curl --user admin:pw124 https://x"))

    def test_multiline_curl_user_and_dotted_keys(self):
        self.assertNotIn("pwML1", redact_text("curl \\\n  -u admin:pwML1 \\\n  https://x"))
        self.assertNotIn("dotv2", redact_text("secret.value=dotv2"))
        self.assertNotIn("dotv3", redact_text("app.client.token.raw: dotv3"))
        self.assertEqual(redact_text("    token_test.go:42: x"), "    token_test.go:42: x")

    def test_secret_shaped_keys_and_curl_user(self):
        cases = [("masterKey: mk111", "mk111"), ("  encryption_key: ek222", "ek222"), ("signingkey=sk333", "sk333"),
                 ("curl -u tokenonly444 https://x", "tokenonly444"),
                 ("curl \\\n  -u tokenonly555 \\\n  https://x", "tokenonly555"),
                 ("wget --user=:pwcolon666 https://x", "pwcolon666")]
        for text, secret in cases:
            with self.subTest(text=text[:30]):
                self.assertNotIn(secret, redact_text(text))

    def test_yaml_key_lines_not_redacted(self):
        for line in ["  key: my-config-name", "monkey: 3", "  sort_key: name"]:
            with self.subTest(line=line):
                self.assertEqual(redact_text(line), line)
        self.assertNotIn("k9k9", redact_text("  x-api-key: k9k9"))
        self.assertNotIn("kubetok", redact_text("    token: kubetok"))

    def test_home_dir_shortened(self):
        self.assertEqual(redact_text(str(Path.home()) + "/src/x"), "~/src/x")

    def test_plain_text_unchanged(self):
        s = "make test PKG=./internal/batch/... RUN=TestBatch"
        self.assertEqual(redact_text(s), s)


class RedactValueTest(unittest.TestCase):
    def test_secret_dict_keys(self):
        out = redact({"env": {"CLIENT_SECRET": "x", "PKG": "./internal/..."}, "headers": [{"Authorization": "abc"}]})
        self.assertEqual(out["env"]["CLIENT_SECRET"], "[REDACTED:key]")
        self.assertEqual(out["env"]["PKG"], "./internal/...")
        self.assertEqual(out["headers"][0]["Authorization"], "[REDACTED:key]")

    def test_more_secret_dict_keys(self):
        out = redact({"access_key": "a1", "AccountKey": "a2", "client_key": "a3", "auth": "a4", "author": "Ann"})
        self.assertEqual([out[k] for k in ("access_key", "AccountKey", "client_key", "auth")], ["[REDACTED:key]"] * 4)
        self.assertEqual(out["author"], "Ann")


if __name__ == "__main__":
    unittest.main()
