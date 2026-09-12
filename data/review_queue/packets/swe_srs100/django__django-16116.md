# django__django-16116

Machine verdict: **valid** (gold resolved and empty patch not resolved)
Protocol: verifier_invalid.fresh_environment.execution, grade A, adjudicator machine.
Human spot check: do the execution results below support the machine verdict? Mark one: [ ] agree  [ ] disagree  [ ] cannot tell. Reason (one line):

## Execution under the official SWE-bench harness (fresh container)

| Treatment | resolved | F2P (pass, fail) | P2P (pass, fail) | F2P failures | P2P failures |
| --- | --- | --- | --- | --- | --- |
| gold patch | True | (1, 0) | (137, 0) | [] | [] |
| empty patch | False | (0, 1) | (137, 0) | ['makemigrations --check should exit with a non-zero status when'] | [] |

Expected for a valid task: gold resolved True, empty resolved False.

## FAIL_TO_PASS tests (declared, first 8)

['makemigrations --check should exit with a non-zero status when']

## Issue text (first 60 lines)

```
makemigrations --check generating migrations is inconsistent with other uses of --check
Description
	
To script a check for missing migrations but without actually intending to create the migrations, it is necessary to use both --check and --dry-run, which is inconsistent with migrate --check and optimizemigration --check, which just exit (after possibly logging a bit).
I'm suggesting that makemigrations --check should just exit without making migrations.
The choice to write the migrations anyway was not discussed AFAICT on ticket:25604 or ​https://groups.google.com/g/django-developers/c/zczdY6c9KSg/m/ZXCXQsGDDAAJ.
Noticed when reading ​PR to adjust the documentation of migrate --check. I think the current documentation is silent on this question.
```

## Test patch (first 80 lines)

```diff
diff --git a/tests/migrations/test_commands.py b/tests/migrations/test_commands.py
--- a/tests/migrations/test_commands.py
+++ b/tests/migrations/test_commands.py
@@ -2391,9 +2391,10 @@ def test_makemigrations_check(self):
         makemigrations --check should exit with a non-zero status when
         there are changes to an app requiring migrations.
         """
-        with self.temporary_migration_module():
+        with self.temporary_migration_module() as tmpdir:
             with self.assertRaises(SystemExit):
                 call_command("makemigrations", "--check", "migrations", verbosity=0)
+            self.assertFalse(os.path.exists(tmpdir))
 
         with self.temporary_migration_module(
             module="migrations.test_migrations_no_changes"
```
