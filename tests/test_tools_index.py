"""Tests for the tools index category filter."""

import pytest
from click.testing import CliRunner

from coala_client import main
from coala_client.tools_index import resolve_category, search_tools

INDEX = [
    {"name": "bwa", "category": "Command-line tool", "category_group": "Command-line tools"},
    {"name": "bwa-py", "category": "Python library", "category_group": "Libraries"},
    {"name": "Rbwa", "category": "Bioconductor package", "category_group": "Libraries"},
    {"name": "bwa-r", "category": "R package", "category_group": "Libraries"},
    {"name": "Bio-BWA", "category": "Perl module", "category_group": "Libraries"},
    {"name": "bwa-other", "category": "Other library", "category_group": "Libraries"},
    {"name": "bwa-galaxy", "category": "Galaxy workflow", "category_group": "Workflows"},
    {"name": "bwa-nf", "category": "Nextflow workflow", "category_group": "Workflows"},
    {"name": "bwa-cwl", "category": "CWL workflow", "category_group": "Workflows"},
]

LIBRARIES = {"bwa-py", "Rbwa", "bwa-r", "Bio-BWA", "bwa-other"}


def _names(tools: list[dict]) -> set[str]:
    return {t["name"] for t in tools}


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("Python library", {"bwa-py"}),
        ("python library", {"bwa-py"}),
        ("  Galaxy workflow ", {"bwa-galaxy"}),
        ("Libraries", LIBRARIES),
        ("workflows", {"bwa-galaxy", "bwa-nf", "bwa-cwl"}),
        ("Command-line tools", {"bwa"}),
    ],
)
def test_category_and_group_names(category, expected):
    assert _names(search_tools(INDEX, "bwa", category=category)) == expected


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("CLI", {"bwa"}),
        ("python", {"bwa-py"}),
        ("R", {"bwa-r"}),
        ("bioconductor", {"Rbwa"}),
        ("perl", {"Bio-BWA"}),
        ("galaxy", {"bwa-galaxy"}),
        ("nextflow", {"bwa-nf"}),
        ("CWL", {"bwa-cwl"}),
        ("library", LIBRARIES),
    ],
)
def test_old_short_labels(alias, expected):
    assert _names(search_tools(INDEX, "bwa", category=alias)) == expected


def test_unknown_category_matches_nothing():
    assert resolve_category(INDEX, "nope") == set()
    assert search_tools(INDEX, "bwa", category="nope") == []


def test_old_index_labels_still_match_directly():
    old_index = [{"name": "bwa", "category": "CLI"}, {"name": "bwa-py", "category": "python"}]
    assert _names(search_tools(old_index, "bwa", category="cli")) == {"bwa"}


def test_cli_search_accepts_alias(monkeypatch):
    monkeypatch.setattr(main, "get_tools_index", lambda force_refresh=False: INDEX)
    result = CliRunner().invoke(main.cli, ["search", "bwa", "--category", "CLI"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "[Command-line tool] bwa"


def test_cli_search_unknown_category(monkeypatch):
    monkeypatch.setattr(main, "get_tools_index", lambda force_refresh=False: INDEX)
    result = CliRunner().invoke(main.cli, ["search", "bwa", "--category", "nope"])
    assert result.exit_code == 1
    assert "Unknown category 'nope'" in result.output
    assert "Groups: Command-line tools, Libraries, Workflows" in result.output
