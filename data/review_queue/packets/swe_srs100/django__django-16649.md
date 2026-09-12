# django__django-16649

Machine verdict: **valid** (gold resolved and empty patch not resolved)
Protocol: verifier_invalid.fresh_environment.execution, grade A, adjudicator machine.
Human spot check: do the execution results below support the machine verdict? Mark one: [ ] agree  [ ] disagree  [ ] cannot tell. Reason (one line):

## Execution under the official SWE-bench harness (fresh container)

| Treatment | resolved | F2P (pass, fail) | P2P (pass, fail) | F2P failures | P2P failures |
| --- | --- | --- | --- | --- | --- |
| gold patch | True | (2, 0) | (52, 0) | [] | [] |
| empty patch | False | (0, 2) | (52, 0) | ['test_union_multiple_models_with_values_list_and_annotations (queries.test_qs_combinators.QuerySetSetOperationTests.test_union_multiple_models_with_values_list_and_annotations)', 'test_union_with_two_annotated_values_list (queries.test_qs_combinators.QuerySetSetOperationTests.test_union_with_two_annotated_values_list)'] | [] |

Expected for a valid task: gold resolved True, empty resolved False.

## FAIL_TO_PASS tests (declared, first 8)

['test_union_multiple_models_with_values_list_and_annotations (queries.test_qs_combinators.QuerySetSetOperationTests.test_union_multiple_models_with_values_list_and_annotations)', 'test_union_with_two_annotated_values_list (queries.test_qs_combinators.QuerySetSetOperationTests.test_union_with_two_annotated_values_list)']

## Issue text (first 60 lines)

```
Querysets: annotate() columns are forced into a certain position which may disrupt union()
Description
	
(Reporting possible issue found by a user on #django)
Using values() to force selection of certain columns in a certain order proved useful unioning querysets with union() for the aforementioned user. The positioning of columns added with annotate() is not controllable with values() and has the potential to disrupt union() unless this fact is known and the ordering done in a certain way to accommodate it.
I'm reporting this mainly for posterity but also as a highlight that perhaps this should be mentioned in the documentation. I'm sure there are reasons why the annotations are appended to the select but if someone feels that this is changeable then it would be a bonus outcome.
```

## Test patch (first 80 lines)

```diff
diff --git a/tests/postgres_tests/test_array.py b/tests/postgres_tests/test_array.py
--- a/tests/postgres_tests/test_array.py
+++ b/tests/postgres_tests/test_array.py
@@ -466,8 +466,8 @@ def test_group_by_order_by_select_index(self):
                 ],
             )
         sql = ctx[0]["sql"]
-        self.assertIn("GROUP BY 1", sql)
-        self.assertIn("ORDER BY 1", sql)
+        self.assertIn("GROUP BY 2", sql)
+        self.assertIn("ORDER BY 2", sql)
 
     def test_index(self):
         self.assertSequenceEqual(
diff --git a/tests/queries/test_qs_combinators.py b/tests/queries/test_qs_combinators.py
--- a/tests/queries/test_qs_combinators.py
+++ b/tests/queries/test_qs_combinators.py
@@ -246,7 +246,7 @@ def test_union_with_two_annotated_values_list(self):
             )
             .values_list("num", "count")
         )
-        self.assertCountEqual(qs1.union(qs2), [(1, 0), (2, 1)])
+        self.assertCountEqual(qs1.union(qs2), [(1, 0), (1, 2)])
 
     def test_union_with_extra_and_values_list(self):
         qs1 = (
@@ -368,6 +368,20 @@ def test_union_multiple_models_with_values_list_and_order_by_extra_select(self):
             [reserved_name.pk],
         )
 
+    def test_union_multiple_models_with_values_list_and_annotations(self):
+        ReservedName.objects.create(name="rn1", order=10)
+        Celebrity.objects.create(name="c1")
+        qs1 = ReservedName.objects.annotate(row_type=Value("rn")).values_list(
+            "name", "order", "row_type"
+        )
+        qs2 = Celebrity.objects.annotate(
+            row_type=Value("cb"), order=Value(-10)
+        ).values_list("name", "order", "row_type")
+        self.assertSequenceEqual(
+            qs1.union(qs2).order_by("order"),
+            [("c1", -10, "cb"), ("rn1", 10, "rn")],
+        )
+
     def test_union_in_subquery(self):
         ReservedName.objects.bulk_create(
             [
```
