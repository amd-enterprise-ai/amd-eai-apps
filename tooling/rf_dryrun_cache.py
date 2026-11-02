# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Speed up ``robot --dryrun`` by caching keyword resolution.

Robot Framework has no namespace-level runner cache: every keyword call re-scans
all transitively imported resource files, and each scan regex-matches every
embedded-argument keyword. Under the layered spec architecture a single suite
imports ~two dozen resources, so a dry-run resolves the same (name -> keyword)
mapping millions of times. The scan, not imports or I/O, dominates dry-run wall
time.

This module is a Robot listener. When -- and only when -- it observes a dry-run,
it installs a per-``KeywordStore`` cache over the resource- and library-scan step.

Correctness: a name is cached only when its scan finds 0 or 1 matching keyword.
Ambiguous scans are deliberately excluded from this optimization, so RF always
runs its full tie-break chain for them. The cache is cleared whenever the
resolution inputs change (a resource/library import or a library search-order
change), so a mid-suite import cannot serve a stale result.

Within a process, real (non-dry-run) executions are left unpatched: the
monkeypatch is never installed unless the run is a dry-run. The patch is applied
to RF's classes and is not restored afterwards, so it is scoped to the process --
this repo always shells out to a fresh ``robot``, so a dry-run never leaks into a
real run. Were both ever executed in one interpreter, the real run would keep the
cache live, where ``Reload Library`` is reachable and does *not* invalidate it.

