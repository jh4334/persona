import os
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from classroom_sim.web import auth, mcp, server


class McpOAuthTest(unittest.TestCase):
    def setUp(self):
        self.old_auth = server.AUTH
        self.old_verifier = server.VERIFIER
        self.old_public_url = os.environ.get("CLASSROOM_SIM_PUBLIC_URL")
        server.AUTH = auth.AuthConfig(
            url="https://project.supabase.co",
            anon_key="anon",
            jwt_secret="",
            required=True,
        )
        server.VERIFIER = auth.Verifier(server.AUTH)
        os.environ["CLASSROOM_SIM_PUBLIC_URL"] = "https://classroom.example"
        self.client = TestClient(server.app)

    def tearDown(self):
        server.AUTH = self.old_auth
        server.VERIFIER = self.old_verifier
        if self.old_public_url is None:
            os.environ.pop("CLASSROOM_SIM_PUBLIC_URL", None)
        else:
            os.environ["CLASSROOM_SIM_PUBLIC_URL"] = self.old_public_url

    def test_protected_resource_metadata(self):
        response = self.client.get("/.well-known/oauth-protected-resource/mcp")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "resource": "https://classroom.example/mcp",
            "authorization_servers": ["https://project.supabase.co/auth/v1"],
            "bearer_methods_supported": ["header"],
            "scopes_supported": ["openid", "email"],
        })

    def test_mcp_challenge_points_to_metadata(self):
        response = self.client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {},
        })
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.headers["www-authenticate"],
            'Bearer resource_metadata="https://classroom.example/.well-known/oauth-protected-resource/mcp"',
        )

    def test_consent_page_is_served(self):
        response = self.client.get("/oauth/consent?authorization_id=request-1")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="screen-oauth"', response.text)
        self.assertIn('id="btn-oauth-approve"', response.text)
        self.assertIn('id="btn-oauth-deny"', response.text)

    def test_tools_publish_chatgpt_metadata(self):
        for tool in mcp.TOOLS:
            with self.subTest(tool=tool["name"]):
                self.assertTrue(tool["title"])
                self.assertEqual(tool["outputSchema"]["type"], "object")
                self.assertIn("readOnlyHint", tool["annotations"])
                self.assertIn("destructiveHint", tool["annotations"])
                self.assertIn("openWorldHint", tool["annotations"])
                schemes = [{"type": "oauth2", "scopes": ["openid", "email"]}]
                self.assertEqual(tool["securitySchemes"], schemes)
                self.assertEqual(tool["_meta"]["securitySchemes"], schemes)


if __name__ == "__main__":
    unittest.main()
