from __future__ import annotations

from pathlib import Path

import pytest
from scripts.check_documentation import ROOT, repository_reference


def test_evidence_references_must_remain_inside_the_repository() -> None:
    assert repository_reference("README.md") == (ROOT / "README.md").resolve()

    with pytest.raises(AssertionError, match="repository-relative"):
        repository_reference(str(Path("/etc/passwd")))
    with pytest.raises(AssertionError, match="escapes the repository"):
        repository_reference("../outside-evidence.json")
    with pytest.raises(AssertionError, match="not a repository file"):
        repository_reference("docs")
