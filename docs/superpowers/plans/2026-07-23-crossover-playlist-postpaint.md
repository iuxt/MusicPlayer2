# CrossOver Playlist Post-Paint Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deterministically clear the ListView client area below the last item during the normal double-buffered paint cycle so CrossOver cannot preserve pixels from removed playlist rows.

**Architecture:** Add one protected `CListCtrlEx` helper that computes and fills only the unused client rectangle. Request control-level `CDDS_POSTPAINT` from both custom-draw handlers and call the shared helper there, while preserving asynchronous `Invalidate(FALSE)`, `LVS_EX_DOUBLEBUFFER`, and the existing `OnEraseBkgnd` suppression.

**Tech Stack:** C++/MFC ListView custom draw, Python 3 standard-library source-contract tests, Visual Studio 2022 MSBuild

---

## Global Constraints

- Keep `CListCtrlEx::OnEraseBkgnd` returning `TRUE`.
- Keep `LVS_EX_DOUBLEBUFFER`; do not add Wine- or CrossOver-specific runtime checks.
- Do not call `UpdateWindow`, `RedrawWindow`, or request synchronous painting.
- Do not change playlist search, item data, row colors, selection, grid, or playing-item markers.
- Use the custom-draw HDC supplied by `NMLVCUSTOMDRAW`; do not acquire a separate window DC.

### Task 1: Clear the unused area in the base list control

**Files:**
- Modify: `tests/test_playlist_repaint_contract.py`
- Modify: `MusicPlayer2/ListCtrlEx.h:50-52`
- Modify: `MusicPlayer2/ListCtrlEx.cpp:270-283`
- Modify: `MusicPlayer2/ListCtrlEx.cpp:299-404`

**Interfaces:**
- Add: `void CListCtrlEx::FillEmptyListArea(CDC* pDC)`
- Preserve: `void CListCtrlEx::SetListData(ListData* pListData)`
- Preserve: `BOOL CListCtrlEx::OnEraseBkgnd(CDC* pDC)`

- [ ] **Step 1: Replace the source-contract test with the base-list expectations**

Replace `tests/test_playlist_repaint_contract.py` with:

```python
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIST_CTRL_SOURCE_PATH = PROJECT_ROOT / "MusicPlayer2" / "ListCtrlEx.cpp"
LIST_CTRL_HEADER_PATH = PROJECT_ROOT / "MusicPlayer2" / "ListCtrlEx.h"


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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
python3 -m unittest tests/test_playlist_repaint_contract.py -v
```

Expected: the existing invalidation test passes; the two new tests fail because `FillEmptyListArea` and control-level `CDRF_NOTIFYPOSTPAINT` do not exist.

- [ ] **Step 3: Declare the shared empty-area drawing helper**

Add the declaration below `IsRowSelected` in the protected section of `MusicPlayer2/ListCtrlEx.h`:

```cpp
    void FillEmptyListArea(CDC* pDC);
```

- [ ] **Step 4: Implement the bounded empty-area fill**

Add the following function immediately before `CListCtrlEx::IsRowSelected` in `MusicPlayer2/ListCtrlEx.cpp`:

```cpp
void CListCtrlEx::FillEmptyListArea(CDC* pDC)
{
    if (pDC == nullptr)
        return;

    CRect empty_rect;
    GetClientRect(empty_rect);
    const int item_count{ GetItemCount() };
    if (item_count > 0)
    {
        CRect last_item_rect;
        if (GetItemRect(item_count - 1, last_item_rect, LVIR_BOUNDS))
        {
            empty_rect.top = std::clamp(
                last_item_rect.bottom,
                empty_rect.top,
                empty_rect.bottom
            );
        }
    }

    if (!empty_rect.IsRectEmpty())
        pDC->FillSolidRect(empty_rect, m_background_color);
}
```

The clamp makes these cases deterministic:

- no items: fill the whole clipped client area;
- last item visible: fill from its bottom to the client bottom;
- last item below the client: fill nothing;
- last item above the client: fill the whole visible client area.

- [ ] **Step 5: Connect the base custom-draw handler**

Change the `CDDS_PREPAINT` case in `CListCtrlEx::OnNMCustomdraw` to:

```cpp
    case CDDS_PREPAINT:
        *pResult = CDRF_NOTIFYITEMDRAW | CDRF_NOTIFYPOSTPAINT;
        break;
```

Add this case after the existing `CDDS_ITEMPOSTPAINT` case:

```cpp
    case CDDS_POSTPAINT:
        FillEmptyListArea(CDC::FromHandle(nmcd.hdc));
        break;
```

- [ ] **Step 6: Run the focused test and verify GREEN**

Run:

```bash
python3 -m unittest tests/test_playlist_repaint_contract.py -v
```

Expected: all three tests pass.

- [ ] **Step 7: Review and commit the base-list behavior**

Run:

```bash
git diff --check
git diff -- MusicPlayer2/ListCtrlEx.h MusicPlayer2/ListCtrlEx.cpp tests/test_playlist_repaint_contract.py
git add MusicPlayer2/ListCtrlEx.h MusicPlayer2/ListCtrlEx.cpp tests/test_playlist_repaint_contract.py
git commit -m "fix: clear unused list area after painting"
```

