"""The published examples say nothing the data pack next to them does not hold."""
import re
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).parent.parent / "examples"
FOLDERS = sorted(path.parent for path in EXAMPLES.glob("*/analisi.md"))
SWAP = str.maketrans(",.", ".,")


def pack_text(folder: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted((folder / "pacchetto").glob("*.md")))


def test_there_is_an_example_of_both_levels():
    assert FOLDERS and all((folder / "piano.md").is_file() and (folder / "README.md").is_file() for folder in FOLDERS)


@pytest.mark.parametrize("folder", FOLDERS, ids=lambda folder: folder.name)
@pytest.mark.parametrize("name", ["analisi.md", "piano.md"])
def test_every_figure_of_an_example_is_written_in_its_pack(folder, name):
    pack, text = pack_text(folder), (folder / name).read_text(encoding="utf-8")
    missing = []
    for figure in sorted(set(re.findall(r"\d+(?:[.,]\d+)*", text))):
        # the examples write figures the Italian way; the pack writes most of them the English way
        found = any(re.search(r"(?<![\d.,])" + re.escape(form) + r"(?!\d|[.,]\d)", pack)
                    for form in (figure, figure.translate(SWAP)))
        if not found:
            missing.append(figure)
    assert not missing


@pytest.mark.parametrize("folder", FOLDERS, ids=lambda folder: folder.name)
def test_every_ad_named_in_an_example_is_in_its_pack(folder):
    pack = pack_text(folder)
    for name in ("analisi.md", "piano.md"):
        ids = set(re.findall(r"\b\d{13,17}\b", (folder / name).read_text(encoding="utf-8")))
        assert ids and all(library_id in pack for library_id in ids)


@pytest.mark.parametrize("folder", FOLDERS, ids=lambda folder: folder.name)
def test_an_example_shows_no_path_of_a_computer(folder):
    for path in folder.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"[A-Za-z]:\\|/Users/|/home/|AppData", text), path.name


@pytest.mark.parametrize("folder", FOLDERS, ids=lambda folder: folder.name)
def test_the_amounts_of_the_plan_are_those_the_program_computed(folder):
    project = (folder / "pacchetto" / "project.md").read_text(encoding="utf-8")
    plan = (folder / "piano.md").read_text(encoding="utf-8")
    # every amount with a decimal or a thousands part under "Numbers for the test"; "2,5" is a multiplier
    computed = set(re.findall(r"\d+(?:[.,]\d+)+", project.split("##")[2])) - {"2,5"}
    assert len(computed) >= 8 and not [amount for amount in computed if amount not in plan]
