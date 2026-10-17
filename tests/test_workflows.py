"""ワークフローの YAML に同じキーが2つ無いか（2026-10-17、checkout の with: が2つになり GitHub が作成のワークフローを読めず、20:00 の作成が動かなかった）"""
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # PyYAML が無い環境では飛ばす
    yaml = None


def _loader():
    class L(yaml.SafeLoader):
        pass

    def mapping(loader, node, deep=False):
        seen = set()
        for k, _ in node.value:
            key = loader.construct_object(k, deep=deep)
            if key in seen:
                raise ValueError(f"同じキー {key!r} が2つあります（{k.start_mark.line + 1} 行目）")
            seen.add(key)
        return yaml.SafeLoader.construct_mapping(loader, node, deep)

    L.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    return L


@unittest.skipIf(yaml is None, "PyYAML が無い")
class ワークフローのテスト(unittest.TestCase):
    def test_同じキーが2つ無い(self):
        loader = _loader()
        for f in sorted((Path(__file__).resolve().parents[1] / ".github" / "workflows").glob("*.yml")):
            with self.subTest(f.name):
                yaml.load(f.read_text(encoding="utf-8"), Loader=loader)


if __name__ == "__main__":
    unittest.main()
