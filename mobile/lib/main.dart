import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'core/theme.dart';
import 'screens/home_shell.dart';
import 'screens/login_screen.dart';
import 'state/session.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  runApp(
    ProviderScope(
      overrides: [prefsProvider.overrideWithValue(prefs)],
      // screens show a "Try again" button instead of retrying silently
      retry: (_, _) => null,
      child: const PosApp(),
    ),
  );
}

class PosApp extends ConsumerWidget {
  const PosApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final loggedIn = ref.watch(sessionProvider.select((s) => s.loggedIn));
    return MaterialApp(
      title: 'POS',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(), // light mode only, everywhere
      themeMode: ThemeMode.light,
      home: loggedIn ? const HomeShell() : const LoginScreen(),
    );
  }
}