The patched bodies re-implement RF's resolution pipeline verbatim, so they are
only valid for the RF versions they were written against. ``_install`` therefore
checks the running RF version and refuses to patch outside the supported range:
a future release that reorders or inserts a filter step fails safe to uncached
rather than silently diverging on ambiguous names.
"""

import re

from robot.api import logger
from robot.running import namespace as _namespace
from robot.running.context import EXECUTION_CONTEXTS
from robot.version import VERSION as _RF_VERSION

ROBOT_LISTENER_API_VERSION = 3

# The patched resolution bodies are copied from RF's own namespace.py. The range
# below is deliberately only the versions actually diffed against upstream (7.4.x,
# byte-identical modulo the memoized scan) -- not every release believed to be
# compatible. An unverified RF therefore runs uncached (slower, never wrong) and
# logs why. To widen it, diff _get_runner_from_resource_files and
# _get_runner_from_libraries against the new release first, then bump.
_MIN_RF = (7, 4)
_MAX_RF_EXCLUSIVE = (7, 5)

_ATTEMPTED = False

# Only a plain numeric release qualifies. Matching on the numeric prefix alone
# would accept "7.4.0rc1" (its first two parts parse) while rejecting "7.4rc1"
# (its second does not) -- an arbitrary split. A pre-release or dev build is not
# a version this cache was diffed against, so require the whole string to be a
# released version and treat everything else as unsupported.
_RELEASE_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.\d+)*$")


def _rf_version_supported():
    match = _RELEASE_VERSION.fullmatch(_RF_VERSION.strip())
    if not match:  # pre-release, dev build, or unparseable
        return False
    parts = (int(match.group(1)), int(match.group(2)))
    return _MIN_RF <= parts < _MAX_RF_EXCLUSIVE


def start_suite(data, result):
    """Install the cache on the first dry-run suite; no-op for real runs."""
    global _ATTEMPTED
    if _ATTEMPTED:
        return
    ctx = EXECUTION_CONTEXTS.current
    if ctx is None or not getattr(ctx, "dry_run", False):
        return
    # Attempt exactly once, whatever the outcome: a failure must never leave a
    # half-patched state that a later retry could compound, so we do not reset
    # this flag on error. On failure the dry-run simply runs uncached.
    _ATTEMPTED = True
    try:
        _install(ctx.namespace._kw_store)
    except Exception as err:  # never let the optimization break a dry-run
        logger.warn(f"rf_dryrun_cache: not installed ({err}); running without cache.")


def _seed(store_instance):
    store_instance._dryrun_res_scan = {}
    store_instance._dryrun_lib_scan = {}


def _install(root_store):
    store = _namespace.KeywordStore
    namespace = _namespace.Namespace
    # Guard: if RF is outside the range these patched bodies were written against,
    # or its internals no longer look as expected, refuse to patch. Being slow is
    # fine; silently changing resolution semantics is not.
    if not _rf_version_supported():
        raise RuntimeError(
            f"unsupported Robot Framework {_RF_VERSION} "
            f"(cache supports >={'.'.join(map(str, _MIN_RF))},"
            f"<{'.'.join(map(str, _MAX_RF_EXCLUSIVE))})"
        )
    for owner, attr in (
        (store, "_get_runner_from_resource_files"),
        (store, "_get_runner_from_libraries"),
        (store, "_filter_based_on_search_order"),
        (store, "_prioritize_same_file_or_public"),
        (store, "_select_best_matches"),
        (store, "_filter_stdlib_handler"),
        (store, "_raise_multiple_keywords_found"),
        (namespace, "set_search_order"),
        (namespace, "_import_resource"),
        (namespace, "_import_library"),
    ):
        if not hasattr(owner, attr):
            raise AttributeError(f"{owner.__name__}.{attr} missing")

    orig_init = store.__init__

    def __init__(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        _seed(self)

    def _get_runner_from_resource_files(self, name):
        cache = self._dryrun_res_scan
        if name in cache:
            keywords = cache[name]
        else:
            keywords = [kw for res in self.resources.values() for kw in res.find_keywords(name)]
            if len(keywords) <= 1:
                cache[name] = keywords
        if not keywords:
            return None
        if len(keywords) > 1:
            keywords = self._filter_based_on_search_order(keywords)
            if len(keywords) > 1:
                keywords = self._prioritize_same_file_or_public(keywords)
                if len(keywords) > 1:
                    keywords = self._select_best_matches(keywords)
                    if len(keywords) > 1:
                        self._raise_multiple_keywords_found(keywords, name)
        return keywords[0].create_runner(name, self.languages)

    def _get_runner_from_libraries(self, name):
        cache = self._dryrun_lib_scan
        if name in cache:
            keywords = cache[name]
        else:
            keywords = [kw for lib in self.libraries.values() for kw in lib.find_keywords(name)]
            if len(keywords) <= 1:
                cache[name] = keywords
        if not keywords:
            return None
        pre_run_message = None
        if len(keywords) > 1:
            keywords = self._filter_based_on_search_order(keywords)
            if len(keywords) > 1:
                keywords = self._select_best_matches(keywords)
                if len(keywords) > 1:
                    keywords, pre_run_message = self._filter_stdlib_handler(keywords)
                    if len(keywords) > 1:
                        self._raise_multiple_keywords_found(keywords, name)
        runner = keywords[0].create_runner(name, self.languages)
        if pre_run_message:
            runner.pre_run_messages += (pre_run_message,)
        return runner

    def _clear(store_instance):
        # Both dicts are seeded together (root store before patching, every later
        # store via __init__), so either both exist or neither does. Re-seeding is
        # equivalent to clearing and needs no guard.
        _seed(store_instance)

    orig_set_search_order = namespace.set_search_order

    def set_search_order(self, new_order):
        # Defensive, and deliberately not covered by a test that would fail
        # without it: search order is consulted only by _filter_based_on_search_order,
        # which runs only for scans with >1 match -- exactly the scans that are
        # never cached. Clearing here costs nothing and keeps the invalidation set
        # complete if the caching rule is ever widened past the <=1 margin.
        _clear(self._kw_store)
        return orig_set_search_order(self, new_order)

    orig_import_resource = namespace._import_resource

    def _import_resource(self, *args, **kwargs):
        try:
            return orig_import_resource(self, *args, **kwargs)
        finally:
            _clear(self._kw_store)

    orig_import_library = namespace._import_library

    def _import_library(self, *args, **kwargs):
        try:
            return orig_import_library(self, *args, **kwargs)
        finally:
            _clear(self._kw_store)

    # Seed the already-existing root store BEFORE the patched methods go live, so
    # no patched method can ever run against a store without its cache dicts. Every
    # store created after this point is seeded by the wrapped __init__. All the
    # assignments below are plain attribute writes that cannot fail, so once we
    # reach here the patch is applied all-or-nothing.
    _seed(root_store)
    store.__init__ = __init__
    store._get_runner_from_resource_files = _get_runner_from_resource_files
    store._get_runner_from_libraries = _get_runner_from_libraries
    namespace.set_search_order = set_search_order
    namespace._import_resource = _import_resource
    namespace._import_library = _import_library
