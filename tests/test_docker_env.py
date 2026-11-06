from contextlib import redirect_stdout
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from dotenv import dotenv_values
from scripts.init_docker_env import initialize


class DockerEnvironmentTests(unittest.TestCase):
    def test_isolates_credentials_preserves_literals_and_is_idempotent(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            local = "GROQ_API_KEY='provider$literal'\nPINECONE_API_KEY=fixture-pinecone\nTAVILY_API_KEY=fixture-tavily\nADMIN_API_KEY=must-not-copy\n"
            (root / ".env").write_text(local, encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                initialize(root)
                original = (root / ".env.docker").read_bytes()
                initialize(root)
            self.assertEqual((root / ".env.docker").read_bytes(), original)
            self.assertEqual((root / ".env").read_text(encoding="utf-8"), local)
            values = dotenv_values(root / ".env.docker", interpolate=False)
            self.assertEqual(values["GROQ_API_KEY"], "provider$literal")
            credentials = [value for key, value in values.items() if key.startswith("DOCKER_")]
            self.assertEqual(len(credentials), 4)
            self.assertEqual(len(set(credentials)), 4)
            self.assertTrue(all(len(value) == 64 for value in credentials))
            self.assertNotIn("ADMIN_API_KEY", values)
            for secret in credentials + ["provider$literal", "must-not-copy"]:
                self.assertNotIn(secret, output.getvalue())

    def test_missing_provider_configuration_is_reported_without_secrets(self):
        with TemporaryDirectory() as directory:
            output = io.StringIO()
            with redirect_stdout(output):
                initialize(Path(directory))
            for key in ("GROQ_API_KEY", "PINECONE_API_KEY", "TAVILY_API_KEY"):
                self.assertIn(key, output.getvalue())
