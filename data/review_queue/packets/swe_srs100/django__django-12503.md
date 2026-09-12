# django__django-12503

Machine verdict: **INVALID** (reference fails own verifier)
Protocol: verifier_invalid.fresh_environment.execution, grade A, adjudicator machine.
Human spot check: do the execution results below support the machine verdict? Mark one: [ ] agree  [ ] disagree  [ ] cannot tell. Reason (one line):

## Execution under the official SWE-bench harness (fresh container)

| Treatment | resolved | F2P (pass, fail) | P2P (pass, fail) | F2P failures | P2P failures |
| --- | --- | --- | --- | --- | --- |
| gold patch | False | (0, 1) | (48, 0) | ['test_no_option (i18n.test_extraction.BasicExtractorTests)'] | [] |
| empty patch | False | (0, 1) | (48, 0) | ['test_no_option (i18n.test_extraction.BasicExtractorTests)'] | [] |

Expected for a valid task: gold resolved True, empty resolved False.

## FAIL_TO_PASS tests (declared, first 8)

['test_no_option (i18n.test_extraction.BasicExtractorTests)']

## Issue text (first 60 lines)

```
makemessages doesn't provide feedback when no locale is specified
Description
	 
		(last modified by Cristóbal Mackenzie)
	 
makemessages requires that one of three flags be passed to specify locales for message building: --locale to explicitly specify locales, --exclude to specify locales to exclude, or --all to build message files for all locales.
When non of these flags are present, the command doesn't show any errors for the user. According to the source code, it should raise CommandError, but that never happens because of a bug in an if statement that checks if a locale has been specified.
I've already fixed this in my fork and have submitted a small PR.
​https://github.com/django/django/pull/12503
Please point out if there are any other necessary steps to move this forward. Thanks!
```

## Test patch (first 80 lines)

```diff
diff --git a/tests/i18n/test_extraction.py b/tests/i18n/test_extraction.py
--- a/tests/i18n/test_extraction.py
+++ b/tests/i18n/test_extraction.py
@@ -142,6 +142,16 @@ def test_use_i18n_false(self):
             self.assertIn('#. Translators: One-line translator comment #1', po_contents)
             self.assertIn('msgctxt "Special trans context #1"', po_contents)
 
+    def test_no_option(self):
+        # One of either the --locale, --exclude, or --all options is required.
+        msg = "Type 'manage.py help makemessages' for usage information."
+        with mock.patch(
+            'django.core.management.commands.makemessages.sys.argv',
+            ['manage.py', 'makemessages'],
+        ):
+            with self.assertRaisesRegex(CommandError, msg):
+                management.call_command('makemessages')
+
     def test_comments_extractor(self):
         management.call_command('makemessages', locale=[LOCALE], verbosity=0)
         self.assertTrue(os.path.exists(self.PO_FILE))
```
