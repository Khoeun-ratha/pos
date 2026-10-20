import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/session.dart';
import '../widgets/brand_mark.dart';
import '../widgets/common.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  late final _server = TextEditingController(text: ref.read(sessionProvider).serverUrl);
  final _username = TextEditingController();
  final _secret = TextEditingController();
  bool _usePin = false;
  bool _busy = false;

  Future<void> _login() async {
    if (_username.text.trim().isEmpty || _secret.text.isEmpty) return;
    setState(() => _busy = true);
    try {
      await ref.read(sessionProvider.notifier).login(_server.text, _username.text, _secret.text, usePin: _usePin);
    } catch (e) {
      if (mounted) showError(context, ref, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final storeName = ref.watch(sessionProvider.select((s) => s.settings.storeName));
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: AutofillGroup(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Center(child: BrandMark(size: 80)),
                    const SizedBox(height: 14),
                    Text(
                      storeName,
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800, letterSpacing: 0.5),
                    ),
                    const SizedBox(height: 32),
                    TextField(
                      controller: _server,
                      keyboardType: TextInputType.url,
                      decoration: const InputDecoration(
                        labelText: 'Server address',
                        helperText: 'e.g. http://192.168.1.10:8000',
                        prefixIcon: Icon(Icons.dns),
                      ),
                    ),
                    const SizedBox(height: 16),
                    TextField(
                      controller: _username,
                      autofillHints: const [AutofillHints.username],
                      decoration: const InputDecoration(labelText: 'Username', prefixIcon: Icon(Icons.person)),
                    ),
                    const SizedBox(height: 16),
                    SegmentedButton<bool>(
                      segments: const [
                        ButtonSegment(value: false, label: Text('Password'), icon: Icon(Icons.password)),
                        ButtonSegment(value: true, label: Text('PIN'), icon: Icon(Icons.pin)),
                      ],
                      selected: {_usePin},
                      onSelectionChanged: (s) => setState(() {
                        _usePin = s.first;
                        _secret.clear();
                      }),
                    ),
                    const SizedBox(height: 16),
                    TextField(
                      controller: _secret,
                      obscureText: true,
                      keyboardType: _usePin ? TextInputType.number : TextInputType.visiblePassword,
                      autofillHints: _usePin ? null : const [AutofillHints.password],
                      decoration: InputDecoration(labelText: _usePin ? 'PIN' : 'Password', prefixIcon: const Icon(Icons.lock)),
                      onSubmitted: (_) => _login(),
                    ),
                    const SizedBox(height: 24),
                    FilledButton.icon(
                      onPressed: _busy ? null : _login,
                      icon: _busy
                          ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
                          : const Icon(Icons.login),
                      label: const Text('Log in'),
                      style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
