import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../ui/theme.dart';

/// A single labeled text field for the auth pages. Stateful so it can manage
/// its own password visibility toggle without leaking that into callers.
class AuthField extends StatefulWidget {
  final String label;
  final TextEditingController controller;
  final bool obscure;
  final TextInputType? keyboardType;
  final List<String>? autofillHints;
  final String? Function(String?)? validator;
  final ValueChanged<String>? onSubmitted;
  final TextInputAction? textInputAction;
  final FocusNode? focusNode;
  final bool autofocus;
  final List<TextInputFormatter>? inputFormatters;
  final IconData? prefixIcon;

  const AuthField({
    super.key,
    required this.label,
    required this.controller,
    this.obscure = false,
    this.keyboardType,
    this.autofillHints,
    this.validator,
    this.onSubmitted,
    this.textInputAction,
    this.focusNode,
    this.autofocus = false,
    this.inputFormatters,
    this.prefixIcon,
  });

  @override
  State<AuthField> createState() => _AuthFieldState();
}

class _AuthFieldState extends State<AuthField> {
  late bool _obscured = widget.obscure;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(widget.label, style: AppText.label),
        const SizedBox(height: 6),
        TextFormField(
          controller: widget.controller,
          focusNode: widget.focusNode,
          autofocus: widget.autofocus,
          obscureText: _obscured,
          keyboardType: widget.keyboardType,
          autofillHints: widget.autofillHints,
          validator: widget.validator,
          onFieldSubmitted: widget.onSubmitted,
          textInputAction: widget.textInputAction,
          inputFormatters: widget.inputFormatters,
          cursorColor: AppColors.accent,
          cursorWidth: 1,
          style: const TextStyle(
            color: AppColors.text,
            fontSize: 13,
            letterSpacing: 0.4,
          ),
          decoration: InputDecoration(
            isDense: true,
            filled: true,
            fillColor: AppColors.panel2,
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
            errorStyle: const TextStyle(
                color: AppColors.alert, fontSize: 10, letterSpacing: 0.6),
            prefixIcon: widget.prefixIcon == null
                ? null
                : Icon(widget.prefixIcon, size: 14, color: AppColors.textMute),
            prefixIconConstraints:
                const BoxConstraints(minWidth: 32, minHeight: 32),
            suffixIcon: widget.obscure
                ? _EyeToggle(
                    obscured: _obscured,
                    onTap: () => setState(() => _obscured = !_obscured),
                  )
                : null,
            suffixIconConstraints:
                const BoxConstraints(minWidth: 36, minHeight: 36),
            enabledBorder: _border(AppColors.line),
            focusedBorder: _border(AppColors.accent),
            errorBorder: _border(AppColors.alert),
            focusedErrorBorder: _border(AppColors.alert),
          ),
        ),
      ],
    );
  }

  OutlineInputBorder _border(Color c) => OutlineInputBorder(
        borderRadius: BorderRadius.circular(2),
        borderSide: BorderSide(color: c, width: 1),
      );
}

class _EyeToggle extends StatelessWidget {
  final bool obscured;
  final VoidCallback onTap;
  const _EyeToggle({required this.obscured, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: obscured ? 'Show password' : 'Hide password',
      child: InkWell(
        onTap: onTap,
        customBorder: const CircleBorder(),
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: Icon(
            obscured
                ? Icons.visibility_outlined
                : Icons.visibility_off_outlined,
            size: 16,
            color: AppColors.textDim,
          ),
        ),
      ),
    );
  }
}

class AuthPrimaryButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool busy;

  const AuthPrimaryButton({
    super.key,
    required this.label,
    this.onPressed,
    this.busy = false,
  });

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    return SizedBox(
      height: 42,
      child: Material(
        color: enabled ? AppColors.accentSoft : AppColors.panel2,
        child: InkWell(
          onTap: onPressed,
          child: Container(
            decoration: BoxDecoration(
              border: Border.all(
                color: enabled ? AppColors.accent : AppColors.line,
                width: 1,
              ),
            ),
            alignment: Alignment.center,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (busy) ...[
                  const SizedBox(
                    width: 12,
                    height: 12,
                    child: CircularProgressIndicator(
                      strokeWidth: 1.4,
                      valueColor:
                          AlwaysStoppedAnimation<Color>(AppColors.accent),
                    ),
                  ),
                  const SizedBox(width: 10),
                ],
                Text(
                  label,
                  style: TextStyle(
                    fontSize: 11,
                    letterSpacing: 2.4,
                    color: enabled ? AppColors.accent : AppColors.textMute,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class AuthErrorBanner extends StatelessWidget {
  final String message;
  final int? statusCode;
  final List<String>? details;

  const AuthErrorBanner({
    super.key,
    required this.message,
    this.statusCode,
    this.details,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF2A1518),
        border: Border.all(color: AppColors.alert, width: 1),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.warning_amber_rounded,
              size: 14, color: AppColors.alert),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (statusCode != null) ...[
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 5, vertical: 2),
                        margin: const EdgeInsets.only(right: 8, top: 1),
                        decoration: BoxDecoration(
                          color: AppColors.alert.withOpacity(0.18),
                          border:
                              Border.all(color: AppColors.alert, width: 0.8),
                        ),
                        child: Text(
                          'ERR $statusCode',
                          style: const TextStyle(
                            color: AppColors.alert,
                            fontSize: 8.5,
                            letterSpacing: 1.0,
                            fontWeight: FontWeight.w700,
                            fontFamilyFallback: ['Consolas', 'monospace'],
                          ),
                        ),
                      ),
                    ],
                    Expanded(
                      child: Text(
                        message.toUpperCase(),
                        style: const TextStyle(
                          color: AppColors.alert,
                          fontSize: 10,
                          letterSpacing: 1.2,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ],
                ),
                if (details != null && details!.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  ...details!.take(4).map(
                        (d) => Padding(
                          padding: const EdgeInsets.only(top: 2),
                          child: Text(
                            '› $d',
                            style: const TextStyle(
                              color: Color(0xFFE08B86),
                              fontSize: 10,
                              height: 1.3,
                              letterSpacing: 0.2,
                              fontFamilyFallback: ['Consolas', 'monospace'],
                            ),
                          ),
                        ),
                      ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
