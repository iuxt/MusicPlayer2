import re
import unittest
from pathlib import Path


SOURCE_PATH = (
    Path(__file__).resolve().parents[1] / "MusicPlayer2" / "ListCtrlEx.cpp"
)


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
        cls.source = SOURCE_PATH.read_text(encoding="utf-8-sig")

    def test_virtual_list_data_update_invalidates_without_background_erase(self):
        set_data_body = extract_function(
            self.source,
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
            self.source,
            "BOOL CListCtrlEx::OnEraseBkgnd(CDC* pDC)",
        )
        erase_body_without_comments = re.sub(r"//.*", "", erase_body)
        self.assertIn("return TRUE;", erase_body_without_comments)
        self.assertNotIn(
            "return CListCtrl::OnEraseBkgnd(pDC);",
            erase_body_without_comments,
        )


if __name__ == "__main__":
    unittest.main()
