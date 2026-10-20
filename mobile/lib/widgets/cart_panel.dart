import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/money.dart';
import '../core/pricing.dart';
import '../core/theme.dart';
import '../api/api_client.dart';
import '../models.dart';
import '../screens/checkout_screen.dart';
import '../screens/customers_screen.dart';
import '../state/cart.dart';
import '../state/held.dart';
import '../state/sales.dart';
import '../state/session.dart';
import 'common.dart';
import 'product_image.dart';

/// Cashiers need a manager PIN to remove items or give discounts; one approval covers the whole sale.
Future<bool> approveCartAction(BuildContext context, WidgetRef ref, String reason) async {
  if (ref.read(currentUserProvider).isManager) return true;
  if (ref.read(cartProvider).managerPin != null) return true;
  final pin = await askManagerPin(context, ref, reason: reason);
  if (pin == null) return false;
  ref.read(cartProvider.notifier).setManagerPin(pin);
  return true;
}

/// Taking items off an unpaid sale is a void: approved, then written to the activity log on the server.
/// Offline the void still happens; it just cannot be logged.
Future<bool> recordVoid(BuildContext context, WidgetRef ref, String kind, List<(CartLine, int)> items) async {
  if (!await approveCartAction(context, ref, kind == 'clear' ? 'Void sale' : 'Void item')) return false;
  try {
    await ref.read(apiProvider).post('/api/sales/void', {
      'kind': kind,
      'items': [
        for (final (line, qty) in items) {'name': line.product.name, 'qty': qty, 'amount': line.product.price * qty},
      ],
      'manager_pin': ref.read(cartProvider).managerPin,
    });
    return true;
  } on ApiException catch (e) {
    if (e.isNetwork) return true;
    ref.read(cartProvider.notifier).setManagerPin(null);
    if (context.mounted) showError(context, ref, e);
    return false;
  }
}

/// Pay button / F12. A till takes money only into a counted drawer (offline: the server decides later).
void startCheckout(BuildContext context, WidgetRef ref, {bool inSheet = false}) {
  if (ref.read(cartProvider).isEmpty) return;
  final shift = ref.read(currentShiftProvider);
  if (shift.hasValue && shift.value == null) {
    showMessage(context, 'Open a shift first: count the cash drawer on the Shift page.');
    return;
  }
  if (inSheet) Navigator.pop(context);
  Navigator.push(context, MaterialPageRoute(builder: (_) => const CheckoutScreen()));
}

class CartPanel extends ConsumerWidget {
  const CartPanel({super.key, this.inSheet = false});

  final bool inSheet;

  Future<void> _removeLine(BuildContext context, WidgetRef ref, int index) async {
    final line = ref.read(cartProvider).lines[index];
    if (await recordVoid(context, ref, 'line', [(line, line.qty)])) ref.read(cartProvider.notifier).remove(index);
  }

  /// One less is a void of one unit.
  Future<void> _less(BuildContext context, WidgetRef ref, int index) async {
    final line = ref.read(cartProvider).lines[index];
    if (await recordVoid(context, ref, 'line', [(line, 1)])) ref.read(cartProvider.notifier).setQty(index, line.qty - 1);
  }

  /// Tap the quantity to type it (e.g. 24 for a whole box). Fewer is a void, like the minus button.
  Future<void> _typeQty(BuildContext context, WidgetRef ref, int index) async {
    final line = ref.read(cartProvider).lines[index];
    final text = await askText(
      context,
      title: line.product.name,
      label: 'Quantity',
      initial: '${line.qty}',
      keyboard: TextInputType.number,
    );
    final qty = text == null ? null : parseWhole(text);
    if (qty == null || qty < 1 || qty > 9999 || qty == line.qty || !context.mounted) return;
    if (qty < line.qty && !await recordVoid(context, ref, 'line', [(line, line.qty - qty)])) return;
    ref.read(cartProvider.notifier).setQty(index, qty);
  }

  Future<void> _clear(BuildContext context, WidgetRef ref) async {
    if (!await confirm(context, 'Clear cart', 'Remove all items from this sale?')) return;
    final lines = ref.read(cartProvider).lines;
    if (!context.mounted || !await recordVoid(context, ref, 'clear', [for (final l in lines) (l, l.qty)])) return;
    ref.read(cartProvider.notifier).clear();
    if (inSheet && context.mounted) Navigator.pop(context);
  }

