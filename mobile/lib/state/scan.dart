import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'session.dart';

const _khmerDigits = '០១២៣៤៥៦៧៨៩';

/// A scanned or typed code: trimmed, and Khmer digits (a scanner typing while the Khmer keyboard is on) as 0-9.
String cleanCode(String raw) {
  final out = StringBuffer();
  for (final char in raw.trim().split('')) {
    final digit = _khmerDigits.indexOf(char);
    out.write(digit >= 0 ? '$digit' : char);
  }
  return out.toString();
}

/// A scanner may read UPC-A (12 digits) for a product saved as EAN-13 with a leading 0, or the other way round.
Set<String> codeVariants(String raw) {
  final code = cleanCode(raw);
  return {code, if (RegExp(r'^\d{12}$').hasMatch(code)) '0$code', if (RegExp(r'^0\d{12}$').hasMatch(code)) code.substring(1)};
}

final _qtyPrefix = RegExp(r'^\s*(\d{1,4})\s*[*xX×]\s*(.*)$');

/// "3*8850999320014" or "3x coke": 3 of that item. A lone "3*" waits for the next scan or tap.
(int qty, String rest) splitQty(String text) {
  final m = _qtyPrefix.firstMatch(cleanCode(text));
  if (m == null) return (1, text.trim());
  return (int.parse(m.group(1)!).clamp(1, 9999), m.group(2)!.trim());
}

/// True when only "3*" is typed: the next scan or tap adds 3.
bool isPendingQty(String text) {
  final (qty, rest) = splitQty(text);
  return rest.isEmpty && _qtyPrefix.hasMatch(cleanCode(text)) && qty > 0;
}

// ---------- sound ----------

class ScanSoundNotifier extends Notifier<bool> {
  static const _key = 'scan_sound';

  @override
  bool build() => ref.read(prefsProvider).getBool(_key) ?? true;

  void set(bool on) {
    state = on;
    ref.read(prefsProvider).setBool(_key, on);
  }
}

final scanSoundProvider = NotifierProvider<ScanSoundNotifier, bool>(ScanSoundNotifier.new);

/// Vibrates, and clicks / buzzes when the scanner sound is on.
void scanFeedback(WidgetRef ref, {required bool ok}) {
  ok ? HapticFeedback.mediumImpact() : HapticFeedback.heavyImpact();
  if (ref.read(scanSoundProvider)) SystemSound.play(ok ? SystemSoundType.click : SystemSoundType.alert);
}

// ---------- USB / Bluetooth scanners ----------

/// A code scanned on another screen (the receipt of the last sale) for the till to add.
class ScanRequestNotifier extends Notifier<(String, int)?> {
  int _seq = 0;

  @override
  (String, int)? build() => null;

  void send(String code) => state = (code, ++_seq);
}

final scanRequestProvider = NotifierProvider<ScanRequestNotifier, (String, int)?>(ScanRequestNotifier.new);

/// Barcode scanners ("keyboard wedge") type the code very fast and press Enter (some press Tab). This tells such a
/// burst apart from a person typing, while no text box has the focus, and calls [onScan]. Keys are read by their
/// place on the keyboard, so a scan reads the same with the Khmer keyboard layout switched on. It works only while
/// this screen is the one showing. [shortcuts] are keys like F12 for the same screen.
class ScanListener extends StatefulWidget {
  const ScanListener({super.key, required this.onScan, this.shortcuts = const {}, required this.child});

  final void Function(String code) onScan;
  final Map<LogicalKeyboardKey, VoidCallback> shortcuts;
  final Widget child;

  @override
  State<ScanListener> createState() => _ScanListenerState();
}

class _ScanListenerState extends State<ScanListener> {
  /// Longest pause between two keys of one scan. Scanners send a key every 1-30 ms; people are much slower.
  static const _maxGap = Duration(milliseconds: 50);
  static const _minLength = 4;

