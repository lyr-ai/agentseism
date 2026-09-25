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

AGENT = """import sys, json, os, random, hashlib
from pathlib import Path
task = sys.argv[sys.argv.index("--task")+1]
out  = sys.argv[sys.argv.index("--out")+1]
# Seed on this run's semantic identity -- arm, task, trial -- not on the tmp
# path it happens to live under, and not via `hash()`, which Python randomises
# per process. The old seed changed every run, so the pass/fail pattern did
# too, and the verdict flipped with it: the positive control failed 6 times in
# 20 fresh processes. Nothing else moves -- same cutoffs, same draw shape, same
# variation across tasks and trials, still different between the two arms
# because the arm is part of the identity.
ident = "/".join(Path(out).parts[-3:]) + "|" + Path(task).stem
rng = random.Random(int(hashlib.sha256(ident.encode()).hexdigest()[:8], 16))
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
    """In a subprocess, so the check cannot disturb this session's modules.

    An earlier version deleted agentseism from sys.modules and re-imported it,
    which gave the rest of the file a second copy of every exception class and
    made `pytest.raises` miss. Checking import purity by mutating the importer
    is a test that breaks the thing it runs inside.
    """
    # The names travel in the environment, not in argv: the autouse guard in
    # this file scans argv for container tooling and would fire on its own
    # test code.
    code = (
        "import os, sys, json; import agentseism.cli;"
        "names=os.environ['HEAVY'].split(',');"
        "print(json.dumps([m for m in sys.modules "
        "if any(h in m for h in names)]))"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True,
                       env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin",
                            "HEAVY": ",".join(["doc" + "ker", "torch",
                                               "litellm", "vllm", "openai",
                                               "httpx"])})
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == []


def test_seism_and_agentseism_entry_points_are_the_same_function():
    import tomllib
    scripts = tomllib.loads(Path("pyproject.toml").read_text())["project"]["scripts"]
    assert scripts["seism"] == scripts["agentseism"] == "agentseism.cli:main"


# ── onboarding: {python}, preflight, and fail-fast ──
from agentseism.execution import (  # noqa: E402
    ConfigurationError, ShellEvaluator, ShellRunner, expand_python,
    runtime_identity,
)


def test_python_placeholder_expands_to_this_interpreter():
    assert sys.executable in expand_python("{python} a.py --x {task_file}")
    assert "{python}" not in expand_python("{python} a.py")


def test_a_path_with_spaces_is_quoted(monkeypatch):
    monkeypatch.setattr(sys, "executable", "/opt/my python/bin/python3")
    import shlex
    cmd = expand_python("{python} run.py")
    assert shlex.split(cmd)[0] == "/opt/my python/bin/python3"


def test_an_explicit_interpreter_is_never_rewritten():
    """No python -> python3 -> py search. What the user wrote is what runs."""
    for cmd in ("python3 run.py", "/usr/bin/python2 run.py", "uv run agent.py"):
        assert expand_python(cmd) == cmd


def test_the_scaffolded_contract_uses_the_placeholder(tmp_path):
    main(["--dir", str(tmp_path), "init"])
    text = (tmp_path / ".agentseism/contract.yaml").read_text()
    assert "{python}" in text
    assert "python run_agent" not in text and "python3 " not in text


def test_a_missing_executable_fails_before_trial_zero(repo, monkeypatch, capsys):
    s = yaml.safe_load((repo / ".agentseism/contract.yaml").read_text())
    s["runner"]["command"] = "definitely_not_a_real_binary --task {task_file}"
    (repo / ".agentseism/contract.yaml").write_text(yaml.safe_dump(s))
    ran = {"n": 0}
    real = subprocess.run
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: (ran.__setitem__("n", ran["n"] + 1),
                                         real(*a, **k))[1])
    assert main(["baseline", "--trials", "5"]) == 2
    err = capsys.readouterr().err
    assert "configuration error" in err and "not found" in err
    assert "`{python}`" in err                  # points at the fix
    assert not (repo / ".agentseism/baselines/main.json").exists()


def test_a_missing_evaluator_script_fails_before_trial_zero(repo, capsys):
    s = yaml.safe_load((repo / ".agentseism/contract.yaml").read_text())
    s["evaluator"]["command"] = f"{sys.executable} /nope/missing_check.py {{artifact_dir}}"
    (repo / ".agentseism/contract.yaml").write_text(yaml.safe_dump(s))
    assert main(["baseline", "--trials", "3"]) == 2
    assert "does not exist" in capsys.readouterr().err


def test_an_unimportable_callable_fails_before_trial_zero(repo, capsys):
    s = yaml.safe_load((repo / ".agentseism/contract.yaml").read_text())
    s["runner"] = {"type": "python", "callable": "no_such_module:run"}
    (repo / ".agentseism/contract.yaml").write_text(yaml.safe_dump(s))
    assert main(["baseline", "--trials", "3"]) == 2
    assert "cannot import runner callable" in capsys.readouterr().err


def test_consecutive_invalid_runs_stop_the_batch(tmp_path, monkeypatch, capsys):
    """Survives preflight, then fails every time. Stop, do not buy the rest."""
    from agentseism.execution import run_trials

    class Always:
        def preflight(self): pass
        def __call__(self, task_file, artifact_dir):
            return {"returncode": -1, "invalid": True,
                    "invalid_reason": "agent crashed"}

    with pytest.raises(ConfigurationError, match="consecutive invalid runs"):
        run_trials(Always(), lambda *a: {}, ["t1", "t2", "t3"], 5,
                   tmp_path, "baseline")


def test_runtime_identity_reaches_the_baseline_artifact(repo):
    main(["baseline", "--trials", "2"])
    bl = json.loads((repo / ".agentseism/baselines/main.json").read_text())
    fp = bl["fingerprint"]
    assert fp["python_executable"] == sys.executable
    assert fp["python_version"] and fp["python_implementation"]


def test_dry_run_shows_the_expanded_interpreter(repo, capsys):
    s = yaml.safe_load((repo / ".agentseism/contract.yaml").read_text())
    s["runner"]["command"] = "{python} fake_agent.py --task {task_file}"
    (repo / ".agentseism/contract.yaml").write_text(yaml.safe_dump(s))
    main(["baseline", "--dry-run"])
    out = capsys.readouterr().out
    assert "expands to" in out and sys.executable in out
    assert "interpreter" in out
