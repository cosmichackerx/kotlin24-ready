# Contributing

    python -m venv .venv && . .venv/bin/activate
    pip install -e . pytest
    pytest -q

* A new rule needs an entry in `src/kotlin24_ready/rules.py` with the section of the Kotlin 2.4 compatibility guide it comes from, a detector in `scan.py`, and unit tests with positive and negative cases.
* Rules are checked against a real Kotlin Gradle plugin. Add the construct as a case in `tests/oracle/run_oracle.py` and run it (`python tests/oracle/run_oracle.py --kgp 2.4.20 --gradle /path/to/gradle-9.x/bin/gradle`; needs JDK 17+ and network access to Maven Central and the Gradle plugin portal). If the plugin does not fail on it, say so in the rule (`oracle=False`) and in the README.
* Fixes (`--fix`) must be safe: add the case to `tests/test_rules.py`.
* Keep the project dependency-free (standard library only) and compatible with Python 3.9.
