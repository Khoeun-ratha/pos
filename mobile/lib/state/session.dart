import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api_client.dart';
import '../models.dart';

/// The server address the login screen starts with, until one is saved. A real phone needs the PC's Wi-Fi address:
/// `flutter run --dart-define=POS_SERVER=http://192.168.1.152:8000` (start_mobile.bat finds it by itself).
/// Without it: the Android emulator, which reaches the PC at 10.0.2.2.
const defaultServerUrl = String.fromEnvironment('POS_SERVER', defaultValue: 'http://10.0.2.2:8000');

final prefsProvider = Provider<SharedPreferences>((ref) => throw UnimplementedError('Overridden in main()'));

class Session {
  const Session({required this.serverUrl, this.token, this.user, this.settings = const StoreSettings()});

  final String serverUrl;
  final String? token;
  final User? user;
  final StoreSettings settings;

  bool get loggedIn => token != null && user != null;
}

class SessionNotifier extends Notifier<Session> {
  SharedPreferences get _prefs => ref.read(prefsProvider);

  @override
  Session build() {
    final prefs = ref.read(prefsProvider);
    final user = prefs.getString('user');
    final settings = prefs.getString('settings');
    return Session(
      serverUrl: prefs.getString('server_url') ?? defaultServerUrl,
      token: prefs.getString('token'),
      user: user == null ? null : User.fromJson(jsonDecode(user)),
      settings: settings == null ? const StoreSettings() : StoreSettings.fromJson(jsonDecode(settings)),
    );
  }

  Future<void> login(String serverUrl, String username, String secret, {required bool usePin}) async {
    final url = serverUrl.trim().replaceAll(RegExp(r'/+$'), '');
    final data = await ApiClient(url)
        .post(usePin ? '/api/auth/pin-login' : '/api/auth/login', {'username': username.trim(), usePin ? 'pin' : 'password': secret});
    final token = data['access_token'] as String;
    final user = User.fromJson(data['user']);
    final settings = StoreSettings.fromJson(await ApiClient(url, token: token).get('/api/settings'));

    await _prefs.setString('server_url', url);
    await _prefs.setString('token', token);
    await _prefs.setString('user', jsonEncode(user.toJson()));
    await _prefs.setString('settings', jsonEncode(settings.toJson()));
    state = Session(serverUrl: url, token: token, user: user, settings: settings);
  }

  Future<void> refreshSettings() async {
    final settings = StoreSettings.fromJson(await ref.read(apiProvider).get('/api/settings'));
    await _prefs.setString('settings', jsonEncode(settings.toJson()));
    state = Session(serverUrl: state.serverUrl, token: state.token, user: state.user, settings: settings);
  }

  Future<void> logout() async {
    await _prefs.remove('token');
    await _prefs.remove('user');
    state = Session(serverUrl: state.serverUrl, settings: state.settings);
  }
}

final sessionProvider = NotifierProvider<SessionNotifier, Session>(SessionNotifier.new);

final apiProvider = Provider<ApiClient>((ref) {
  final session = ref.watch(sessionProvider);
  return ApiClient(session.serverUrl, token: session.token);
});

final currentUserProvider = Provider<User>((ref) => ref.watch(sessionProvider).user!);
