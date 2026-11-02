# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Regression coverage for a "No keyword with name ... found" failure during the
AIWB Robot dry-run.

arguments.txt puts both this directory's ``libraries`` and AIRM's
``../../airm/specs/libraries`` on ``--pythonpath`` for the SAME dry-run process.
Two library files there can share a stem, and Robot caches Python libraries in
``sys.modules`` under that stem rather than under their full path -- so the
second import can silently resolve to the first file, and every keyword the
shadowed file defines disappears. A source-text diff of filenames cannot prove
this stays fixed; the structural guard below can.

Which import forms are actually vulnerable, read off ``robot/utils/importer.py``
in the pinned robotframework rather than assumed:

``NonDottedImporter`` and ``DottedImporter`` -- a bare ``Library Foo`` or a
dotted ``Library libraries.Foo`` -- call ``__import__``, which honours
``sys.modules``. The first root to supply the name wins for the rest of the
process and the other file is never loaded. These are the genuinely vulnerable
form.

``ByPathImporter`` -- ``Library libraries/Foo.py`` -- first calls
``_remove_wrong_module_from_sys_modules``, which compares the cached module's
``__file__`` directory against the one being imported and evicts a mismatch
before re-importing. A collision between two path-style imports therefore
self-heals.

Imports are read with Robot's own parser (``robot.api.get_model`` /
``get_resource_model``) rather than a regex over the source text, matching
``test_custom_model_cleanup.py`` and the other AST-based guards in this
directory. That is not only convention: an import is a ``LibraryImport`` or
``ResourceImport`` node or it is nothing, so the forms a hand-written pattern has
to re-derive one at a time -- tab versus two-space cells, a lowercase ``library``
setting, ``WITH NAME``/``AS`` aliases, dotted package names, a commented-out row
-- are all handled by construction, by the same tokenizer Robot itself runs.

An alias is exposed as a separate ``alias`` field, and this module reads only
``name``. That is the correct token: aliasing is applied as
``lib = lib.copy(name=alias)`` in ``robot/running/importer.py`` *after* the import
has already resolved and cached the module, so it renames the library in the
keyword namespace and never touches the ``sys.modules`` key. Two same-stem
libraries therefore collide identically whether either one is aliased.

Listeners count too. ``--listener <name>`` loads a Python module into the same
process and the same ``sys.modules``, so a listener and a library sharing a stem
shadow each other exactly as two libraries would.

