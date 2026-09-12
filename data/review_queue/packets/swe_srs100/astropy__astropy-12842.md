# astropy__astropy-12842

Machine verdict: **valid** (gold resolved and empty patch not resolved)
Protocol: verifier_invalid.fresh_environment.execution, grade A, adjudicator machine.
Human spot check: do the execution results below support the machine verdict? Mark one: [ ] agree  [ ] disagree  [ ] cannot tell. Reason (one line):

## Execution under the official SWE-bench harness (fresh container)

| Treatment | resolved | F2P (pass, fail) | P2P (pass, fail) | F2P failures | P2P failures |
| --- | --- | --- | --- | --- | --- |
| gold patch | True | (3, 0) | (417, 0) | [] | [] |
| empty patch | False | (0, 3) | (417, 0) | ['astropy/time/tests/test_basic.py::test_write_every_format_to_ecsv[datetime]', 'astropy/time/tests/test_basic.py::test_write_every_format_to_ecsv[datetime64]', 'astropy/time/tests/test_basic.py::test_write_every_format_to_ecsv[byear]'] | [] |

Expected for a valid task: gold resolved True, empty resolved False.

## FAIL_TO_PASS tests (declared, first 8)

['astropy/time/tests/test_basic.py::test_write_every_format_to_ecsv[datetime]', 'astropy/time/tests/test_basic.py::test_write_every_format_to_ecsv[datetime64]', 'astropy/time/tests/test_basic.py::test_write_every_format_to_ecsv[byear]']

## Issue text (first 60 lines)

```
No longer able to read BinnedTimeSeries with datetime column saved as ECSV after upgrading from 4.2.1 -> 5.0+
<!-- This comments are hidden when you submit the issue,
so you do not need to remove them! -->

<!-- Please be sure to check out our contributing guidelines,
https://github.com/astropy/astropy/blob/main/CONTRIBUTING.md .
Please be sure to check out our code of conduct,
https://github.com/astropy/astropy/blob/main/CODE_OF_CONDUCT.md . -->

<!-- Please have a search on our GitHub repository to see if a similar
issue has already been posted.
If a similar issue is closed, have a quick look to see if you are satisfied
by the resolution.
If not please go ahead and open an issue! -->

<!-- Please check that the development version still produces the same bug.
You can install development version with
pip install git+https://github.com/astropy/astropy
command. -->

### Description
<!-- Provide a general description of the bug. -->
Hi, [This commit](https://github.com/astropy/astropy/commit/e807dbff9a5c72bdc42d18c7d6712aae69a0bddc) merged in PR #11569 breaks my ability to read an ECSV file created using Astropy v 4.2.1, BinnedTimeSeries class's write method, which has a datetime64 column. Downgrading astropy back to 4.2.1 fixes the issue because the strict type checking in line 177 of ecsv.py is not there.

Is there a reason why this strict type checking was added to ECSV? Is there a way to preserve reading and writing of ECSV files created with BinnedTimeSeries across versions? I am happy to make a PR on this if the strict type checking is allowed to be scaled back or we can add datetime64 as an allowed type. 

### Expected behavior
<!-- What did you expect to happen. -->

The file is read into a `BinnedTimeSeries` object from ecsv file without error.

### Actual behavior
<!-- What actually happened. -->
<!-- Was the output confusing or poorly described? -->

ValueError is produced and the file is not read because ECSV.py does not accept the datetime64 column.
`ValueError: datatype 'datetime64' of column 'time_bin_start' is not in allowed values ('bool', 'int8', 'int16', 'int32', 'int64', 'uint8', 'uint16', 'uint32', 'uint64', 'float16', 'float32', 'float64', 'float128', 'string')`

### Steps to Reproduce
<!-- Ideally a code example could be provided so we can run it ourselves. -->
<!-- If you are pasting code, use triple backticks (```) around
your code snippet. -->
<!-- If necessary, sanitize your screen output to be pasted so you do not
reveal secrets like tokens and passwords. -->

The file is read using:    
`BinnedTimeSeries.read('<file_path>', format='ascii.ecsv')`
which gives a long error. 


