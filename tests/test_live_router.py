"""Opt-in integration test against the real llama.cpp routers (MLC-15).

**Off by default.** The whole module is skipped unless ``HOMEBENCH_LIVE=1``,
so CI (which runs a bare ``pytest -q``) never touches a live service. Run it
deliberately:

    HOMEBENCH_LIVE=1 .venv/bin/python -m pytest -q tests/test_live_router.py

It unloads and loads models on hosts that also serve Open WebUI through
Traefik, so it restores the initial set of resident models in a ``finally``
block whatever happens. It never starts, stops or restarts a container
(AD-001), and it never prints the API key.
"""

import os

import pytest

from homebench.lifecycle.manager import ModelLifecycleManager
from homebench.lifecycle.models import LoadParams
from homebench.lifecycle.router import LlamaRouterClient
from homebench.providers import LlamaCppProvider

pytestmark = pytest.mark.skipif(
    os.environ.get("HOMEBENCH_LIVE") != "1",
    reason="live router test — set HOMEBENCH_LIVE=1 to run it; never in CI",
)

#: The two backends over the same GPU. Overridable for another machine.
HOSTS = [
    ("vulkan", os.environ.get("HOMEBENCH_LIVE_VULKAN", "http://127.0.0.1:8080")),
    ("rocm", os.environ.get("HOMEBENCH_LIVE_ROCM", "http://127.0.0.1:8081")),
]

#: Where the deployment keeps the key. Read, never printed.
KEY_FILE = os.path.expanduser("~/llm-server/llama/api-key.txt")

LOAD_TIMEOUT = 300.0


def _api_key():
    key = os.environ.get("LLAMACPP_API_KEY")
    if key:
        return key
    try:
        with open(KEY_FILE, "r", encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def _client(host):
    return LlamaRouterClient(host=host, api_key=_api_key())


def _model_path(state):
    """The ``-m <path>`` the router resolved for this model, if any."""
    args = list(state.args)
    for flag in ("-m", "--model"):
        if flag in args:
            i = args.index(flag)
            if i + 1 < len(args):
                return args[i + 1]
    return None


def _smallest_model(states):
    """The model with the smallest file on disk, so the test stays quick."""
    sized = []
    for state in states:
        path = _model_path(state)
        if path and os.path.isfile(path):
            sized.append((os.path.getsize(path), state))
    if not sized:
        pytest.skip(
            "cannot size any model file from this machine — run the live test "
            "where the router's model directory is readable"
        )
    return min(sized, key=lambda pair: pair[0])[1]


def _loaded_ids(client):
    return sorted(m.id for m in client.loaded_models())


def _restore(client, initial_ids):
    """Put the host back the way it was found, best-effort."""
    problems = []
    for model_id in _loaded_ids(client):
        if model_id not in initial_ids:
            try:
                client.unload(model_id)
            except Exception as exc:                      # noqa: BLE001
                problems.append("unload %s: %s" % (model_id, exc))
    for model_id in initial_ids:
        if model_id not in _loaded_ids(client):
            try:
                client.load(model_id)
                client.wait_until_loaded(model_id, timeout=LOAD_TIMEOUT)
            except Exception as exc:                      # noqa: BLE001
                problems.append("reload %s: %s" % (model_id, exc))
    return problems


# =====================================================================
# both hosts must be the same build or the comparison is meaningless
# =====================================================================
def test_both_hosts_run_the_same_build():
    builds = {}
    for label, host in HOSTS:
        info = _client(host).props()
        assert info.role == "router", f"{label} at {host} is not a router"
        builds[label] = info.build_info

    assert len(set(builds.values())) == 1, (
        "the two hosts run different llama.cpp builds: "
        + " · ".join(f"{label}={build}" for label, build in builds.items())
        + ". Comparing Vulkan against ROCm on divergent builds measures the "
        "build as much as the backend — rebuild both before trusting the "
        "numbers (design.md, Risks & Concerns)."
    )


# =====================================================================
# the full cycle, on each host
# =====================================================================
@pytest.mark.parametrize("label, host", HOSTS, ids=[h[0] for h in HOSTS])
def test_full_lifecycle_cycle(label, host):
    client = _client(host)
    initial = client.list_models()
    initial_ids = _loaded_ids(client)
    target = _smallest_model(initial)

    try:
        if target.id in initial_ids:
            client.unload(target.id)
        assert target.id not in _loaded_ids(client)

        client.load(target.id)
        client.wait_until_loaded(target.id, timeout=LOAD_TIMEOUT)
        assert target.id in _loaded_ids(client)

        provider = LlamaCppProvider(host=host, api_key=_api_key())
        result = provider.generate(target.id, "Reply with the single word: ok",
                                   max_tokens=8, timeout=120.0)
        assert result.text.strip(), f"{label}: no text generated by {target.id}"
        assert result.speed.output_tokens > 0

        provider.unload(target.id)
        assert provider.last_unload_error is None
        assert target.id not in _loaded_ids(client)
    finally:
        problems = _restore(client, initial_ids)

    assert not problems, f"{label}: could not restore initial state: {problems}"
    assert _loaded_ids(client) == initial_ids


# =====================================================================
# the manager's guarantee, live: only the target stays resident
# =====================================================================
@pytest.mark.parametrize("label, host", HOSTS, ids=[h[0] for h in HOSTS])
def test_ensure_only_leaves_just_the_target_resident(label, host):
    client = _client(host)
    initial_ids = _loaded_ids(client)
    target = _smallest_model(client.list_models())

    try:
        outcome = ModelLifecycleManager(client).ensure_only(
            target.id, LoadParams(), lambda plan: True
        )
        assert outcome.aborted is False
        assert _loaded_ids(client) == [target.id]
        assert outcome.effective_args, "the router reported no resolved argv"
    finally:
        problems = _restore(client, initial_ids)

    assert not problems, f"{label}: could not restore initial state: {problems}"