The guard reports a duplicate stem whatever the form, which is over-cautious for
a pure path-vs-path pair and exact for anything else. That is deliberate, and
not merely caution: the eviction only repairs the path-style import itself, so a
stem reached by BOTH a path-style and a bare import is still vulnerable in the
order path-then-bare, where the bare import reads whatever the path import left
cached. A pair that is path-only today becomes that case the moment anyone adds
a one-line bare import, and the failure is silent when it does.
"""

from pathlib import Path

from robot.api import get_model, get_resource_model
from robot.parsing.model.statements import LibraryImport, ResourceImport

SPECS_DIR = Path(__file__).resolve().parent
ARGUMENTS_FILE = SPECS_DIR / "arguments.txt"
APPS_DIR = SPECS_DIR.parents[2]


def _argument_tokens(text: str) -> list[str]:
    """An argument file as Robot reads it: line-oriented, with comment lines dropped.

    ``robot/utils/argumentparser.py`` strips each line, treats one beginning with ``-`` as
    an option and any other non-empty line as a value, and skips a line beginning with
    ``#`` entirely. Splitting the whole file on whitespace instead cannot tell a comment
    from a live argument: a commented-out ``# --listener Ghost`` then reads as an active
    listener, and a commented-out ``# --pythonpath <dir>`` widens the search roots this
    guard resolves imports against -- which can both invent a collision and hide one.

    A non-option line is kept whole rather than split, because a value is a path and a
    path may contain spaces. An option line is split on its first separator only, for the
    same reason: ``_split_option`` yields exactly a name and a value, so
    ``--pythonpath /some path`` names one directory rather than two tokens.
    """
    tokens: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tokens.extend(_split_option(line) if line.startswith("-") else [line])
    return tokens


def _split_option(option: str) -> list[str]:
    """An option line split the way ``_split_option`` in Robot's argument parser splits it.

    The first separator wins and the remainder is the value, whichever of space or ``=``
    appears first. Splitting on every space instead would read a value containing one as
    several tokens, which drops the rest of a path and shifts every following value.
    """
    has_space, has_equals = " " in option, "=" in option
    if not has_space and not has_equals:
        return [option]
    if not has_equals:
        separator = " "
    elif not has_space:
        separator = "="
    else:
        separator = " " if option.index(" ") < option.index("=") else "="
    name, value = option.split(separator, 1)
    return [name, value.strip()]


def _pythonpath_entries(text: str) -> list[str]:
    """Every value following a ``--pythonpath`` flag, in file order."""
    tokens = _argument_tokens(text)
    return [tokens[i + 1] for i, token in enumerate(tokens) if token == "--pythonpath" and i + 1 < len(tokens)]


def _search_roots(arguments_file: Path) -> list[Path]:
    """Directories one Robot process resolves a non-relative import against: the suite
    directory it is pointed at, then every ``--pythonpath`` entry, in file order."""
    roots = [arguments_file.parent.resolve()]
    for entry in _pythonpath_entries(arguments_file.read_text()):
        path = (arguments_file.parent / entry).resolve()
        if path.is_dir() and path not in roots:
            roots.append(path)
    return roots


def _listener_entries(text: str) -> list[str]:
    """Every ``--listener`` value, stripped of its ``:``-separated arguments.

    A listener is a Python module loaded into the same process and keyed in
    ``sys.modules`` by the same stem rule as a library, so leaving it out would let a
    listener/library collision pass unseen. ``--listener Foo:arg`` names module ``Foo``.
    """
    tokens = _argument_tokens(text)
    values = [
        tokens[index + 1] for index, token in enumerate(tokens) if token == "--listener" and index + 1 < len(tokens)
    ]
    return [value.split(":", maxsplit=1)[0] for value in values]


def _imports(robot_file: Path) -> list[tuple[str, str]]:
    """``("Library"|"Resource", name)`` for each import in a Robot suite or resource file.

    Robot's own parser, so the node type decides what an import is. A ``#`` comment, a
    tab-separated cell, a lowercase ``library`` setting and an aliased row need no special
    handling here: the tokenizer has already classified them. ``name`` is the import token
    and never the alias, which is the token that fixes the ``sys.modules`` key.
    """
    read = get_resource_model if robot_file.suffix == ".resource" else get_model
    model = read(str(robot_file))
    imports: list[tuple[str, str]] = []
    for section in model.sections:
        for statement in getattr(section, "body", []):
            if isinstance(statement, LibraryImport):
                imports.append(("Library", statement.name))
            elif isinstance(statement, ResourceImport):
                imports.append(("Resource", statement.name))
    return [(kind, name) for kind, name in imports if name]


def _resolve(name: str, importing_file: Path, roots: list[Path]) -> Path | None:
    """Where Robot would load a path-style ``name`` from: relative to the importing file
    first, then each search root in order. ``None`` when no file backs it."""
    for candidate in [importing_file.parent / name, *(root / name for root in roots)]:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _resolve_bare(name: str, roots: list[Path]) -> list[Path]:
    """Every file a module-style ``Library <name>`` could resolve to, in search order.

    All of them, not just the winner: this form resolves through ``__import__``, which
    honours ``sys.modules``, so more than one root supplying the name IS the shadowing --
    the first root silently wins and the other module's keywords never load. Unlike the
    path-style form, nothing evicts the stale module first (see the note on
    ``ByPathImporter`` in the module docstring), which is why this form is reported from a
    single statement rather than from a pair of them. A name with no file behind it (a
    stdlib or installed module such as ``Collections``) yields nothing and is not the
    guard's concern.

    Dotted names are package paths, so ``libraries.DatasetUploader`` is probed as
    ``<root>/libraries/DatasetUploader.py``. Robot accepts that form and the repository
    uses it, so probing only ``<root>/<name>.py`` would drop those imports from the walk
    entirely -- and a dropped import is a library this guard never sees.
    """
    relative = Path(*name.split("."))
    return [
        (root / relative).with_suffix(".py").resolve()
        for root in roots
        if (root / relative).with_suffix(".py").is_file()
    ]


def _imported_libraries(arguments_file: Path) -> dict[str, list[Path]]:
    """Every ``.py`` module one Robot process loads, keyed by the stem it lands under in
    ``sys.modules``: the libraries reached by walking ``Resource`` imports out from the
    suite, plus the listeners the run config names.

    Derived from the import statements rather than from directory names: a
    ``--pythonpath`` entry is neither necessary (``Library libraries/Foo.py`` resolves
    relative to the importing file, so the UI suites reach a ``libraries`` directory that
    is never named on the pythonpath at all) nor sufficient (a directory whose resources
    nothing imports contributes no module, and flagging it would be a false alarm).
    """
    roots = _search_roots(arguments_file)
    queue = sorted(arguments_file.parent.rglob("*.robot"))
    seen: set[Path] = set()
    libraries: dict[str, list[Path]] = {}

    # Listeners first: they are loaded by the same process under the same stem rule, so
    # they belong in the same namespace map as the libraries walked below.
    for listener in _listener_entries(arguments_file.read_text()):
        if listener.endswith(".py"):
            target = _resolve(listener, arguments_file, roots)
            targets = [target] if target is not None else []
            key = Path(listener).stem
        else:
            targets = _resolve_bare(listener, roots)
            key = listener
        for target in targets:
            if target not in libraries.setdefault(key, []):
                libraries[key].append(target)

    while queue:
        robot_file = queue.pop()
        if robot_file in seen:
            continue
        seen.add(robot_file)
        for kind, name in _imports(robot_file):
            if kind == "Resource":
                target = _resolve(name, robot_file, roots)
                if target is not None:
                    queue.append(target)
                continue
            if name.endswith(".py"):
                target = _resolve(name, robot_file, roots)
                targets = [target] if target is not None else []
                # Robot caches a path-style import under the file's stem, so this shares a
                # namespace with a bare ``Library <stem>`` elsewhere in the same process.
                key = Path(name).stem
            else:
                targets = _resolve_bare(name, roots)
                # A module-style import lands in sys.modules under the name as written, so
                # a dotted one occupies its own namespace and cannot collide with a stem.
                key = name
            for target in targets:
                if target not in libraries.setdefault(key, []):
                    libraries[key].append(target)
    return libraries


def test_arguments_file_puts_both_cleanup_library_dirs_on_the_same_pythonpath() -> None:
    """Ground the rest of this module in the actual CI dry-run config, not an
    assumption about how the two suites get linked together."""
    entries = _pythonpath_entries(ARGUMENTS_FILE.read_text())
    assert "libraries" in entries
    assert "../../airm/specs/libraries" in entries


def test_library_walk_reaches_a_directory_the_pythonpath_never_names() -> None:
    """A library directory reached only by a relative import must still be guarded, or
    the walk silently stops covering whole suites.

    The UI AIRM suite is that case, and is the reason this is derived from the import
    statements rather than from ``--pythonpath`` entries named ``libraries``: its own
    ``specs/libraries`` is on no entry at all, and its resources reach into it with
    ``Library ../libraries/<name>.py``, resolved relative to the importing file.
    """
    ui_arguments = APPS_DIR / "ui" / "airm" / "specs" / "arguments.txt"
    assert ui_arguments.is_file(), "the UI AIRM suite is the fixture for this guard"

    ui_libraries = (ui_arguments.parent / "libraries").resolve()
    named = {(ui_arguments.parent / entry).resolve() for entry in _pythonpath_entries(ui_arguments.read_text())}
    assert ui_libraries not in named, (
        f"{ui_libraries} is now on the pythonpath, so it no longer exercises relative resolution"
    )

    reached = {path for paths in _imported_libraries(ui_arguments).values() for path in paths}
    assert any(path.parent == ui_libraries for path in reached), (
        f"no library under {ui_libraries} was reached; the walk is not following relative imports"
    )


def test_a_commented_out_directive_is_not_read_as_an_active_one() -> None:
    """A run config is not a bag of whitespace-separated words; comments are real.

    Robot drops a line beginning with ``#`` outright. Reading the file as one token stream
    instead makes a commented-out directive indistinguishable from a live one, in both
    damaging directions: a disabled ``--pythonpath`` silently widens the roots imports
    resolve against, inventing collisions and masking real ones, and a disabled
    ``--listener`` puts a module into the sweep that the run never loads.

    The real AIWB config is the fixture, because it documents an inactive listener in
    exactly this shape, and the token-stream reading returned a bare ``#`` for it.
    """
    disabled = "--pythonpath\n.\n# --pythonpath    ../SHOULD-NOT-BE-ACTIVE\n# --listener    Ghost\n"
    assert _pythonpath_entries(disabled) == ["."], "a commented-out pythonpath must not widen the roots"
    assert _listener_entries(disabled) == [], "a commented-out listener must not enter the sweep"

    # A value containing a space is one value. Splitting an option line on every space
    # would take only its first fragment as the directory and shift every later value.
    assert _pythonpath_entries("--pythonpath /some path/with spaces\n") == ["/some path/with spaces"]
    assert _pythonpath_entries("--pythonpath=/some path\n") == ["/some path"]

    live = _listener_entries(ARGUMENTS_FILE.read_text())
    assert "AimCatalogGenerator" in live, f"the active listener must still be found: {live}"
    assert all(not entry.startswith("#") for entry in live), f"a comment leaked in as a listener: {live}"
    assert all(not entry.startswith("#") for entry in _pythonpath_entries(ARGUMENTS_FILE.read_text()))


def test_every_import_spelling_robot_accepts_is_read_as_one_import(tmp_path: Path) -> None:
    """The forms a hand-written pattern would have to special-case, read in one pass.

    Each row here is valid Robot that an earlier regex-based version of this module either
    missed outright or misread, and every miss is silent: an import the walk never sees is
    a module never checked for a collision, which the sweep then reports as a clean pass.
    Kept as executable documentation of what the walk relies on the parser for, so an
    upgrade that changed any of it fails here rather than quietly narrowing the sweep.

    Covered: lower and upper case settings, tab-separated cells, ``WITH NAME`` and its
    modern ``AS`` spelling, dotted package names, and a commented-out row that must not be
    read as an import at all.
    """
    suite = tmp_path / "forms.robot"
    suite.write_text(
        "*** Settings ***\n"
        "library    libraries/Foo.py\n"
        "LIBRARY    libraries/Bar.py\n"
        "LiBrArY\tlibraries/Baz.py\n"
        "Library    libraries/Aliased.py    WITH NAME    Renamed\n"
        "Library    libraries.Dotted    AS    D\n"
        "resource    lower.resource\n"
        "RESOURCE\tupper.resource\n"
        "# Library    libraries/CommentedOut.py\n"
    )

    assert _imports(suite) == [
        ("Library", "libraries/Foo.py"),
        ("Library", "libraries/Bar.py"),
        ("Library", "libraries/Baz.py"),
        # The import token, never the alias: the alias is applied after the module is
        # cached, so it cannot move the sys.modules key a collision is keyed on.
        ("Library", "libraries/Aliased.py"),
        ("Library", "libraries.Dotted"),
        ("Resource", "lower.resource"),
        ("Resource", "upper.resource"),
    ]


def test_a_configured_listener_is_swept_like_a_library(tmp_path: Path) -> None:
    """A listener shares ``sys.modules`` with the libraries, so it shares their collisions.

    ``--listener Foo`` loads a Python module into the same process under the same stem
    rule. Walking only ``Library`` imports would leave a listener/library stem clash
    invisible while the sweep reports success -- and the repository configures listeners
    today, so this is a live path rather than a hypothetical one.
    """
    libraries = tmp_path / "libraries"
    libraries.mkdir()
    (libraries / "Shared.py").write_text("")
    other = tmp_path / "other"
    other.mkdir()
    (other / "Shared.py").write_text("")
    (tmp_path / "suite.robot").write_text("*** Settings ***\nLibrary    other/Shared.py\n")
    arguments = tmp_path / "arguments.txt"
    arguments.write_text("--pythonpath\n.\n--listener\nlibraries/Shared.py:someArg\n")

    loaded = _imported_libraries(arguments)
    assert "Shared" in loaded, f"the listener never entered the sweep: {sorted(loaded)}"
    assert len(loaded["Shared"]) > 1, (
        f"a listener colliding with a library must be reported, found only {loaded['Shared']}"
    )


def _arguments_files() -> list[Path]:
    """Every Robot run config under ``apps``, found at whatever depth it sits.

    Not a fixed ``*/*/specs`` glob: that encodes today's two-level ``<team>/<app>`` layout
    as though it were a rule, and an app added at any other depth would silently drop out
    of the sweep below -- which reports a clean pass rather than an absence.
    """
    return sorted(APPS_DIR.rglob("specs/arguments.txt"))


def _uncovered_suites(suites: list[Path], roots: list[Path]) -> list[Path]:
    """Suite directories no run config reaches, by containment rather than equality.

    A separate function so the rule can be exercised on synthetic paths. Against the real
    tree every suite happens to sit at the same depth, so a depth assumption reintroduced
    into the discovery glob would change nothing observable and a mutation would pass --
    the rule has to be provable independently of today's directory layout.
    """
    return [suite for suite in suites if not any(suite == root or root in suite.parents for root in roots)]


def test_a_suite_outside_every_run_config_is_reported_uncovered() -> None:
    """The coverage rule itself, on synthetic paths, so it does not rest on the real tree.

    A nested suite is covered by its parent's config; a sibling at a different depth is
    not covered by anything and has to be named. The second case is the one a fixed-depth
    discovery glob silently creates.
    """
    roots = [Path("apps/api/aiwb/specs"), Path("apps/ui/aiwb/specs")]
    nested = Path("apps/api/aiwb/specs/airm")
    elsewhere = Path("apps/edge/gateway/v2/specs")

    assert _uncovered_suites([nested], roots) == []
    assert _uncovered_suites([elsewhere], roots) == [elsewhere]
    assert _uncovered_suites([nested, elsewhere], roots) == [elsewhere]


def test_every_robot_suite_is_reached_by_a_discovered_run_config() -> None:
    """Asserting the config list is non-empty proves it found something, not everything.

    A suite no discovered ``arguments.txt`` covers is a suite the collision sweep never
    walks, and the sweep passing then means only that it did not look. Coverage is
    reachability rather than an exact directory match, because a nested suite directory
    (``apps/api/airm/specs/airm``) is legitimately walked from its parent's config.
    """
    roots = [arguments_file.parent for arguments_file in _arguments_files()]
    assert roots, "no Robot run config found under apps/"

    suites = sorted({path.parent for path in APPS_DIR.rglob("*.robot")})
    assert suites, "no Robot suites found under apps/; the sweep would be vacuous"

    uncovered = _uncovered_suites(suites, roots)
    assert not uncovered, (
        f"Robot suite(s) reached by no arguments.txt, so never swept for import collisions: "
        f"{[str(suite.relative_to(APPS_DIR)) for suite in uncovered]}"
    )


def test_cleanup_library_filenames_do_not_collide() -> None:
    """Structural guard over every suite's real config, not just the AIWB/AIRM pair:
    within one Robot process no two ``.py`` libraries may share a stem, or the importer
    will shadow one with the other and drop its keywords."""
    arguments_files = _arguments_files()
    assert arguments_files

    offenders: list[str] = []
    for arguments_file in arguments_files:
        for stem, paths in sorted(_imported_libraries(arguments_file).items()):
            if len(paths) > 1:
                shadowed = " vs ".join(str(path.relative_to(APPS_DIR.parent)) for path in sorted(paths))
                offenders.append(f"{arguments_file.relative_to(APPS_DIR)}: {stem} ({shadowed})")
    assert not offenders, f"library filename stem(s) shadowed on a shared pythonpath: {offenders}"