  Future<void> _lineDiscount(BuildContext context, WidgetRef ref, int index) async {
    final line = ref.read(cartProvider).lines[index];
    final result = await DiscountDialog.show(
      context,
      title: 'Discount: ${line.product.name}',
      type: line.discountType,
      value: line.discountValue,
    );
    if (result == null || !context.mounted) return;
    if (result.type != null && !await approveCartAction(context, ref, 'Discount')) return;
    ref.read(cartProvider.notifier).setLineDiscount(index, result.type, result.value);
  }

  Future<void> _pickCustomer(BuildContext context, WidgetRef ref) async {
    final customer = await Navigator.push<Customer>(context, MaterialPageRoute(builder: (_) => const CustomersScreen(pickMode: true)));
    if (customer != null) ref.read(cartProvider.notifier).setCustomer(customer);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cart = ref.watch(cartProvider);
    final totals = ref.watch(cartTotalsProvider);
    final rate = ref.watch(sessionProvider.select((s) => s.settings.exchangeRate));
    final notifier = ref.read(cartProvider.notifier);
    final customer = cart.customer;
    final held = ref.watch(heldOrdersProvider).value ?? const <HeldOrder>[];
    final lastAdded = ref.watch(lastAddedProvider);

    return Material(
      color: Colors.white,
      child: Column(
        children: [
          // customer
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 8, 12),
            child: Row(
              children: [
                Expanded(
                  child: Row(
                    children: [
                      Flexible(
                        flex: 4,
                        child: Text(
                          customer?.name ?? 'Walk-in Customer',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                        ),
                      ),
                      const SizedBox(width: 8),
                      // the name gets most of the room; the tag shrinks only on very narrow screens
                      Flexible(child: _Tag(customer == null ? 'Walk-in' : '${customer.points} pts')),
                    ],
                  ),
                ),
                if (customer != null)
                  IconButton(
                    tooltip: 'Remove customer',
                    icon: const Icon(Icons.close, size: 18),
                    onPressed: () => notifier.setCustomer(null),
                  ),
                TextButton(onPressed: () => _pickCustomer(context, ref), child: Text(customer == null ? 'Change customer' : 'Change')),
              ],
            ),
          ),
          const Divider(),
          // held orders (all tills)
          if (held.isNotEmpty) ...[
            SizedBox(
              height: 48,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                children: [for (final h in held) _HeldChip(order: h, inSheet: inSheet)],
              ),
            ),
            const Divider(),
          ],
          // items
          Expanded(
            child: cart.isEmpty
                ? const Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.shopping_bag_outlined, size: 44, color: AppColors.border),
                        SizedBox(height: 8),
                        Text('Tap a product to add', style: TextStyle(color: AppColors.muted, fontSize: 15)),
                      ],
                    ),
                  )
                : ListView.separated(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    itemCount: cart.lines.length,
                    separatorBuilder: (_, _) => const Divider(indent: 16, endIndent: 16),
                    itemBuilder: (context, i) {
                      final line = cart.lines[i];
                      final result = i < totals.lines.length ? totals.lines[i] : null;
                      final flash = lastAdded != null && lastAdded.$1 == line.product.id && !line.hasDiscount ? lastAdded.$2 : null;
                      return _CartLineTile(
                        line: line,
                        flashSeq: flash,
                        onQty: () => _typeQty(context, ref, i),
                        amount: result == null ? line.product.price * line.qty : result.gross - result.discount,
                        discount: result?.discount ?? 0,
                        onTap: () => _lineDiscount(context, ref, i),
                        onMinus: () => line.qty == 1 ? _removeLine(context, ref, i) : _less(context, ref, i),
                        onPlus: () => notifier.setQty(i, line.qty + 1),
                      );
                    },
                  ),
          ),
          // totals
          Container(
            decoration: const BoxDecoration(
              color: Color(0xFFFAFBFD),
              border: Border(top: BorderSide(color: AppColors.border)),
            ),
            child: SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
                child: Column(
                  children: [
                    _OrderDiscountRow(enabled: !cart.isEmpty),
                    const SizedBox(height: 8),
                    _TotalRow('Subtotal', usd(totals.subtotal)),
                    if (totals.discountTotal > 0) _TotalRow('Discount', '-${usd(totals.discountTotal)}', color: AppColors.price),
                    if (totals.taxTotal > 0) _TotalRow('VAT', usd(totals.taxTotal)),
                    const Padding(padding: EdgeInsets.symmetric(vertical: 8), child: Divider()),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Padding(
                          padding: EdgeInsets.only(top: 6),
                          child: Text('Grand Total', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              FittedBox(
                                fit: BoxFit.scaleDown,
                                alignment: Alignment.centerRight,
                                child: Text(usd(totals.total), style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w800)),
                              ),
                              Text(
                                khr(usdCentsToKhr(totals.total, rate)),
                                style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.w600),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 14),
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton(
                            style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(52), foregroundColor: AppColors.muted),
                            onPressed: cart.isEmpty ? null : () => _clear(context, ref),
                            child: const Text('Clear'),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Tooltip(
                          message: 'Hold this sale and serve another customer',
                          child: OutlinedButton(
                            style: OutlinedButton.styleFrom(minimumSize: const Size(52, 52), padding: EdgeInsets.zero),
                            onPressed: cart.isEmpty ? null : () => holdCart(context, ref),
                            child: const Icon(Icons.pause_circle_outline),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          flex: 2,
                          child: FilledButton(
                            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
                            onPressed: cart.isEmpty ? null : () => startCheckout(context, ref, inSheet: inSheet),
                            child: Text('Pay · ${usd(totals.total)}', style: const TextStyle(fontSize: 17)),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// A held order: tap to continue it here, x to throw it away.
class _HeldChip extends ConsumerWidget {
  const _HeldChip({required this.order, required this.inSheet});

  final HeldOrder order;
  final bool inSheet;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: InputChip(
        avatar: const Icon(Icons.pause_circle_outline, size: 16, color: AppColors.primary),
        label: Text('${order.title} · ${usd(order.total)}'),
        labelStyle: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.w600),
        backgroundColor: AppColors.primarySoft,
        side: BorderSide.none,
        tooltip: 'Resume order held at ${order.time} by ${order.cashierName}',
        onPressed: () => resumeHeld(context, ref, order),
        deleteIcon: const Icon(Icons.close, size: 16),
        deleteButtonTooltipMessage: 'Discard held order',
        onDeleted: () => discardHeld(context, ref, order),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
    decoration: BoxDecoration(color: AppColors.page, borderRadius: BorderRadius.circular(6)),
    child: Text(
      text,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: const TextStyle(fontSize: 12, color: AppColors.muted, fontWeight: FontWeight.w600),
    ),
  );
}

class _TotalRow extends StatelessWidget {
  const _TotalRow(this.label, this.value, {this.color});
  final String label, value;
  final Color? color;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 3),
    child: Row(
      children: [
        Text(label, style: TextStyle(fontSize: 15, color: color ?? AppColors.muted)),
        const Spacer(),
        Text(
          value,
          style: TextStyle(fontSize: 15, color: color ?? AppColors.text, fontWeight: FontWeight.w600),
        ),
      ],
    ),
  );
}

class _CartLineTile extends StatefulWidget {
  const _CartLineTile({
    required this.line,
    required this.amount,
    required this.discount,
    required this.flashSeq,
    required this.onTap,
    required this.onQty,
    required this.onMinus,
    required this.onPlus,
  });

  final CartLine line;
  final int amount, discount;

  /// Set when the last tap or scan went to this line: it flashes and scrolls into view.
  final int? flashSeq;
  final VoidCallback onTap, onQty, onMinus, onPlus;

  @override
  State<_CartLineTile> createState() => _CartLineTileState();
}

class _CartLineTileState extends State<_CartLineTile> {
  @override
  void initState() {
    super.initState();
    if (widget.flashSeq != null) _show();
  }

  @override
  void didUpdateWidget(_CartLineTile old) {
    super.didUpdateWidget(old);
    if (widget.flashSeq != null && widget.flashSeq != old.flashSeq) _show();
  }

  void _show() => WidgetsBinding.instance.addPostFrameCallback((_) {
    if (!mounted) return;
    Scrollable.ensureVisible(
      context,
      alignmentPolicy: ScrollPositionAlignmentPolicy.keepVisibleAtEnd,
      duration: const Duration(milliseconds: 200),
    );
  });

  @override
  Widget build(BuildContext context) {
    final line = widget.line;
    final amount = widget.amount;
    final discount = widget.discount;
    final tile = InkWell(
      onTap: widget.onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(
          children: [
            ProductImage(product: line.product, width: 40, height: 40, iconSize: 20, radius: 10),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    line.product.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                  Text(
                    discount > 0 ? '${usd(line.product.price)} · discount -${usd(discount)}' : usd(line.product.price),
                    style: TextStyle(fontSize: 12, color: discount > 0 ? AppColors.price : AppColors.muted),
                  ),
                ],
              ),
            ),
            _QtyStepper(qty: line.qty, onMinus: widget.onMinus, onPlus: widget.onPlus, onQty: widget.onQty),
            SizedBox(
              width: 72,
              child: Text(
                usd(amount),
                textAlign: TextAlign.right,
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
            ),
          ],
        ),
      ),
    );
    if (widget.flashSeq == null) return tile;
    return TweenAnimationBuilder<Color?>(
      key: ValueKey(widget.flashSeq), // restarts when the same line is added again
      tween: ColorTween(begin: const Color(0xFFDBEAFE), end: Colors.transparent),
      duration: const Duration(milliseconds: 1200),
      curve: Curves.easeOut,
      builder: (context, color, child) => ColoredBox(color: color ?? Colors.transparent, child: child),
      child: tile,
    );
  }
}

