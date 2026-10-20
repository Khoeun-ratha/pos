import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models.dart';
import '../state/session.dart';
import '../widgets/common.dart';

final customerSearchProvider = FutureProvider.autoDispose.family<List<Customer>, String>((ref, query) async {
  final data = await ref.watch(apiProvider).get('/api/customers', query: {if (query.isNotEmpty) 'q': query});
  return [for (final c in data) Customer.fromJson(c)];
});

/// Customer list. In pick mode, tapping a customer returns it.
class CustomersScreen extends ConsumerStatefulWidget {
  const CustomersScreen({super.key, this.pickMode = false, this.embedded = false});

  final bool pickMode;

  /// Shown inside the main menu, which already has a title bar.
  final bool embedded;

  @override
  ConsumerState<CustomersScreen> createState() => _CustomersScreenState();
}

class _CustomersScreenState extends ConsumerState<CustomersScreen> {
  String _query = '';

  Future<void> _add() async {
    final name = TextEditingController();
    final phone = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('New customer'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: name,
              autofocus: true,
              decoration: const InputDecoration(labelText: 'Name'),
            ),
            TextField(
              controller: phone,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(labelText: 'Phone'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Save')),
        ],
      ),
    );
    if (ok != true || name.text.trim().isEmpty) return;
    try {
      final data = await ref.read(apiProvider).post('/api/customers', {'name': name.text.trim(), 'phone': phone.text.trim()});
      final customer = Customer.fromJson(data);
      ref.invalidate(customerSearchProvider);
      if (mounted && widget.pickMode) Navigator.pop(context, customer);
    } catch (e) {
      if (mounted) showError(context, ref, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final customers = ref.watch(customerSearchProvider(_query));
    return Scaffold(
      appBar: widget.embedded ? null : AppBar(title: Text(widget.pickMode ? 'Choose customer' : 'Customers')),
      floatingActionButton: FloatingActionButton.extended(
        heroTag: null, // several menu screens with buttons are alive side by side
        onPressed: _add,
        icon: const Icon(Icons.person_add),
        label: const Text('New'),
      ),
      body: MaxWidth(
        width: 900,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(12),
              child: TextField(
                decoration: const InputDecoration(
                  hintText: 'Search name or phone',
                  prefixIcon: Icon(Icons.search),
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
                onChanged: (value) => setState(() => _query = value.trim()),
              ),
            ),
            Expanded(
              child: AsyncView<List<Customer>>(
                value: customers,
                onRetry: () => ref.invalidate(customerSearchProvider(_query)),
                builder: (list) => list.isEmpty
                    ? const Center(child: Text('No customers'))
                    : ListView.builder(
                        itemCount: list.length,
                        itemBuilder: (context, i) => ListTile(
                          leading: CircleAvatar(child: Text(list[i].name.characters.first.toUpperCase())),
                          title: Text(list[i].name),
                          subtitle: Text(list[i].phone ?? ''),
                          trailing: Text('${list[i].points} pts'),
                          onTap: widget.pickMode ? () => Navigator.pop(context, list[i]) : null,
                        ),
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
