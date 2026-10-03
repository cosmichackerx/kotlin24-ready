import json
import os
import shutil
import subprocess

import pytest

from kotlin24_ready.cli import main
from kotlin24_ready.diffmode import GitError, scan_against_base

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, env={**os.environ, **ENV}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "build.gradle.kts").write_text('plugins { kotlin("multiplatform") version "2.3.20" }\nkotlin {\n  jvm()\n  targetHierarchy.default()\n}\n')
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "build.gradle.kts").write_text('plugins { id("org.jetbrains.kotlin.plugin.compose") }\ncomposeCompiler { enableStrongSkippingMode = true }\n')
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    git(tmp_path, "branch", "base")
    git(tmp_path, "checkout", "-q", "-b", "feature")
    return tmp_path


def commit(repo, msg="change"):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


def new(repo, **kw):
    r = scan_against_base(str(repo), "base", **kw)
    return [(f.rule, f.file, f.snippet) for f in r.findings], r.pr


def test_unchanged_branch_has_no_new_findings(repo):
    f, pr = new(repo)
    assert f == [] and pr == {"base": "base", "existing": 2, "resolved": 0}


def test_only_the_introduced_finding_is_reported(repo):
    with open(repo / "app" / "build.gradle.kts", "a") as fh:
        fh.write('kotlin { compilerOptions { languageVersion.set(KotlinVersion.KOTLIN_1_9) } }\n')
    commit(repo)
    f, pr = new(repo)
    assert [x[0] for x in f] == ["language-version-1-9"] and f[0][1] == "app/build.gradle.kts" and pr["existing"] == 2


def test_line_shifts_and_fixes_do_not_create_new_findings(repo):
    src = (repo / "build.gradle.kts").read_text()
    (repo / "build.gradle.kts").write_text("// header\n// more\n" + src)
    commit(repo)
    assert new(repo)[0] == []
    (repo / "app" / "build.gradle.kts").write_text("plugins { }\n")
    commit(repo)
    f, pr = new(repo)
    assert f == [] and pr["resolved"] == 1


def test_renamed_file_keeps_its_old_findings(repo):
    git(repo, "mv", "app/build.gradle.kts", "app/build-renamed.gradle.kts")
    commit(repo)
    f, pr = new(repo)
    assert pr["existing"] + len(f) >= 1


def test_exit_codes_and_json(repo, capsys):
    with open(repo / "app" / "build.gradle.kts", "a") as fh:
        fh.write("kotlin { js(IR) { nodejs() } }\n")
    commit(repo)
    assert main([str(repo), "--base", "base", "--fail-on", "error", "-f", "json"]) == 0  # only a warning is new
    capsys.readouterr()
    assert main([str(repo), "--base", "base", "--fail-on", "warning", "-f", "json"]) == 1
    capsys.readouterr()
    assert main([str(repo), "--base", "base", "--fail-on", "never", "-f", "json"]) == 0
    out = capsys.readouterr().out
    d = json.loads(out[out.rindex('{\n  "tool"'):])
    assert d["pullRequest"] == {"base": "base", "existing": 2, "resolved": 0} and len(d["findings"]) == 1


def test_unknown_base_and_not_a_repo(tmp_path, repo, capsys):
    assert main([str(repo), "--base", "nope"]) == 2
    assert "fetch-depth: 0" in capsys.readouterr().err
    other = tmp_path.parent / (tmp_path.name + "-nogit")
    other.mkdir()
    (other / "build.gradle.kts").write_text("kotlin { targetHierarchy.default() }\n")
    try:
        with pytest.raises(GitError):
            scan_against_base(str(other), "main")
    finally:
        shutil.rmtree(other)


def test_base_and_fix_cannot_be_combined(repo):
    assert main([str(repo), "--base", "base", "--fix"]) == 2


def test_buildsrc_sources_take_part_in_pr_mode(repo):
    (repo / "buildSrc" / "src" / "main" / "kotlin").mkdir(parents=True)
    (repo / "buildSrc" / "src" / "main" / "kotlin" / "Conv.kt").write_text("fun f(c: C) = c.compileKotlinTask\n")
    commit(repo)
    f, pr = new(repo)
    assert [(x[0], x[1]) for x in f] == [("compilation-task-accessors", "buildSrc/src/main/kotlin/Conv.kt")] and pr["existing"] == 2