class _QtyStepper extends StatelessWidget {
  const _QtyStepper({required this.qty, required this.onMinus, required this.onPlus, required this.onQty});

  final int qty;
  final VoidCallback onMinus, onPlus, onQty;

  @override
  Widget build(BuildContext context) {
    Widget button(IconData icon, VoidCallback onTap, String tip) => InkWell(
      borderRadius: BorderRadius.circular(8),
      onTap: onTap,
      child: Tooltip(
        message: tip,
        child: Padding(
          padding: const EdgeInsets.all(6),
          child: Icon(icon, size: 16, color: AppColors.text),
        ),
      ),
    );
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 8),
      decoration: BoxDecoration(
        border: Border.all(color: AppColors.border),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          button(qty == 1 ? Icons.delete_outline : Icons.remove, onMinus, qty == 1 ? 'Remove' : 'Less'),
          Tooltip(
            message: 'Type the quantity',
            child: InkWell(
              borderRadius: BorderRadius.circular(6),
              onTap: onQty,
              child: Container(
                constraints: const BoxConstraints(minWidth: 26),
                padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 4),
                child: Text(
                  '$qty',
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ),
            ),
          ),
          button(Icons.add, onPlus, 'More'),
        ],
      ),
    );
  }
}

/// "Discount  [$|%]  [ 0.00 ]" — applied when the cashier presses Enter or leaves the field.
class _OrderDiscountRow extends ConsumerStatefulWidget {
  const _OrderDiscountRow({required this.enabled});

