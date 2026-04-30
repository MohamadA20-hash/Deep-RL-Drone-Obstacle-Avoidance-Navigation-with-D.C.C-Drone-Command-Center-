import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/auth/auth_controller.dart';
import '../../ui/theme.dart';
import 'widgets/auth_scaffold.dart';
import 'widgets/auth_widgets.dart';

class RegisterPage extends ConsumerStatefulWidget {
  const RegisterPage({super.key});

  @override
  ConsumerState<RegisterPage> createState() => _RegisterPageState();
}

class _RegisterPageState extends ConsumerState<RegisterPage> {
  final _formKey = GlobalKey<FormState>();
  final _user = TextEditingController();
  final _email = TextEditingController();
  final _pass = TextEditingController();
  final _confirm = TextEditingController();

  final _userFocus = FocusNode();
  final _emailFocus = FocusNode();
  final _passFocus = FocusNode();
  final _confirmFocus = FocusNode();

  bool _busy = false;

  @override
  void initState() {
    super.initState();
    // Re-validate confirm when password changes so the mismatch hint disappears
    // as soon as the user fixes it.
    _pass.addListener(() {
      if (_confirm.text.isNotEmpty) _formKey.currentState?.validate();
    });
  }

  @override
  void dispose() {
    _user.dispose();
    _email.dispose();
    _pass.dispose();
    _confirm.dispose();
    _userFocus.dispose();
    _emailFocus.dispose();
    _passFocus.dispose();
    _confirmFocus.dispose();
    super.dispose();
  }

  String? _validatePassword(String? v) {
    if (v == null || v.isEmpty) return 'Required';
    if (v.length < 8) return 'Min 8 characters';
    if (!RegExp(r'[A-Z]').hasMatch(v)) return 'Must include uppercase';
    if (!RegExp(r'[a-z]').hasMatch(v)) return 'Must include lowercase';
    if (!RegExp(r'\d').hasMatch(v)) return 'Must include a digit';
    if (!RegExp(r'[!@#\$%^&*(),.?":{}|<>_\-+=\[\]/\\;`~]').hasMatch(v)) {
      return 'Must include a special character';
    }
    return null;
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!_formKey.currentState!.validate() || _busy) return;
    setState(() => _busy = true);
    final ok = await ref.read(authControllerProvider.notifier).register(
          username: _user.text.trim(),
          password: _pass.text,
          email: _email.text.trim(),
        );
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) context.go('/dashboard');
  }

  @override
  Widget build(BuildContext context) {
    final error = ref.watch(authControllerProvider).error;
    return AuthScaffold(
      title: 'REQUEST  ACCESS',
      subtitle: 'REGISTER A NEW OPERATOR PROFILE',
      child: AutofillGroup(
        child: Form(
          key: _formKey,
          autovalidateMode: AutovalidateMode.onUserInteraction,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              AuthField(
                label: 'USERNAME',
                controller: _user,
                focusNode: _userFocus,
                autofocus: true,
                prefixIcon: Icons.person_outline,
                autofillHints: const [AutofillHints.newUsername],
                textInputAction: TextInputAction.next,
                inputFormatters: [
                  FilteringTextInputFormatter.deny(RegExp(r'\s')),
                  LengthLimitingTextInputFormatter(50),
                ],
                validator: (v) {
                  if (v == null || v.trim().isEmpty) return 'Required';
                  if (v.trim().length < 3) return 'Min 3 characters';
                  return null;
                },
                onSubmitted: (_) => _emailFocus.requestFocus(),
              ),
              const SizedBox(height: 16),
              AuthField(
                label: 'EMAIL',
                controller: _email,
                focusNode: _emailFocus,
                prefixIcon: Icons.alternate_email,
                keyboardType: TextInputType.emailAddress,
                autofillHints: const [AutofillHints.email],
                textInputAction: TextInputAction.next,
                validator: (v) {
                  if (v == null || v.trim().isEmpty) return 'Required';
                  if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
                      .hasMatch(v.trim())) {
                    return 'Invalid email';
                  }
                  return null;
                },
                onSubmitted: (_) => _passFocus.requestFocus(),
              ),
              const SizedBox(height: 16),
              AuthField(
                label: 'PASSWORD',
                controller: _pass,
                focusNode: _passFocus,
                obscure: true,
                prefixIcon: Icons.lock_outline,
                autofillHints: const [AutofillHints.newPassword],
                textInputAction: TextInputAction.next,
                validator: _validatePassword,
                onSubmitted: (_) => _confirmFocus.requestFocus(),
              ),
              const SizedBox(height: 16),
              AuthField(
                label: 'CONFIRM PASSWORD',
                controller: _confirm,
                focusNode: _confirmFocus,
                obscure: true,
                prefixIcon: Icons.lock_outline,
                textInputAction: TextInputAction.done,
                validator: (v) =>
                    v != _pass.text ? 'Passwords do not match' : null,
                onSubmitted: (_) => _submit(),
              ),
              const SizedBox(height: 22),
              if (error != null)
                AuthErrorBanner(
                  message: error.message,
                  statusCode: error.statusCode,
                  details: error.details,
                ),
              if (error != null) const SizedBox(height: 14),
              AuthPrimaryButton(
                label: _busy ? 'PROVISIONING' : 'CREATE  PROFILE',
                busy: _busy,
                onPressed: _busy ? null : _submit,
              ),
              const SizedBox(height: 18),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Text('ALREADY ENROLLED?  ', style: AppText.label),
                  InkWell(
                    onTap: () {
                      ref.read(authControllerProvider.notifier).clearError();
                      context.go('/login');
                    },
                    child: const Padding(
                      padding: EdgeInsets.symmetric(vertical: 4, horizontal: 4),
                      child: Text(
                        'SIGN  IN',
                        style: TextStyle(
                          fontSize: 9.5,
                          letterSpacing: 1.6,
                          color: AppColors.accent,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