  static final _keys = <PhysicalKeyboardKey, String>{
    PhysicalKeyboardKey.digit0: '0',
    PhysicalKeyboardKey.digit1: '1',
    PhysicalKeyboardKey.digit2: '2',
    PhysicalKeyboardKey.digit3: '3',
    PhysicalKeyboardKey.digit4: '4',
    PhysicalKeyboardKey.digit5: '5',
    PhysicalKeyboardKey.digit6: '6',
    PhysicalKeyboardKey.digit7: '7',
    PhysicalKeyboardKey.digit8: '8',
    PhysicalKeyboardKey.digit9: '9',
    PhysicalKeyboardKey.numpad0: '0',
    PhysicalKeyboardKey.numpad1: '1',
    PhysicalKeyboardKey.numpad2: '2',
    PhysicalKeyboardKey.numpad3: '3',
    PhysicalKeyboardKey.numpad4: '4',
    PhysicalKeyboardKey.numpad5: '5',
    PhysicalKeyboardKey.numpad6: '6',
    PhysicalKeyboardKey.numpad7: '7',
    PhysicalKeyboardKey.numpad8: '8',
    PhysicalKeyboardKey.numpad9: '9',
    PhysicalKeyboardKey.minus: '-',
    PhysicalKeyboardKey.numpadSubtract: '-',
    PhysicalKeyboardKey.period: '.',
    PhysicalKeyboardKey.slash: '/',
    for (final (i, key) in [
      PhysicalKeyboardKey.keyA,
      PhysicalKeyboardKey.keyB,
      PhysicalKeyboardKey.keyC,
      PhysicalKeyboardKey.keyD,
      PhysicalKeyboardKey.keyE,
      PhysicalKeyboardKey.keyF,
      PhysicalKeyboardKey.keyG,
      PhysicalKeyboardKey.keyH,
      PhysicalKeyboardKey.keyI,
      PhysicalKeyboardKey.keyJ,
      PhysicalKeyboardKey.keyK,
      PhysicalKeyboardKey.keyL,
      PhysicalKeyboardKey.keyM,
      PhysicalKeyboardKey.keyN,
      PhysicalKeyboardKey.keyO,
      PhysicalKeyboardKey.keyP,
      PhysicalKeyboardKey.keyQ,
      PhysicalKeyboardKey.keyR,
      PhysicalKeyboardKey.keyS,
      PhysicalKeyboardKey.keyT,
      PhysicalKeyboardKey.keyU,
      PhysicalKeyboardKey.keyV,
      PhysicalKeyboardKey.keyW,
      PhysicalKeyboardKey.keyX,
      PhysicalKeyboardKey.keyY,
      PhysicalKeyboardKey.keyZ,
    ].indexed)
      key: String.fromCharCode(97 + i),
  };

  final _buffer = StringBuffer();
  Duration _last = Duration.zero;

  @override
  void initState() {
    super.initState();
    HardwareKeyboard.instance.addHandler(_handle);
  }

  @override
  void dispose() {
    HardwareKeyboard.instance.removeHandler(_handle);
    super.dispose();
  }

  /// This screen is showing: not under a dialog or another page, and not a hidden tab of the main menu.
  bool get _showing => mounted && (ModalRoute.of(context)?.isCurrent ?? true) && TickerMode.valuesOf(context).enabled;

  bool _inTextField() => FocusManager.instance.primaryFocus?.context?.findAncestorWidgetOfExactType<EditableText>() != null;

  bool _handle(KeyEvent event) {
    if (event is KeyUpEvent) return false;
    final gap = event.timeStamp - _last;
    _last = event.timeStamp;

    final shortcut = widget.shortcuts[event.logicalKey];
    if (shortcut != null && event is KeyDownEvent && _showing) {
      shortcut();
      return true;
    }

    final key = event.logicalKey;
    if (key == LogicalKeyboardKey.enter || key == LogicalKeyboardKey.numpadEnter || key == LogicalKeyboardKey.tab) {
      final code = _buffer.toString().trim();
      _buffer.clear();
      // a text box with the focus gets the scan as typing; its own Enter handles it
      if (gap > _maxGap || code.length < _minLength || _inTextField() || !_showing) return false;
      widget.onScan(code);
      return true; // the Enter must not also press the focused button
    }

    var char = _keys[event.physicalKey] ?? event.character;
    if (char == null || char.length != 1) return false;
    if (HardwareKeyboard.instance.isShiftPressed) char = char.toUpperCase();
    if (gap > _maxGap) _buffer.clear();
    _buffer.write(char);
    return false;
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