  final bool enabled;

  @override
  ConsumerState<_OrderDiscountRow> createState() => _OrderDiscountRowState();
}

class _OrderDiscountRowState extends ConsumerState<_OrderDiscountRow> {
  final _value = TextEditingController();
  final _focus = FocusNode();
  DiscountType _type = DiscountType.amount;

  @override
  void initState() {
    super.initState();
    _focus.addListener(() {
      if (!_focus.hasFocus) _apply();
    });
  }

  @override
  void dispose() {
    _value.dispose();
    _focus.dispose();
    super.dispose();
  }

  Future<void> _apply() async {
    if (!mounted) return;
    final cart = ref.read(cartProvider);
    final entered = parseDollars(_value.text) ?? 0; // $1.50 -> 150 cents; 10% -> 1000 basis points
    final current = cart.hasOrderDiscount ? (cart.discountType, cart.discountValue) : (null, 0);
    if (current == (entered > 0 ? _type : null, entered)) return;
    if (entered > 0 && !await approveCartAction(context, ref, 'Discount')) {
      _value.clear();
      return;
    }
    ref.read(cartProvider.notifier).setOrderDiscount(entered > 0 ? _type : null, entered);
  }

  @override
  Widget build(BuildContext context) {
    // keep the field in step when the cart is cleared or a sale completes
    ref.listen(cartProvider.select((c) => c.hasOrderDiscount), (_, has) {
      if (!has && !_focus.hasFocus) _value.clear();
    });

    Widget toggle(DiscountType type, String label) {
      final selected = _type == type;
      return InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: widget.enabled
            ? () {
                setState(() => _type = type);
                if (_value.text.isNotEmpty) _apply();
              }
            : null,
        child: Container(
          width: 34,
          height: 34,
          alignment: Alignment.center,
          decoration: BoxDecoration(color: selected ? AppColors.primary : Colors.transparent, borderRadius: BorderRadius.circular(8)),
          child: Text(
            label,
            style: TextStyle(color: selected ? Colors.white : AppColors.muted, fontWeight: FontWeight.w700),
          ),
        ),
      );
    }

