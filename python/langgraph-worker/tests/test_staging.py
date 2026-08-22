from puerflow_worker.tools.staging import FileFingerprint, _safe_path, changed_paths


def test_safe_path_rejects_escape():
    assert _safe_path("notes/a.txt")
    assert not _safe_path("../secret")
    assert not _safe_path("/etc/passwd")


def test_changed_paths_detects_add_update_delete():
    before = [FileFingerprint("a.txt", 1, 0, "old", "old")]
    after = [FileFingerprint("b.txt", 1, 0, "new", "new")]
    assert changed_paths(before, after) == {"a.txt", "b.txt"}
