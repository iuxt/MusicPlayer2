# CrossOver Playlist Repaint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure replacing virtual playlist data invalidates the complete list client area so CrossOver cannot retain pixels from removed rows.

**Architecture:** Keep the existing `WM_ERASEBKGND` suppression that prevents resize flicker. Extend the existing `CListCtrlEx::SetListData(ListData*)` contract so every data replacement schedules one asynchronous, non-erasing full-client repaint.

**Tech Stack:** C++/MFC, Python 3 standard-library regression test, Visual Studio 2022 MSBuild

## Global Constraints

- Preserve the existing `CListCtrlEx::OnEraseBkgnd` behavior that returns `TRUE`.
- Do not add Wine- or CrossOver-specific branches.
- Do not change playlist data, search behavior, row styling, or the custom-drawn playlist.
- Use `Invalidate(FALSE)`; do not call `UpdateWindow`, `RedrawWindow`, or request background erasure.
- Limit production changes to `CListCtrlEx::SetListData(ListData*)`.

---

### Task 1: Enforce the virtual-list repaint contract

**Files:**
- Create: `tests/test_playlist_repaint_contract.py`
- Modify: `MusicPlayer2/ListCtrlEx.cpp:211-217`

**Interfaces:**
- Consumes: `void CListCtrlEx::SetListData(ListData* pListData)`
- Produces: the guarantee that a successful virtual-list data replacement calls `Invalidate(FALSE)` after `SetItemCount`

- [ ] **Step 1: Write the failing source-contract regression test**

Create `tests/test_playlist_repaint_contract.py`:

```python
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
```

- [ ] **Step 2: Run the regression test and verify RED**

Run:

```bash
cd /Users/iuxt/code/MusicPlayer2
python3 -m unittest tests/test_playlist_repaint_contract.py -v
```

Expected: `FAIL`, because the current `SetListData(ListData*)` body does not contain `Invalidate(FALSE)` after `SetItemCount`.

- [ ] **Step 3: Implement the minimal repaint request**

Change `CListCtrlEx::SetListData(ListData*)` in `MusicPlayer2/ListCtrlEx.cpp` to:

```cpp
void CListCtrlEx::SetListData(ListData* pListData)
{
    if (pListData == nullptr)
        return;
    m_pListData = pListData;
    SetItemCount(pListData->size());
    Invalidate(FALSE);
}
```

- [ ] **Step 4: Run the regression test and verify GREEN**

Run:

```bash
cd /Users/iuxt/code/MusicPlayer2
python3 -m unittest tests/test_playlist_repaint_contract.py -v
```

Expected: `PASS` for `test_virtual_list_data_update_invalidates_without_background_erase`.

- [ ] **Step 5: Check formatting and review the focused diff**

Run:

```bash
cd /Users/iuxt/code/MusicPlayer2
git diff --check
git diff -- MusicPlayer2/ListCtrlEx.cpp tests/test_playlist_repaint_contract.py
```

Expected: no whitespace errors; the production diff contains only the `Invalidate(FALSE)` call.

- [ ] **Step 6: Commit the tested fix**

```bash
cd /Users/iuxt/code/MusicPlayer2
git add MusicPlayer2/ListCtrlEx.cpp tests/test_playlist_repaint_contract.py
git commit -m "fix: refresh virtual playlist after data changes"
```

Expected: one commit containing the regression test and one-line production fix.

---

### Task 2: Verify builds and runtime behavior

**Files:**
- Verify: `MusicPlayer2.sln`
- Verify: `MusicPlayer2/ListCtrlEx.cpp`
- Verify: `tests/test_playlist_repaint_contract.py`

**Interfaces:**
- Consumes: the repaint guarantee implemented by Task 1
- Produces: build and runtime evidence that the fix removes CrossOver residual rows without restoring Windows resize flicker

- [ ] **Step 1: Re-run the cross-platform regression test from a clean process**

Run:

```bash
cd /Users/iuxt/code/MusicPlayer2
python3 -m unittest tests/test_playlist_repaint_contract.py -v
```

Expected: one test passes.

- [ ] **Step 2: Build Release x64 on a Windows Visual Studio 2022 environment**

Run:

```powershell
msbuild MusicPlayer2.sln -t:Build "-p:Configuration=Release;Platform=x64" -m:4
```

Run this command from the repository root. Expected: `Build succeeded` with zero errors.

- [ ] **Step 3: Build Release x86 on a Windows Visual Studio 2022 environment**

Run:

```powershell
msbuild MusicPlayer2.sln -t:Build "-p:Configuration=Release;Platform=x86" -m:4
```

Run this command from the repository root. Expected: `Build succeeded` with zero errors.

- [ ] **Step 4: Reproduce the repaired CrossOver scenario**

Run the newly built executable in the affected CrossOver bottle:

1. Open a traditional playlist containing multiple tracks.
2. Enter a search term with no matches.
3. Verify that only “没有结果可以显示” remains and all previous rows disappear immediately.
4. Resize the window and verify that the list does not visually change.
5. Type and delete several search terms and verify that list changes remain immediate.

Expected: no residual rows before or after resizing.

- [ ] **Step 5: Check the Windows resize regression**

Run the newly built executable on Windows:

1. Show the traditional playlist.
2. Resize the main window continuously for at least five seconds.
3. Search for and clear a nonexistent track name.

Expected: no obvious list background flicker; search and list selection behavior remain unchanged.

- [ ] **Step 6: Record unavailable platform verification honestly**

If the current environment lacks Visual Studio/MSBuild or a Windows runtime, do not claim Tasks 2.2, 2.3, or 2.5 passed. Report the exact unavailable checks and provide the successful source-contract test and diff verification as the completed local evidence.
