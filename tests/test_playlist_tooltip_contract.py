import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAYLIST_SOURCE_PATH = PROJECT_ROOT / "MusicPlayer2" / "PlayListCtrl.cpp"
PLAYLIST_HEADER_PATH = PROJECT_ROOT / "MusicPlayer2" / "PlayListCtrl.h"


def extract_function(source: str, signature: str) -> str:
    signature_start = source.index(signature)
    body_start = source.index("{", signature_start)
    depth = 0
    for index in range(body_start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[body_start + 1:index]
    raise AssertionError(f"Function body not closed: {signature}")


class PlaylistTooltipContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = PLAYLIST_SOURCE_PATH.read_text(encoding="utf-8-sig")
        cls.header = PLAYLIST_HEADER_PATH.read_text(encoding="utf-8-sig")

    def test_hovered_row_cache_starts_invalid(self):
        self.assertRegex(
            self.header,
            re.compile(r"int m_nItem\{\s*-1\s*\};"),
        )

    def test_playlist_refresh_resets_hover_and_hides_stale_tooltip(self):
        show_playlist_body = extract_function(
            self.source,
            "void CPlayListCtrl::ShowPlaylist(DisplayFormat display_format, "
            "bool search_result)",
        )
        self.assertRegex(
            show_playlist_body,
            re.compile(r"m_nItem = -1;\s*m_toolTip\.Pop\(\);"),
        )

    def test_searched_tooltip_uses_search_result_mapping(self):
        mouse_move_body = extract_function(
            self.source,
            "void CPlayListCtrl::OnMouseMove(UINT nFlags, CPoint point)",
        )
        self.assertIn(
            "song_index = m_search_result[m_nItem];",
            mouse_move_body,
        )
        self.assertNotRegex(
            mouse_move_body,
            re.compile(
                r"GetItemText\(m_nItem,\s*0\)|"
                r"_ttoi\(str\)"
            ),
        )

    def test_registered_tooltip_text_is_updated_and_invalid_rows_are_cleared(self):
        self.assertIn(
            "void UpdateToolTipText(const CString& text);",
            self.header,
        )
        self.assertIn(
            "void CPlayListCtrl::UpdateToolTipText(const CString& text)",
            self.source,
        )
        update_body = extract_function(
            self.source,
            "void CPlayListCtrl::UpdateToolTipText(const CString& text)",
        )
        self.assertRegex(
            update_body,
            re.compile(
                r"GetToolCount\(\) == 0.*"
                r"AddTool\(this,\s*text\).*"
                r"UpdateTipText\(text,\s*this\).*"
                r"Pop\(\);",
                re.DOTALL,
            ),
        )

        mouse_move_body = extract_function(
            self.source,
            "void CPlayListCtrl::OnMouseMove(UINT nFlags, CPoint point)",
        )
        self.assertNotIn("m_toolTip.AddTool", mouse_move_body)
        self.assertRegex(
            mouse_move_body,
            re.compile(
                r"if \(song_index < 0 \|\| song_index >= "
                r"static_cast<int>\(m_all_song_info\.size\(\)\)\)\s*"
                r"\{\s*UpdateToolTipText\(_T\(\"\"\)\);\s*return;\s*\}"
            ),
        )


if __name__ == "__main__":
    unittest.main()
