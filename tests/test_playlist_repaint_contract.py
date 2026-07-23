import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIST_CTRL_SOURCE_PATH = PROJECT_ROOT / "MusicPlayer2" / "ListCtrlEx.cpp"
LIST_CTRL_HEADER_PATH = PROJECT_ROOT / "MusicPlayer2" / "ListCtrlEx.h"
PLAYLIST_SOURCE_PATH = PROJECT_ROOT / "MusicPlayer2" / "PlayListCtrl.cpp"


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


class PlaylistRepaintContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.list_ctrl_source = LIST_CTRL_SOURCE_PATH.read_text(
            encoding="utf-8-sig"
        )
        cls.list_ctrl_header = LIST_CTRL_HEADER_PATH.read_text(
            encoding="utf-8-sig"
        )
        cls.playlist_source = PLAYLIST_SOURCE_PATH.read_text(
            encoding="utf-8-sig"
        )

    def test_virtual_list_data_update_invalidates_without_background_erase(self):
        set_data_body = extract_function(
            self.list_ctrl_source,
            "void CListCtrlEx::SetListData(ListData* pListData)",
        )
        self.assertRegex(
            set_data_body,
            re.compile(
                r"SetItemCount\(pListData->size\(\)\);\s*"
                r"Invalidate\(FALSE\);"
            ),
        )

        erase_body = extract_function(
            self.list_ctrl_source,
            "BOOL CListCtrlEx::OnEraseBkgnd(CDC* pDC)",
        )
        erase_body_without_comments = re.sub(r"//.*", "", erase_body)
        self.assertIn("return TRUE;", erase_body_without_comments)
        self.assertNotIn(
            "return CListCtrl::OnEraseBkgnd(pDC);",
            erase_body_without_comments,
        )

    def test_base_list_requests_and_handles_control_postpaint(self):
        custom_draw_body = extract_function(
            self.list_ctrl_source,
            "void CListCtrlEx::OnNMCustomdraw(NMHDR *pNMHDR, LRESULT *pResult)",
        )
        self.assertRegex(
            custom_draw_body,
            re.compile(
                r"case CDDS_PREPAINT:\s*"
                r"\*pResult = CDRF_NOTIFYITEMDRAW\s*\|\s*"
                r"CDRF_NOTIFYPOSTPAINT;"
            ),
        )
        self.assertRegex(
            custom_draw_body,
            re.compile(
                r"case CDDS_POSTPAINT:\s*"
                r"FillEmptyListArea\(CDC::FromHandle\(nmcd\.hdc\)\);\s*"
                r"break;"
            ),
        )

    def test_empty_list_area_starts_after_last_item_and_is_filled(self):
        self.assertIn(
            "void FillEmptyListArea(CDC* pDC);",
            self.list_ctrl_header,
        )
        self.assertIn(
            "void CListCtrlEx::FillEmptyListArea(CDC* pDC)",
            self.list_ctrl_source,
        )
        fill_body = extract_function(
            self.list_ctrl_source,
            "void CListCtrlEx::FillEmptyListArea(CDC* pDC)",
        )
        self.assertRegex(
            fill_body,
            re.compile(
                r"GetClientRect\(empty_rect\);.*"
                r"GetItemRect\(item_count - 1,\s*last_item_rect,\s*"
                r"LVIR_BOUNDS\).*"
                r"empty_rect\.top = std::clamp\(\s*"
                r"last_item_rect\.bottom,\s*empty_rect\.top,\s*"
                r"empty_rect\.bottom\s*\);.*"
                r"FillSolidRect\(empty_rect,\s*m_background_color\);",
                re.DOTALL,
            ),
        )

    def test_playlist_requests_and_handles_control_postpaint(self):
        custom_draw_body = extract_function(
            self.playlist_source,
            "void CPlayListCtrl::OnNMCustomdraw(NMHDR *pNMHDR, LRESULT *pResult)",
        )
        self.assertRegex(
            custom_draw_body,
            re.compile(
                r"case CDDS_PREPAINT:\s*"
                r"\*pResult = CDRF_NOTIFYITEMDRAW\s*\|\s*"
                r"CDRF_NOTIFYPOSTPAINT;"
            ),
        )
        self.assertRegex(
            custom_draw_body,
            re.compile(
                r"case CDDS_POSTPAINT:\s*"
                r"FillEmptyListArea\(CDC::FromHandle\(nmcd\.hdc\)\);\s*"
                r"break;"
            ),
        )


if __name__ == "__main__":
    unittest.main()
