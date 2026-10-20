import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// One light design for every screen: grey page, white rounded cards, blue accent, Inter font.
abstract final class AppColors {
  static const primary = Color(0xFF2563EB);
  static const primarySoft = Color(0xFFEFF6FF);
  static const page = Color(0xFFF1F5F9);
  static const card = Colors.white;
  static const border = Color(0xFFE2E8F0);
  static const text = Color(0xFF0F172A);
  static const muted = Color(0xFF64748B);
  static const price = Color(0xFFE11D48);
  static const success = Color(0xFF16A34A);
  static const successSoft = Color(0xFFDCFCE7);
  static const warning = Color(0xFFD97706);
  static const warningSoft = Color(0xFFFEF3C7);
}

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(seedColor: AppColors.primary, brightness: Brightness.light).copyWith(
    primary: AppColors.primary,
    onSurface: AppColors.text,
    surface: AppColors.card,
    outline: AppColors.muted,
    outlineVariant: AppColors.border,
  );
  final rounded = RoundedRectangleBorder(borderRadius: BorderRadius.circular(12));
  OutlineInputBorder border(Color color, [double width = 1]) => OutlineInputBorder(
    borderRadius: BorderRadius.circular(12),
    borderSide: BorderSide(color: color, width: width),
  );

  final base = ThemeData(
    colorScheme: scheme,
    useMaterial3: true,
    scaffoldBackgroundColor: AppColors.page,
    fontFamily: GoogleFonts.inter().fontFamily,
  );
  return base.copyWith(
    textTheme: base.textTheme.apply(bodyColor: AppColors.text, displayColor: AppColors.text),
    appBarTheme: AppBarTheme(
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.white,
      foregroundColor: AppColors.text,
      elevation: 0,
      scrolledUnderElevation: 0,
      titleTextStyle: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w700, color: AppColors.text),
      shape: const Border(bottom: BorderSide(color: AppColors.border)),
    ),
    cardTheme: CardThemeData(
      color: AppColors.card,
      surfaceTintColor: AppColors.card,
      elevation: 0,
      margin: const EdgeInsets.symmetric(vertical: 4),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: const BorderSide(color: AppColors.border),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      isDense: true,
      filled: true,
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: border(AppColors.border),
      enabledBorder: border(AppColors.border),
      focusedBorder: border(AppColors.primary, 1.6),
      hintStyle: const TextStyle(color: AppColors.muted),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        shape: rounded,
        minimumSize: const Size(64, 48),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        shape: rounded,
        minimumSize: const Size(64, 48),
        side: const BorderSide(color: AppColors.border),
      ),
    ),
    textButtonTheme: TextButtonThemeData(style: TextButton.styleFrom(shape: rounded)),
    segmentedButtonTheme: SegmentedButtonThemeData(style: SegmentedButton.styleFrom(shape: rounded)),
    chipTheme: base.chipTheme.copyWith(
      shape: StadiumBorder(side: BorderSide(color: AppColors.border)),
      backgroundColor: Colors.white,
    ),
    dividerTheme: const DividerThemeData(color: AppColors.border, space: 1),
    listTileTheme: const ListTileThemeData(iconColor: AppColors.muted),
    dialogTheme: DialogThemeData(
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
    ),
    bottomSheetTheme: const BottomSheetThemeData(backgroundColor: Colors.white, surfaceTintColor: Colors.white),
    drawerTheme: const DrawerThemeData(backgroundColor: Colors.white, surfaceTintColor: Colors.white),
    snackBarTheme: SnackBarThemeData(behavior: SnackBarBehavior.floating, shape: rounded),
  );
}

/// Coloured picture area for products without photos: one colour and icon per category.
({Color background, Color foreground, IconData icon}) categoryArt(String? category) {
  final name = (category ?? '').toLowerCase();
  if (name.contains('drink')) return (background: const Color(0xFFDBEAFE), foreground: const Color(0xFF1D4ED8), icon: Icons.local_drink);
  if (name.contains('snack')) return (background: const Color(0xFFFEF3C7), foreground: const Color(0xFFB45309), icon: Icons.cookie);
  if (name.contains('grocer')) return (background: const Color(0xFFDCFCE7), foreground: const Color(0xFF15803D), icon: Icons.rice_bowl);
  if (name.contains('care')) return (background: const Color(0xFFFCE7F3), foreground: const Color(0xFFBE185D), icon: Icons.spa);
  if (name.contains('house')) {
    return (background: const Color(0xFFEDE9FE), foreground: const Color(0xFF6D28D9), icon: Icons.cleaning_services);
  }
  return (background: const Color(0xFFE2E8F0), foreground: const Color(0xFF475569), icon: Icons.inventory_2);
}