Expected: no whitespace errors; the commit contains the helper, base custom-draw connection, and passing regression tests.

### Task 2: Connect the playlist-specific custom-draw handler

**Files:**
- Modify: `tests/test_playlist_repaint_contract.py`
- Modify: `MusicPlayer2/PlayListCtrl.cpp:250-355`

**Interfaces:**
- Reuse: `CListCtrlEx::FillEmptyListArea(CDC* pDC)`
- Modify behavior of: `CPlayListCtrl::OnNMCustomdraw`

- [ ] **Step 1: Add the failing playlist-specific contract**

Add this constant after `LIST_CTRL_HEADER_PATH` in `tests/test_playlist_repaint_contract.py`:

```python
PLAYLIST_SOURCE_PATH = PROJECT_ROOT / "MusicPlayer2" / "PlayListCtrl.cpp"
```

Add this assignment to `setUpClass`:

```python
        cls.playlist_source = PLAYLIST_SOURCE_PATH.read_text(
            encoding="utf-8-sig"
        )
```

Add this test method after `test_base_list_requests_and_handles_control_postpaint`:

```python
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
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
python3 -m unittest \
  tests.test_playlist_repaint_contract.PlaylistRepaintContractTest.test_playlist_requests_and_handles_control_postpaint \
  -v
```

Expected: one failure because `CPlayListCtrl::OnNMCustomdraw` requests only item-level drawing and has no control-level post-paint case.

- [ ] **Step 3: Connect the playlist custom-draw handler**

Change the `CDDS_PREPAINT` case in `CPlayListCtrl::OnNMCustomdraw` to:

```cpp
    case CDDS_PREPAINT:
        *pResult = CDRF_NOTIFYITEMDRAW | CDRF_NOTIFYPOSTPAINT;
        break;
```

Add this case after the existing `CDDS_ITEMPOSTPAINT` case:

```cpp
    case CDDS_POSTPAINT:
        FillEmptyListArea(CDC::FromHandle(nmcd.hdc));
        break;
```

- [ ] **Step 4: Run the focused and complete tests and verify GREEN**

Run:

```bash
python3 -m unittest \
  tests.test_playlist_repaint_contract.PlaylistRepaintContractTest.test_playlist_requests_and_handles_control_postpaint \
  -v
python3 -m unittest discover -s tests -v
```

Expected: the focused playlist contract passes and the complete test suite passes.

- [ ] **Step 5: Review and commit the playlist connection**

Run:

```bash
git diff --check
git diff -- MusicPlayer2/PlayListCtrl.cpp tests/test_playlist_repaint_contract.py
git add MusicPlayer2/PlayListCtrl.cpp tests/test_playlist_repaint_contract.py
git commit -m "fix: clear playlist background after painting"
```

Expected: no whitespace errors; the commit contains only the playlist post-paint connection and its regression contract.

### Task 3: Verify source, build, and runtime behavior

**Files:**
- Verify: `MusicPlayer2/ListCtrlEx.h`
- Verify: `MusicPlayer2/ListCtrlEx.cpp`
- Verify: `MusicPlayer2/PlayListCtrl.cpp`
- Verify: `tests/test_playlist_repaint_contract.py`

- [ ] **Step 1: Run all locally available automated checks**

Run:

```bash
python3 -m unittest discover -s tests -v
git diff --check HEAD~2
git status --short
```

Expected: all tests pass, no whitespace errors, and the worktree is clean.

- [ ] **Step 2: Build Release x64 with Visual Studio 2022**

From a Visual Studio 2022 developer shell, run:

```powershell
msbuild MusicPlayer2.sln -t:Build "-p:Configuration=Release;Platform=x64" -m:4
```

Expected: `Build succeeded` with zero errors.

- [ ] **Step 3: Build Release x86 with Visual Studio 2022**

Run:

```powershell
msbuild MusicPlayer2.sln -t:Build "-p:Configuration=Release;Platform=x86" -m:4
```

Expected: `Build succeeded` with zero errors.

- [ ] **Step 4: Verify the repaired CrossOver scenario**

Run the newly built x64 executable in the affected CrossOver 26.3 bottle:

1. Open a traditional playlist containing multiple tracks.
2. Enter a search term with no matches.
3. Confirm that only “没有结果可以显示” remains and the area below it is immediately white.
4. Resize the window and confirm that no additional old pixels disappear, proving the pre-resize frame was already correct.
5. Type and delete several search terms and confirm every transition remains immediate.
6. Scroll a long playlist and confirm rows, grid lines, selection, and the playing marker are unchanged.

Expected: no residual rows before resizing and no new flicker during search transitions.

- [ ] **Step 5: Verify Windows and other-list regressions**

On Windows:

1. Resize the main window continuously for at least five seconds.
2. Search for and clear a nonexistent track name.
3. Open a media-library list that uses `CListCtrlEx`.
4. Confirm that item rows and the unused background area render normally.

Expected: no obvious resize flicker; list selection, scrolling, grid lines, and empty backgrounds remain correct.

- [ ] **Step 6: Record unavailable platform checks honestly**

If the current environment lacks Visual Studio/MSBuild or Windows, report those checks as unavailable. Do not claim the CrossOver fix is complete until the new executable has passed Task 3 Step 4.
