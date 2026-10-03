import importlib.util
import json
import os

HERE = os.path.dirname(__file__)
spec = importlib.util.spec_from_file_location("watch", os.path.join(HERE, "..", "scripts", "watch", "watch_kotlin_docs.py"))
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)

PAGE = open(os.path.join(HERE, "fixtures", "guide", "24.html"), encoding="utf-8").read()
RULES = "targetHierarchy compileKotlinTask"
ANCHOR = "drop-support-for-language-version-1-9-and-the-k1-compiler"


def test_parse_sections_and_code_spans():
    s = watch.parse(PAGE)
    assert list(s) == [ANCHOR, "remove-deprecated-task-compilation-and-dsl-apis-from-the-kotlin-gradle-plugin", "a-new-section"]
    assert "Brand.newThing" in s["remove-deprecated-task-compilation-and-dsl-apis-from-the-kotlin-gradle-plugin"]["code"]


def test_api_filter():
    assert watch.is_api("KotlinCompilation.compileKotlinTask") and watch.is_api("languageSettings") and watch.is_api("KotlinNativeLink")
    assert not watch.is_api("-Xannotation-default-target=first-only") and not watch.is_api("json") and not watch.is_api("a b")


def test_only_gradle_component_sections_are_checked():
    names = watch.api_names(watch.parse(PAGE))
    assert list(names) == ["remove-deprecated-task-compilation-and-dsl-apis-from-the-kotlin-gradle-plugin"]
    assert "Brand.newThing" in next(iter(names.values()))


def test_analyse_reports_new_api_and_new_section():
    known = {"24:" + ANCHOR}
    res = watch.analyse({"24": PAGE}, known, set(), RULES, [ANCHOR])
    assert res["uncovered_apis"] == [("remove-deprecated-task-compilation-and-dsl-apis-from-the-kotlin-gradle-plugin", "Brand.newThing")]
    assert [s[1] for s in res["new_sections"]] == ["remove-deprecated-task-compilation-and-dsl-apis-from-the-kotlin-gradle-plugin", "a-new-section"]
    assert res["new_pages"] == [] and res["stale_anchors"] == [] and watch.has_news(res)


def test_triaged_and_known_silence_everything():
    ids = {"24:" + s for s in watch.parse(PAGE)}
    res = watch.analyse({"24": PAGE}, ids, {"Brand.newThing"}, RULES, [ANCHOR])
    assert not watch.has_news(res)


def test_new_guide_and_stale_anchor():
    res = watch.analyse({"24": PAGE, "25": PAGE}, set(), set(), RULES, ["gone-anchor"])
    assert res["new_pages"] == ["25"] and res["stale_anchors"] == ["gone-anchor"]


def test_issue_key_is_stable_and_changes_with_content():
    a = watch.analyse({"24": PAGE}, set(), set(), RULES, [])
    t1, b1 = watch.render_issue(a)
    t2, _ = watch.render_issue(watch.analyse({"24": PAGE}, set(), set(), RULES, []))
    t3, _ = watch.render_issue(watch.analyse({"24": PAGE}, set(), {"Brand.newThing"}, RULES, []))
    assert t1 == t2 and t1 != t3 and "kotlin24-ready:watch:" in b1


def test_main_with_pages_dir_and_exit_codes(tmp_path, capsys):
    d = tmp_path / "pages"
    d.mkdir()
    (d / "24.html").write_text(PAGE, encoding="utf-8")
    out = tmp_path / "o.json"
    rc = watch.main(["--pages-dir", str(d), "--known", os.devnull, "--triaged", os.devnull, "--out", str(out)])
    assert rc == 3 and json.load(open(out))["title"].startswith("Kotlin compatibility guide watch")
    (d / "24.html").write_text("<html></html>", encoding="utf-8")
    assert watch.main(["--pages-dir", str(d)]) == 2


def test_the_checked_in_baseline_covers_the_live_rule_anchors():
    anchors = watch.rule_anchors()
    assert anchors and all(a for a in anchors)
