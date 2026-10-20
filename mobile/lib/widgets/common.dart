import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../state/session.dart';

void showMessage(BuildContext context, String message) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(message)));
}

/// Shows the error; an expired login sends the user back to the login screen.
void showError(BuildContext context, WidgetRef ref, Object error) {
  if (error is ApiException && error.isUnauthorized) {
    ref.read(sessionProvider.notifier).logout();
    return;
  }
  showMessage(context, error.toString());
}

Future<String?> askText(
  BuildContext context, {
  required String title,
  String label = '',
  String initial = '',
  TextInputType keyboard = TextInputType.text,
  bool obscure = false,
  String confirmText = 'OK',
}) {
  final controller = TextEditingController(text: initial);
  return showDialog<String>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: TextField(
        controller: controller,
        autofocus: true,
        obscureText: obscure,
        keyboardType: keyboard,
        decoration: InputDecoration(labelText: label),
        onSubmitted: (value) => Navigator.pop(context, value),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: () => Navigator.pop(context, controller.text), child: Text(confirmText)),
      ],
    ),
  );
}

/// Asks for a manager PIN and checks it with the server.
/// Offline the PIN is accepted here and checked when the sale is synced.
Future<String?> askManagerPin(BuildContext context, WidgetRef ref, {String reason = 'Manager approval'}) async {
  final pin = await askText(
    context,
    title: reason,
    label: 'Manager PIN',
    keyboard: TextInputType.number,
    obscure: true,
    confirmText: 'Approve',
  );
  if (pin == null || pin.isEmpty || !context.mounted) return null;
  try {
    await ref.read(apiProvider).post('/api/auth/verify-manager-pin', {'pin': pin});
    return pin;
  } on ApiException catch (e) {
    if (e.isNetwork) return pin;
    if (context.mounted) showError(context, ref, e);
    return null;
  }
}

Future<bool> confirm(BuildContext context, String title, String message, {String confirmText = 'Yes'}) async {
  final result = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        FilledButton(onPressed: () => Navigator.pop(context, true), child: Text(confirmText)),
      ],
    ),
  );
  return result ?? false;
}

class MoneyRow extends StatelessWidget {
  const MoneyRow(this.label, this.value, {super.key, this.bold = false, this.color});

  final String label, value;
  final bool bold;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final style = (bold ? Theme.of(context).textTheme.titleMedium : Theme.of(context).textTheme.bodyMedium)?.copyWith(
      fontWeight: bold ? FontWeight.bold : null,
      color: color,
    );
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Expanded(child: Text(label, style: style)),
          Text(value, style: style),
        ],
      ),
    );
  }
}

/// Loading / error / data for an AsyncValue, with a retry button on errors.
class AsyncView<T> extends ConsumerWidget {
  const AsyncView({super.key, required this.value, required this.builder, required this.onRetry});

  final AsyncValue<T> value;
  final Widget Function(T data) builder;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return value.when(
      data: builder,
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (error, _) {
        if (error is ApiException && error.isUnauthorized) {
          Future.microtask(() => ref.read(sessionProvider.notifier).logout());
        }
        return Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.cloud_off, size: 48),
                const SizedBox(height: 12),
                Text(error.toString(), textAlign: TextAlign.center),
                const SizedBox(height: 12),
                FilledButton.tonal(onPressed: onRetry, child: const Text('Try again')),
              ],
            ),
          ),
        );
      },
    );
  }
}

/// Screen widths where layouts change.
abstract final class Breakpoints {
  static const medium = 700.0; // tablets, small browser windows
  static const wide = 1000.0; // laptops, desktop browsers
}

/// Keeps forms and lists readable on wide screens by centering them at a comfortable width.
class MaxWidth extends StatelessWidget {
  const MaxWidth({super.key, required this.child, this.width = 720});

  final Widget child;
  final double width;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.topCenter,
      heightFactor: 1, // as tall as the child; without it a bottom bar would fill the whole screen
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: width),
        child: child,
      ),
    );
  }
}

final digitsOnly = [FilteringTextInputFormatter.digitsOnly];
final decimalOnly = [FilteringTextInputFormatter.allow(RegExp(r'[0-9.]'))];
