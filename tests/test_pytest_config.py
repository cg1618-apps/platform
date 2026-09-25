"""pytest.ini: this repository collects its own tests and not the apps'.

The apps are cloned inside this directory, so the default collection root is
shared with four other repositories. Getting this wrong is not subtle - it is
119 collection errors - but it is also invisible until someone clones the apps,
which is to say invisible on CI and obvious on every development machine.
"""

import configparser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTEST_INI = ROOT / "pytest.ini"


def _config():
    parser = configparser.ConfigParser()
    parser.read(PYTEST_INI, encoding="utf-8")
    return parser


def test_the_file_exists():
    assert PYTEST_INI.is_file()


def test_collection_is_pinned_to_this_repository_s_tests():
    config = _config()
    assert config.has_section("pytest")
    testpaths = config["pytest"]["testpaths"].split()
    assert testpaths == ["tests"], testpaths


def test_the_pinned_path_is_where_the_tests_actually_are():
    """A testpaths naming a directory that does not exist collects nothing.

    Nothing collected exits 5 rather than 0, but a suite that silently shrank
    to zero is the failure this guards - so assert the directory holds this
    file, rather than merely that it exists.
    """
    testpaths = _config()["pytest"]["testpaths"].split()
    for entry in testpaths:
        assert (ROOT / entry).is_dir(), entry
    assert (ROOT / testpaths[0] / "test_pytest_config.py").is_file()
