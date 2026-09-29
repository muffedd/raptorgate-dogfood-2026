"""Keep seed_event's source fixture in local images, but out of the public preview."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def ignored(path, name):
    # Exact path rules we own; no wildcard substitutions for these critical files.
    return name in {line.strip() for line in path.read_text().splitlines()
                    if line.strip() and not line.startswith('#')}


class ImageContextTests(unittest.TestCase):
    def test_fixture_is_available_to_local_and_offline_images(self):
        self.assertTrue((ROOT / 'fixtures.json').is_file())
        self.assertFalse(ignored(ROOT / '.dockerignore', 'fixtures.json'))
        for dockerfile in ['Dockerfile', 'packaging/Dockerfile.offline']:
            self.assertIn('COPY . .', (ROOT / dockerfile).read_text())

    def test_public_preview_has_separate_context_without_fixture(self):
        self.assertTrue(ignored(ROOT / 'preview.Dockerfile.dockerignore', 'fixtures.json'))
        self.assertTrue(ignored(ROOT / 'preview.Dockerfile.dockerignore', '.dogfood.toml'))
        self.assertTrue(ignored(ROOT / '.dockerignore', '.dogfood.toml'))
        self.assertIn('seed_preview --if-empty', (ROOT / 'preview-start.sh').read_text())
        self.assertNotIn('seed_event', (ROOT / 'preview-start.sh').read_text())

    def test_postgres_build_uses_arch_specific_tag_without_mutable_retag(self):
        script = (ROOT / 'packaging/build-offline-bundle.sh').read_text()
        self.assertIn('docker buildx build --platform "linux/$arch" --load -t "raptorgate-postgres:$arch"', script)
        self.assertNotIn('docker tag postgres:16-alpine', script)
        self.assertIn('docker image inspect "raptorgate-postgres:$arch"', script)


if __name__ == '__main__':
    unittest.main()