    return Row(
      children: [
        const Text('Discount', style: TextStyle(fontSize: 15, color: AppColors.muted)),
        const Spacer(),
        Container(
          padding: const EdgeInsets.all(2),
          decoration: BoxDecoration(color: AppColors.page, borderRadius: BorderRadius.circular(10)),
          child: Row(mainAxisSize: MainAxisSize.min, children: [toggle(DiscountType.amount, r'$'), toggle(DiscountType.percent, '%')]),
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 110,
          child: TextField(
            controller: _value,
            focusNode: _focus,
            enabled: widget.enabled,
            textAlign: TextAlign.right,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            inputFormatters: decimalOnly,
            decoration: InputDecoration(
              hintText: '0.00',
              filled: true,
              fillColor: AppColors.page,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
              enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            ),
            onSubmitted: (_) => _apply(),
          ),
        ),
      ],
    );
  }
}

class DiscountResult {
  const DiscountResult(this.type, this.value);
  final DiscountType? type;
  final int value;
}

/// Percent or fixed amount. Returns type null to remove the discount.
class DiscountDialog extends StatefulWidget {
  const DiscountDialog({super.key, required this.title, this.type, this.value = 0});

  final String title;
  final DiscountType? type;
  final int value;

  static Future<DiscountResult?> show(BuildContext context, {required String title, DiscountType? type, int value = 0}) =>
      showDialog<DiscountResult>(
        context: context,
        builder: (_) => DiscountDialog(title: title, type: type, value: value),
      );

  @override
  State<DiscountDialog> createState() => _DiscountDialogState();
}

class _DiscountDialogState extends State<DiscountDialog> {
  late DiscountType _type = widget.type ?? DiscountType.percent;
  late final _amount = TextEditingController(text: widget.type == null ? '' : (widget.value / 100).toStringAsFixed(2));

  void _apply() {
    final number = double.tryParse(_amount.text.trim());
    if (number == null || number <= 0) return;
    // percent 12.5 -> 1250 basis points; amount $1.50 -> 150 cents
    Navigator.pop(context, DiscountResult(_type, (number * 100).round()));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SegmentedButton<DiscountType>(
            segments: const [
              ButtonSegment(value: DiscountType.percent, label: Text('Percent %')),
              ButtonSegment(value: DiscountType.amount, label: Text(r'Amount $')),
            ],
            selected: {_type},
            onSelectionChanged: (s) => setState(() => _type = s.first),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _amount,
            autofocus: true,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            inputFormatters: decimalOnly,
            decoration: InputDecoration(labelText: _type == DiscountType.percent ? 'Percent' : 'Amount (USD)'),
            onSubmitted: (_) => _apply(),
          ),
        ],
      ),
      actions: [
        if (widget.type != null)
          TextButton(onPressed: () => Navigator.pop(context, const DiscountResult(null, 0)), child: const Text('Remove')),
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: _apply, child: const Text('Apply')),
      ],
    );
  }
}
