"""Basic tests for AIBEF."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_config():
    from core.config import CONFIG
    assert CONFIG.required_txt_count == 6
    assert CONFIG.input_dir.exists()


def test_wos_parser():
    from utils.text_utils import WoSParser
    txt_files = list(CONFIG.input_dir.glob("*.txt"))
    if txt_files:
        parser = WoSParser(txt_files[0])
        df = parser.parse()
        assert not df.empty
        assert "__record_id__" in df.columns
        assert "__source_file__" in df.columns


def test_text_utils():
    from utils.text_utils import normalize_text
    assert normalize_text("  hello  world  ") == "hello world"
    assert normalize_text("") == ""


if __name__ == "__main__":
    test_config()
    test_text_utils()
    print("All basic tests passed!")
