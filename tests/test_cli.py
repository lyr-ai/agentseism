"""The `seism` CLI, end to end with fake runners.

Zero model calls, zero Docker, zero network. An autouse fixture fails any test
that reaches for a container.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from agentseism.cli import main

AGENT = """import sys, json, os, random
task = sys.argv[sys.argv.index("--task")+1]
out  = sys.argv[sys.argv.index("--out")+1]
rng = random.Random(hash((task, out)) & 0xffff)
ok = rng.random() > (0.55 if os.environ.get("DEGRADED") == "1" else 0.15)
json.dump({"success": int(ok), "cost": rng.uniform(0.3, 0.6)},
          open(os.path.join(out, "result.json"), "w"))
"""
EVAL = """import sys, json, os
print(json.dumps(json.load(open(os.path.join(sys.argv[1], "result.json")))))
"""
CONTRACT = """
runner:
  type: shell
  command: "{py} {agent} --task {{task_file}} --out {{artifact_dir}}"
evaluator:
  command: "{py} {ev} {{artifact_dir}}"
features:
  task_success:     {{gate: true,    regression_threshold: 0.10}}
  cost_per_success: {{gate: warning, regression_threshold: 0.25}}
"""


@pytest.fixture(autouse=True)
def _no_docker(monkeypatch):
    real = subprocess.run

    def guard(cmd, *a, **kw):
        argv = cmd if isinstance(cmd, (list, tuple)) else [str(cmd)]
        if any("docker" in str(x) for x in argv):
            raise AssertionError(f"a test invoked Docker: {argv}")
        return real(cmd, *a, **kw)

    monkeypatch.setattr(subprocess, "run", guard)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for k in ("AGENTSEISM_MODEL_REVISION", "AGENTSEISM_SERVING_RUNTIME",
              "AGENTSEISM_PROMPT_VERSION", "AGENTSEISM_SCAFFOLD_VERSION",
              "DEGRADED"):
        monkeypatch.delenv(k, raising=False)
    (tmp_path / "fake_agent.py").write_text(AGENT)
    (tmp_path / "check_result.py").write_text(EVAL)
    assert main(["--dir", str(tmp_path), "init"]) == 0
    ntasks = 6
    for i in range(ntasks):
        (tmp_path / "tasks").mkdir(exist_ok=True)
        (tmp_path / f"tasks/t{i}.json").write_text('{"id": "t%d"}' % i)
    (tmp_path / ".agentseism/contract.yaml").write_text(CONTRACT.format(
        py=sys.executable, agent=tmp_path / "fake_agent.py",
        ev=tmp_path / "check_result.py"))
    (tmp_path / ".agentseism/tasks.yaml").write_text(
        yaml.safe_dump([f"tasks/t{i}.json" for i in range(ntasks)]))
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ── 1-3. init ──
def test_init_creates_the_scaffold(tmp_path):
    assert main(["--dir", str(tmp_path), "init"]) == 0
    for rel in (".agentseism/contract.yaml", ".agentseism/tasks.yaml",
                ".agentseism/baselines", ".agentseism/runs",
                "tasks/example_task.json", ".gitignore"):
        assert (tmp_path / rel).exists(), rel


def test_init_never_overwrites(tmp_path):
    main(["--dir", str(tmp_path), "init"])
    p = tmp_path / ".agentseism/contract.yaml"
    p.write_text("# mine\n")
    gi_before = (tmp_path / ".gitignore").read_text()
    main(["--dir", str(tmp_path), "init"])
    assert p.read_text() == "# mine\n"
    assert (tmp_path / ".gitignore").read_text() == gi_before


def test_the_scaffolded_contract_resolves(tmp_path):
    from agentseism.resolve import resolve_and_validate
    main(["--dir", str(tmp_path), "init"])
    surface = yaml.safe_load((tmp_path / ".agentseism/contract.yaml").read_text())
    c, _, _ = resolve_and_validate(surface)
    assert "task_success" in c.gating


# ── 4-5. runners ──
def test_shell_runner_produces_scored_runs(repo):
    assert main(["baseline", "--trials", "2"]) == 0
    bl = json.loads((repo / ".agentseism/baselines/main.json").read_text())
    assert len(bl["results"]) == 12
    assert all(not r["invalid"] for r in bl["results"])


def test_python_callable_runner(repo, monkeypatch):
    mod = repo / "mypkg.py"
    mod.write_text("import json, os\n"
                   "def run(task_file, artifact_dir):\n"
                   "    json.dump({'success': 1, 'cost': 0.4},"
                   " open(os.path.join(artifact_dir, 'result.json'), 'w'))\n"
                   "    return {}\n")
    monkeypatch.syspath_prepend(str(repo))
    s = yaml.safe_load((repo / ".agentseism/contract.yaml").read_text())
    s["runner"] = {"type": "python", "callable": "mypkg:run"}
    (repo / ".agentseism/contract.yaml").write_text(yaml.safe_dump(s))
    assert main(["baseline", "--trials", "1"]) == 0
    bl = json.loads((repo / ".agentseism/baselines/main.json").read_text())
    assert all(r["outcome"]["success"] == 1 for r in bl["results"])


# ── 6-7. baseline freezing ──
def test_baseline_freezes_everything_the_report_needs(repo):
    main(["baseline", "--trials", "2"])
    bl = json.loads((repo / ".agentseism/baselines/main.json").read_text())
    for k in ("tasks", "trials_per_task", "fingerprint", "runner", "evaluator",
              "contract_sha256", "effective_contract", "surface_contract",
              "field_sources", "started", "finished", "results"):
        assert k in bl, k
    d = (repo / ".agentseism/baselines/main.json.sha256").read_text().split()[0]
    import hashlib
    assert hashlib.sha256(
        (repo / ".agentseism/baselines/main.json").read_bytes()).hexdigest() == d


def test_an_interrupted_baseline_leaves_no_valid_artifact(repo, monkeypatch):
    import agentseism.cli as cli
    monkeypatch.setattr(cli, "run_trials",
                        lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt))
    with pytest.raises(KeyboardInterrupt):
        main(["baseline", "--trials", "2"])
    assert not (repo / ".agentseism/baselines/main.json").exists()


def test_baseline_produces_no_verdict(repo, capsys):
    main(["baseline", "--trials", "2"])
    out = capsys.readouterr().out
    assert "No verdict is produced at baseline time." in out
    for v in ("REGRESSION", "PASS", "INCOMPARABLE"):
        assert f"AgentSeism: {v}" not in out


# ── 8. comparability before any candidate call ──
def test_fingerprint_mismatch_runs_zero_candidate_trials(repo, monkeypatch, capsys):
    main(["baseline", "--trials", "2"])
    called = {"n": 0}
    import agentseism.cli as cli
    real = cli.run_trials
    monkeypatch.setattr(cli, "run_trials",
                        lambda *a, **k: (called.__setitem__("n", called["n"] + 1),
                                         real(*a, **k))[1])
    monkeypatch.setenv("AGENTSEISM_MODEL_REVISION", "something-else")
    main(["check", "--trials", "2"])
    assert called["n"] == 0
    out = capsys.readouterr().out
    assert "INCOMPARABLE" in out and "Trials run: **0**" in out


# ── 9-11. the three measured verdicts, from real runs ──
def test_pass_when_nothing_changed(repo, capsys):
    main(["baseline", "--trials", "3"])
    main(["check", "--trials", "3"])
    assert "AgentSeism: PASS" in capsys.readouterr().out


def test_regression_when_the_agent_degrades(repo, monkeypatch, capsys):
    main(["baseline", "--trials", "5"])
    monkeypatch.setenv("DEGRADED", "1")
    assert main(["check", "--trials", "5"]) == 1
    out = capsys.readouterr().out
    assert "AgentSeism: REGRESSION" in out and "do not merge" in out


def test_insufficient_evidence_when_scenarios_are_too_few(repo, capsys):
    (repo / ".agentseism/tasks.yaml").write_text(
        yaml.safe_dump([f"tasks/t{i}.json" for i in range(3)]))
    main(["baseline", "--trials", "3"])
    main(["check", "--trials", "3"])
    out = capsys.readouterr().out
    assert "INSUFFICIENT EVIDENCE" in out and "not a pass" in out


# ── 12-14. authority and boundaries ──
def test_a_warning_feature_never_produces_a_regression(repo, capsys):
    main(["baseline", "--trials", "3"])
    main(["check", "--trials", "3"])
    out = capsys.readouterr().out
    assert "AgentSeism: REGRESSION" not in out


def test_feasibility_mode_has_no_release_authority(repo, capsys):
    s = yaml.safe_load((repo / ".agentseism/contract.yaml").read_text())
    s["study_mode"] = "feasibility"
    (repo / ".agentseism/contract.yaml").write_text(yaml.safe_dump(s))
    main(["baseline", "--trials", "3"])
    main(["check", "--trials", "3"])
    assert "descriptive only" in capsys.readouterr().out


def test_diagnose_makes_no_model_calls(capsys):
    assert main(["diagnose"]) == 0
    assert "no model calls by design" in capsys.readouterr().out


# ── 15-16. artifacts and dry-run ──
def test_report_artifacts_are_written_with_digests(repo):
    main(["baseline", "--trials", "3"])
    main(["check", "--trials", "3"])
    for name in ("last-report.md", "last-report.json"):
        f = repo / ".agentseism/runs" / name
        assert f.exists() and Path(str(f) + ".sha256").exists()


@pytest.mark.parametrize("cmd", ["baseline", "check"])
def test_dry_run_writes_nothing_and_runs_nothing(repo, cmd, monkeypatch, capsys):
    import agentseism.cli as cli
    monkeypatch.setattr(cli, "run_trials",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("dry run executed the runner")))
    before = sorted(p.name for p in (repo / ".agentseism/runs").iterdir())
    assert main([cmd, "--dry-run"]) == 0
    assert sorted(p.name for p in (repo / ".agentseism/runs").iterdir()) == before
    out = capsys.readouterr().out
    assert "nothing is executed or written" in out
    assert "it will not be invented" in out          # no fabricated dollar cost


# ── 17-18. import purity and the alias ──
def test_importing_the_cli_touches_nothing():
    import importlib
    import sys as _s
    for m in [m for m in list(_s.modules) if m.startswith("agentseism")]:
        del _s.modules[m]
    before = {m for m in _s.modules if any(h in m for h in
                                           ("docker", "torch", "litellm", "vllm"))}
    importlib.import_module("agentseism.cli")
    after = {m for m in _s.modules if any(h in m for h in
                                          ("docker", "torch", "litellm", "vllm"))}
    assert after == before


def test_seism_and_agentseism_entry_points_are_the_same_function():
    import tomllib
    scripts = tomllib.loads(Path("pyproject.toml").read_text())["project"]["scripts"]
    assert scripts["seism"] == scripts["agentseism"] == "agentseism.cli:main"
