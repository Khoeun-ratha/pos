import 'package:intl/intl.dart';

/// Money is always an int: USD in cents, KHR in riel.
final _usd = NumberFormat.currency(locale: 'en_US', symbol: r'$', decimalDigits: 2);
final _number = NumberFormat.decimalPattern('en_US');
final _dateTime = DateFormat('yyyy-MM-dd HH:mm');
final _date = DateFormat('yyyy-MM-dd');

String usd(int cents) => _usd.format(cents / 100);

/// "KHR" rather than "៛": the riel sign is missing from the default web fonts.
String khr(int riel) => '${_number.format(riel)} KHR';
String dateTime(DateTime value) => _dateTime.format(value);
String isoDate(DateTime value) => _date.format(value);

/// Integer division rounding half up (non-negative inputs), same as the server.
int divRound(int numerator, int denominator) => (2 * numerator + denominator) ~/ (2 * denominator);

int khrToUsdCents(int riel, int rate) => divRound(riel * 100, rate);

/// Cents to riel rounded to the nearest 100-riel note.
int usdCentsToKhr(int cents, int rate, {int roundTo = 100}) => divRound(cents * rate, 100 * roundTo) * roundTo;

/// "12.5" -> 1250. Returns null for anything that is not a positive amount.
int? parseDollars(String text) {
  final value = double.tryParse(text.trim().replaceAll(',', ''));
  if (value == null || value < 0) return null;
  return (value * 100).round();
}

int? parseWhole(String text) {
  final value = int.tryParse(text.trim().replaceAll(',', ''));
  return value == null || value < 0 ? null : value;
}
