import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/money.dart';
import '../state/sales.dart';
import '../state/session.dart';
import '../widgets/common.dart';

Future<void> confirmLogout(BuildContext context, WidgetRef ref) async {
  final pending = ref.read(offlineQueueProvider).length;
  final message = pending == 0
      ? 'Log out of this device?'
      : '$pending offline sale(s) are still waiting. They stay on this device and are sent after the next login.';
  if (await confirm(context, 'Log out', message, confirmText: 'Log out')) {
    await ref.read(sessionProvider.notifier).logout();
  }
}

/// Offline sales waiting to sync, and the logged-in account.
class MoreScreen extends ConsumerWidget {
  const MoreScreen({super.key});

  Future<void> _sync(BuildContext context, WidgetRef ref) async {
    try {
      final sent = await ref.read(offlineQueueProvider.notifier).sync();
      if (context.mounted) showMessage(context, sent == 0 ? 'Nothing was sent (still offline?)' : '$sent sale(s) sent');
    } catch (e) {
      if (context.mounted) showError(context, ref, e);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final user = session.user!;
    final pending = ref.watch(offlineQueueProvider);
    final failed = pending.where((p) => p.error != null).toList();

    return MaxWidth(
      width: 640,
      child: ListView(
        padding: const EdgeInsets.all(8),
        children: [
          Card(
            child: ListTile(
              leading: CircleAvatar(child: Text(user.displayName.characters.first.toUpperCase())),
              title: Text(user.displayName),
              subtitle: Text('${user.username} • ${user.role}\nServer: ${session.serverUrl}'),
              isThreeLine: true,
            ),
          ),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.cloud_upload),
                  title: const Text('Offline sales'),
                  subtitle: Text(pending.isEmpty ? 'Everything is synced' : '${pending.length} waiting to be sent'),
                  trailing: pending.isEmpty
                      ? null
                      : FilledButton.tonal(onPressed: () => _sync(context, ref), child: const Text('Sync now')),
                ),
                for (final sale in failed)
                  ListTile(
                    leading: Icon(Icons.error, color: Theme.of(context).colorScheme.error),
                    title: Text('${usd(sale.total)} • ${dateTime(sale.createdAt)}'),
                    subtitle: Text('Rejected: ${sale.error}'),
                    trailing: user.isManager
                        ? IconButton(
                            icon: const Icon(Icons.delete),
                            onPressed: () async {
                              if (await confirm(
                                context,
                                'Discard sale',
                                'Delete this rejected offline sale? Re-enter it if the goods left the shop.',
                              )) {
                                await ref.read(offlineQueueProvider.notifier).discard(sale.uuid);
                              }
                            },
                          )
                        : null,
                  ),
              ],
            ),
          ),
          Card(
            child: ListTile(leading: const Icon(Icons.logout), title: const Text('Log out'), onTap: () => confirmLogout(context, ref)),
          ),
        ],
      ),
    );
  }
}