The file in question is a binned time series created by  `astropy.timeseries.aggregate_downsample`. which itself is a binned version of an `astropy.timeseries.TimeSeries` instance with some TESS data. (loaded via TimeSeries.from_pandas(Tess.set_index('datetime')). I.e., it has a datetime64 index.  The file was written using the classes own .write method in Astropy V4.2.1 from an instance of said class:   
`myBinnedTimeSeries.write('<file_path>',format='ascii.ecsv',overwrite=True)`

I'll attach a concatenated version of the file (as it contains private data). However, the relevant part from the header is on line 4:

```
# %ECSV 0.9
# ---
# datatype:
# - {name: time_bin_start, datatype: datetime64}
```

## Test patch (first 80 lines)

```diff
diff --git a/astropy/io/ascii/tests/test_ecsv.py b/astropy/io/ascii/tests/test_ecsv.py
--- a/astropy/io/ascii/tests/test_ecsv.py
+++ b/astropy/io/ascii/tests/test_ecsv.py
@@ -822,13 +822,13 @@ def _make_expected_values(cols):
      'name': '2-d regular array',
      'subtype': 'float16[2,2]'}]
 
-cols['scalar object'] = np.array([{'a': 1}, {'b':2}], dtype=object)
+cols['scalar object'] = np.array([{'a': 1}, {'b': 2}], dtype=object)
 exps['scalar object'] = [
     {'datatype': 'string', 'name': 'scalar object', 'subtype': 'json'}]
 
 cols['1-d object'] = np.array(
-    [[{'a': 1}, {'b':2}],
-     [{'a': 1}, {'b':2}]], dtype=object)
+    [[{'a': 1}, {'b': 2}],
+     [{'a': 1}, {'b': 2}]], dtype=object)
 exps['1-d object'] = [
     {'datatype': 'string',
      'name': '1-d object',
@@ -966,7 +966,7 @@ def test_masked_vals_in_array_subtypes():
     assert t2.colnames == t.colnames
     for name in t2.colnames:
         assert t2[name].dtype == t[name].dtype
-        assert type(t2[name]) is type(t[name])
+        assert type(t2[name]) is type(t[name])  # noqa
         for val1, val2 in zip(t2[name], t[name]):
             if isinstance(val1, np.ndarray):
                 assert val1.dtype == val2.dtype
diff --git a/astropy/time/tests/test_basic.py b/astropy/time/tests/test_basic.py
--- a/astropy/time/tests/test_basic.py
+++ b/astropy/time/tests/test_basic.py
@@ -6,6 +6,7 @@
 import datetime
 from copy import deepcopy
 from decimal import Decimal, localcontext
+from io import StringIO
 
 import numpy as np
 import pytest
@@ -20,7 +21,7 @@
 from astropy.coordinates import EarthLocation
 from astropy import units as u
 from astropy.table import Column, Table
-from astropy.utils.compat.optional_deps import HAS_PYTZ  # noqa
+from astropy.utils.compat.optional_deps import HAS_PYTZ, HAS_H5PY  # noqa
 
 
 allclose_jd = functools.partial(np.allclose, rtol=np.finfo(float).eps, atol=0)
@@ -2221,6 +2222,66 @@ def test_ymdhms_output():
     assert t.ymdhms.year == 2015
 
 
+@pytest.mark.parametrize('fmt', TIME_FORMATS)
+def test_write_every_format_to_ecsv(fmt):
+    """Test special-case serialization of certain Time formats"""
+    t = Table()
+    # Use a time that tests the default serialization of the time format
+    tm = (Time('2020-01-01')
+          + [[1, 1 / 7],
+             [3, 4.5]] * u.s)
+    tm.format = fmt
+    t['a'] = tm
+    out = StringIO()
+    t.write(out, format='ascii.ecsv')
+    t2 = Table.read(out.getvalue(), format='ascii.ecsv')
+    assert t['a'].format == t2['a'].format
+    # Some loss of precision in the serialization
+    assert not np.all(t['a'] == t2['a'])
+    # But no loss in the format representation
+    assert np.all(t['a'].value == t2['a'].value)
+
+
+@pytest.mark.parametrize('fmt', TIME_FORMATS)
+def test_write_every_format_to_fits(fmt, tmp_path):
+    """Test special-case serialization of certain Time formats"""
+    t = Table()
+    # Use a time that tests the default serialization of the time format
+    tm = (Time('2020-01-01')
+          + [[1, 1 / 7],
```
