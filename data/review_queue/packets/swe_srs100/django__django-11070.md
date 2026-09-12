# django__django-11070

Machine verdict: **valid** (gold resolved and empty patch not resolved)
Protocol: verifier_invalid.fresh_environment.execution, grade A, adjudicator machine.
Human spot check: do the execution results below support the machine verdict? Mark one: [ ] agree  [ ] disagree  [ ] cannot tell. Reason (one line):

## Execution under the official SWE-bench harness (fresh container)

| Treatment | resolved | F2P (pass, fail) | P2P (pass, fail) | F2P failures | P2P failures |
| --- | --- | --- | --- | --- | --- |
| gold patch | True | (10, 0) | (69, 0) | [] | [] |
| empty patch | False | (0, 10) | (69, 0) | ['test_html_autocomplete_attributes (auth_tests.test_forms.AdminPasswordChangeFormTest)', 'test_missing_passwords (auth_tests.test_forms.AdminPasswordChangeFormTest)', 'test_html_autocomplete_attributes (auth_tests.test_forms.PasswordChangeFormTest)', 'test_html_autocomplete_attributes (auth_tests.test_forms.UserCreationFormTest)', 'test_invalid_data (auth_tests.test_forms.UserCreationFormTest)'] | [] |

Expected for a valid task: gold resolved True, empty resolved False.

## FAIL_TO_PASS tests (declared, first 8)

['test_html_autocomplete_attributes (auth_tests.test_forms.AdminPasswordChangeFormTest)', 'test_missing_passwords (auth_tests.test_forms.AdminPasswordChangeFormTest)', 'test_html_autocomplete_attributes (auth_tests.test_forms.PasswordChangeFormTest)', 'test_html_autocomplete_attributes (auth_tests.test_forms.UserCreationFormTest)', 'test_invalid_data (auth_tests.test_forms.UserCreationFormTest)', 'test_html_autocomplete_attributes (auth_tests.test_forms.SetPasswordFormTest)', 'test_password_verification (auth_tests.test_forms.SetPasswordFormTest)', 'test_html_autocomplete_attributes (auth_tests.test_forms.AuthenticationFormTest)']

## Issue text (first 60 lines)

```
Add autocomplete attribute to contrib.auth fields
Description
	 
		(last modified by CHI Cheng)
	 
Add autocomplete=username/email/current-password/new-password to contrib.auth builtin forms.
Pull request: ​https://github.com/django/django/pull/9921
The most useful one is autocomplete=new-password, which prevents browsers prefill with current password, Chrome will also suggest a random strong password for users who turned on account sync.
Related docs:
​https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#autofill
​https://www.chromium.org/developers/design-documents/form-styles-that-chromium-understands
​https://developer.mozilla.org/en-US/docs/Web/Security/Securing_your_site/Turning_off_form_autocompletion#The_autocomplete_attribute_and_login_fields
```

## Test patch (first 80 lines)

```diff
diff --git a/tests/auth_tests/test_forms.py b/tests/auth_tests/test_forms.py
--- a/tests/auth_tests/test_forms.py
+++ b/tests/auth_tests/test_forms.py
@@ -265,6 +265,17 @@ def test_username_field_autocapitalize_none(self):
         form = UserCreationForm()
         self.assertEqual(form.fields['username'].widget.attrs.get('autocapitalize'), 'none')
 
+    def test_html_autocomplete_attributes(self):
+        form = UserCreationForm()
+        tests = (
+            ('username', 'username'),
+            ('password1', 'new-password'),
+            ('password2', 'new-password'),
+        )
+        for field_name, autocomplete in tests:
+            with self.subTest(field_name=field_name, autocomplete=autocomplete):
+                self.assertEqual(form.fields[field_name].widget.attrs['autocomplete'], autocomplete)
+
 
 # To verify that the login form rejects inactive users, use an authentication
 # backend that allows them.
@@ -492,6 +503,16 @@ def test_get_invalid_login_error(self):
         self.assertEqual(error.code, 'invalid_login')
         self.assertEqual(error.params, {'username': 'username'})
 
+    def test_html_autocomplete_attributes(self):
+        form = AuthenticationForm()
+        tests = (
+            ('username', 'username'),
+            ('password', 'current-password'),
+        )
+        for field_name, autocomplete in tests:
+            with self.subTest(field_name=field_name, autocomplete=autocomplete):
+                self.assertEqual(form.fields[field_name].widget.attrs['autocomplete'], autocomplete)
+
 
 class SetPasswordFormTest(TestDataMixin, TestCase):
 
@@ -572,6 +593,16 @@ def test_help_text_translation(self):
             for french_text in french_help_texts:
                 self.assertIn(french_text, html)
 
+    def test_html_autocomplete_attributes(self):
+        form = SetPasswordForm(self.u1)
+        tests = (
+            ('new_password1', 'new-password'),
+            ('new_password2', 'new-password'),
+        )
+        for field_name, autocomplete in tests:
+            with self.subTest(field_name=field_name, autocomplete=autocomplete):
+                self.assertEqual(form.fields[field_name].widget.attrs['autocomplete'], autocomplete)
+
 
 class PasswordChangeFormTest(TestDataMixin, TestCase):
 
@@ -633,6 +664,11 @@ def test_password_whitespace_not_stripped(self):
         self.assertEqual(form.cleaned_data['new_password1'], data['new_password1'])
         self.assertEqual(form.cleaned_data['new_password2'], data['new_password2'])
 
+    def test_html_autocomplete_attributes(self):
+        user = User.objects.get(username='testclient')
+        form = PasswordChangeForm(user)
+        self.assertEqual(form.fields['old_password'].widget.attrs['autocomplete'], 'current-password')
+
 
 class UserChangeFormTest(TestDataMixin, TestCase):
 
@@ -916,6 +952,10 @@ def test_custom_email_field(self):
         self.assertEqual(len(mail.outbox), 1)
         self.assertEqual(mail.outbox[0].to, [email])
 
+    def test_html_autocomplete_attributes(self):
+        form = PasswordResetForm()
+        self.assertEqual(form.fields['email'].widget.attrs['autocomplete'], 'email')
+
 
 class ReadOnlyPasswordHashTest(SimpleTestCase):
 
@@ -997,3 +1037,14 @@ def test_one_password(self):
         form2 = AdminPasswordChangeForm(user, {'password1': 'test', 'password2': ''})
```
