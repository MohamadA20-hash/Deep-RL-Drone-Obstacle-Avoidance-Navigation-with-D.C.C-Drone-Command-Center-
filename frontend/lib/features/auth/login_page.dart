import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/auth/auth_controller.dart';
import '../../ui/theme.dart';
import 'widgets/auth_scaffold.dart';
import 'widgets/auth_widgets.dart';

class LoginPage extends ConsumerStatefulWidget {
  const LoginPage({super.key});

  @override
  ConsumerState<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends ConsumerState<LoginPage> {
  final _formKey = GlobalKey<FormState>();
  final _user = TextEditingController();
  final _pass = TextEditingController();
  final _userFocus = FocusNode();
  final _passFocus = FocusNode();
  bool _busy = false;

  @override
  void dispose() {
    _user.dispose();
    _pass.dispose();
    _userFocus.dispose();
    _passFocus.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!_formKey.currentState!.validate() || _busy) return;
    setState(() => _busy = true);
    final ok = await ref
        .read(authControllerProvider.notifier)
        .login(_user.text.trim(), _pass.text);
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) context.go('/dashboard');
  }

  @override
  Widget build(BuildContext context) {
    final error = ref.watch(authControllerProvider).error;
    return AuthScaffold(
      title: 'OPERATOR  SIGN-IN',
      subtitle: 'AUTHENTICATE TO ACCESS GROUND CONTROL',
      child: AutofillGroup(
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              AuthField(
                label: 'USERNAME',
                controller: _user,
                focusNode: _userFocus,
                autofocus: true,
                prefixIcon: Icons.person_outline,
                autofillHints: const [AutofillHints.username],
                textInputAction: TextInputAction.next,
                validator: (v) =>
                    (v == null || v.trim().isEmpty) ? 'Required' : null,
                onSubmitted: (_) => _passFocus.requestFocus(),
              ),
              const SizedBox(height: 18),
              AuthField(
                label: 'PASSWORD',
                controller: _pass,
                focusNode: _passFocus,
                obscure: true,
                prefixIcon: Icons.lock_outline,
                autofillHints: const [AutofillHints.password],
                textInputAction: TextInputAction.done,
                validator: (v) => (v == null || v.isEmpty) ? 'Required' : null,
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
                label: _busy ? 'AUTHENTICATING' : 'SIGN  IN',
                busy: _busy,
                onPressed: _busy ? null : _submit,
              ),
              const SizedBox(height: 18),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Text('NO ACCOUNT?  ', style: AppText.label),
                  InkWell(
                    onTap: () {
                      ref.read(authControllerProvider.notifier).clearError();
                      context.go('/register');
                    },
                    child: const Padding(
                      padding: EdgeInsets.symmetric(vertical: 4, horizontal: 4),
                      child: Text(
                        'REQUEST  ACCESS',
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
