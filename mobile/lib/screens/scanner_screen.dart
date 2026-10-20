import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../core/theme.dart';
import '../state/scan.dart';

/// What the till did with a scanned code, shown at the bottom of the camera view.
typedef ScanOutcome = ({bool ok, String message});

/// Opens the camera. [scan] returns the first barcode it reads; [scanMany] keeps the camera open and hands every
/// code to the till (like a supermarket scanner) until the cashier taps Done.
class ScannerScreen extends ConsumerStatefulWidget {
  const ScannerScreen({super.key, this.onScan});

  /// Continuous mode when set.
  final Future<ScanOutcome> Function(String code)? onScan;

  static Future<String?> scan(BuildContext context) =>
      Navigator.push<String>(context, MaterialPageRoute(builder: (_) => const ScannerScreen()));

  static Future<void> scanMany(BuildContext context, Future<ScanOutcome> Function(String code) onScan) =>
      Navigator.push<void>(context, MaterialPageRoute(builder: (_) => ScannerScreen(onScan: onScan)));

  @override
  ConsumerState<ScannerScreen> createState() => _ScannerScreenState();
}

class _ScannerScreenState extends ConsumerState<ScannerScreen> {
  /// The same code counts again only after it was out of sight this long: holding an item under the camera adds it
  /// once; a second one of the same product is scanned after the first is taken away.
  static const _sameCodeGap = Duration(milliseconds: 1000);
  static const _frame = Size(280, 160);

  late final _controller = MobileScannerController(
    detectionSpeed: widget.onScan == null ? DetectionSpeed.noDuplicates : DetectionSpeed.normal,
    formats: const [
      BarcodeFormat.ean13,
      BarcodeFormat.ean8,
      BarcodeFormat.upcA,
      BarcodeFormat.upcE,
      BarcodeFormat.code128,
      BarcodeFormat.code39,
      BarcodeFormat.itf14,
      BarcodeFormat.qrCode,
    ],
  );
  bool _done = false;
  String? _lastCode;
  DateTime _lastSeen = DateTime(2000);
  ScanOutcome? _outcome;
  int _added = 0;
  bool _busy = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _onDetect(BarcodeCapture capture) async {
    final code = capture.barcodes.map((b) => b.rawValue?.trim()).whereType<String>().where((c) => c.isNotEmpty).firstOrNull;
    if (code == null || _done || _busy) return;

    final onScan = widget.onScan;
    if (onScan == null) {
      _done = true;
      HapticFeedback.mediumImpact();
      Navigator.pop(context, code);
      return;
    }

    final now = DateTime.now();
    final stillInView = code == _lastCode && now.difference(_lastSeen) < _sameCodeGap;
    _lastCode = code;
    _lastSeen = now;
    if (stillInView) return;

    _busy = true;
    final outcome = await onScan(code);
    _busy = false;
    if (!mounted) return;
    scanFeedback(ref, ok: outcome.ok);
    setState(() {
      _outcome = outcome;
      if (outcome.ok) _added++;
    });
  }

  @override
  Widget build(BuildContext context) {
    final many = widget.onScan != null;
    final outcome = _outcome;
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: Text(many ? 'Scan items' : 'Scan barcode'),
        actions: [
          IconButton(
            tooltip: ref.watch(scanSoundProvider) ? 'Scanner sound on' : 'Scanner sound off',
            icon: Icon(ref.watch(scanSoundProvider) ? Icons.volume_up : Icons.volume_off),
            onPressed: () => ref.read(scanSoundProvider.notifier).set(!ref.read(scanSoundProvider)),
          ),
          IconButton(tooltip: 'Flashlight', icon: const Icon(Icons.flash_on), onPressed: _controller.toggleTorch),
          IconButton(tooltip: 'Switch camera', icon: const Icon(Icons.cameraswitch), onPressed: _controller.switchCamera),
        ],
      ),
      body: LayoutBuilder(
        builder: (context, constraints) {
          final window = Rect.fromCenter(center: constraints.biggest.center(Offset.zero), width: _frame.width, height: _frame.height);
          return Stack(
            children: [
              // only codes inside the frame count, so a second item on the counter is not picked up by mistake
              MobileScanner(controller: _controller, onDetect: _onDetect, scanWindow: window),
              Positioned.fromRect(
                rect: window,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  decoration: BoxDecoration(
                    border: Border.all(
                      color: outcome == null ? Colors.white : (outcome.ok ? AppColors.success : AppColors.price),
                      width: 3,
                    ),
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
              Positioned(
                left: 0,
                right: 0,
                top: window.bottom + 16,
                child: const Text(
                  'Hold the barcode inside the frame',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white70),
                ),
              ),
              if (many)
                Positioned(
                  left: 16,
                  right: 16,
                  bottom: 16,
                  child: SafeArea(
                    top: false,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        if (outcome != null)
                          Container(
                            margin: const EdgeInsets.only(bottom: 10),
                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                            decoration: BoxDecoration(
                              color: outcome.ok ? AppColors.success : AppColors.price,
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Row(
                              children: [
                                Icon(outcome.ok ? Icons.check_circle : Icons.error_outline, color: Colors.white),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: Text(
                                    outcome.message,
                                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 15),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        FilledButton(
                          style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
                          onPressed: () => Navigator.pop(context),
                          child: Text(_added == 0 ? 'Done' : 'Done · $_added scanned'),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}
