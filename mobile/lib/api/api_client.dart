import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

class ApiException implements Exception {
  ApiException(this.status, this.message);

  /// null when the server could not be reached at all.
  final int? status;
  final String message;

  bool get isNetwork => status == null;
  bool get isUnauthorized => status == 401;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient(String baseUrl, {this.token}) : baseUrl = baseUrl.replaceAll(RegExp(r'/+$'), '');

  final String baseUrl;
  final String? token;
  static const _timeout = Duration(seconds: 10);

  Map<String, String> get _headers => {'Content-Type': 'application/json', if (token != null) 'Authorization': 'Bearer $token'};

  Uri _uri(String path, Map<String, String>? query) =>
      Uri.parse('$baseUrl$path').replace(queryParameters: query?.isEmpty ?? true ? null : query);

  Future<dynamic> get(String path, {Map<String, String>? query}) => _send(() => http.get(_uri(path, query), headers: _headers));

  Future<String> getText(String path, {Map<String, String>? query}) async {
    final response = await _raw(() => http.get(_uri(path, query), headers: _headers));
    return utf8.decode(response.bodyBytes);
  }

  Future<dynamic> post(String path, [Object? body]) =>
      _send(() => http.post(_uri(path, null), headers: _headers, body: jsonEncode(body ?? {})));

  Future<dynamic> put(String path, Object body) => _send(() => http.put(_uri(path, null), headers: _headers, body: jsonEncode(body)));

  Future<dynamic> _send(Future<http.Response> Function() request) async {
    final response = await _raw(request);
    if (response.bodyBytes.isEmpty) return null;
    return jsonDecode(utf8.decode(response.bodyBytes));
  }

  Future<http.Response> _raw(Future<http.Response> Function() request) async {
    final http.Response response;
    try {
      response = await request().timeout(_timeout);
    } on SocketException {
      throw ApiException(null, 'Cannot reach the server at $baseUrl');
    } on http.ClientException {
      throw ApiException(null, 'Cannot reach the server at $baseUrl');
    } on TimeoutException {
      throw ApiException(null, 'The server did not answer in time');
    } on FormatException {
      throw ApiException(null, 'Invalid server address: $baseUrl');
    }
    if (response.statusCode >= 400) {
      throw ApiException(response.statusCode, _errorMessage(response));
    }
    return response;
  }

  static String _errorMessage(http.Response response) {
    try {
      final detail = jsonDecode(utf8.decode(response.bodyBytes))['detail'];
      if (detail is String) return detail;
      if (detail is List && detail.isNotEmpty) {
        return detail.map((e) => '${(e['loc'] as List).last}: ${e['msg']}').join('\n');
      }
    } catch (_) {}
    return 'Server error ${response.statusCode}';
  }
}
