typedef Json = Map<String, dynamic>;

class User {
  const User({required this.id, required this.username, required this.fullName, required this.role});

  factory User.fromJson(Json j) => User(id: j['id'], username: j['username'], fullName: j['full_name'] ?? '', role: j['role']);

  final int id;
  final String username, fullName, role;

  String get displayName => fullName.isEmpty ? username : fullName;
  bool get isManager => role == 'admin' || role == 'manager';
  bool get isAdmin => role == 'admin';

  Json toJson() => {'id': id, 'username': username, 'full_name': fullName, 'role': role};
}

class StoreSettings {
  const StoreSettings({
    this.storeName = 'POS',
    this.storeAddress = '',
    this.storePhone = '',
    this.taxRateBp = 0,
    this.taxInclusive = false,
    this.exchangeRate = 4100,
    this.receiptFooter = '',
    this.allowNegativeStock = true,
    this.loyaltyPointsPerUsd = 1,
  });

  factory StoreSettings.fromJson(Json j) => StoreSettings(
    storeName: j['store_name'],
    storeAddress: j['store_address'],
    storePhone: j['store_phone'],
    taxRateBp: j['tax_rate_bp'],
    taxInclusive: j['tax_inclusive'],
    exchangeRate: j['exchange_rate'],
    receiptFooter: j['receipt_footer'],
    allowNegativeStock: j['allow_negative_stock'],
    loyaltyPointsPerUsd: j['loyalty_points_per_usd'],
  );

  final String storeName, storeAddress, storePhone, receiptFooter;
  final int taxRateBp, exchangeRate, loyaltyPointsPerUsd;
  final bool taxInclusive, allowNegativeStock;

  Json toJson() => {
    'store_name': storeName,
    'store_address': storeAddress,
    'store_phone': storePhone,
    'tax_rate_bp': taxRateBp,
    'tax_inclusive': taxInclusive,
    'exchange_rate': exchangeRate,
    'receipt_footer': receiptFooter,
    'allow_negative_stock': allowNegativeStock,
    'loyalty_points_per_usd': loyaltyPointsPerUsd,
  };
}

class Category {
  const Category({required this.id, required this.name});
  factory Category.fromJson(Json j) => Category(id: j['id'], name: j['name']);
  final int id;
  final String name;
  Json toJson() => {'id': id, 'name': name, 'sort_order': 0};
}

class Product {
  const Product({
    required this.id,
    required this.name,
    this.sku,
    this.barcode,
    this.categoryId,
    this.categoryName,
    required this.price,
    this.cost = 0,
    this.trackStock = true,
    this.stockQty = 0,
    this.lowStockThreshold = 5,
    this.isActive = true,
    this.imageUrl,
  });

  factory Product.fromJson(Json j) => Product(
    id: j['id'],
    name: j['name'],
    sku: j['sku'],
    barcode: j['barcode'],
    categoryId: j['category_id'],
    categoryName: j['category_name'],
    price: j['price'],
    cost: j['cost'] ?? 0,
    trackStock: j['track_stock'] ?? true,
    stockQty: j['stock_qty'] ?? 0,
    lowStockThreshold: j['low_stock_threshold'] ?? 5,
    isActive: j['is_active'] ?? true,
    imageUrl: j['image_url'],
  );

  final int id;
  final String name;
  final String? sku, barcode, categoryName;
  final int? categoryId;
  final int price, cost, stockQty, lowStockThreshold;
  final bool trackStock, isActive;

  /// Path on the server, e.g. /uploads/products/12-3f9a.webp; null when there is no photo.
  final String? imageUrl;

  bool get isLowStock => trackStock && stockQty <= lowStockThreshold;

  Json toJson() => {
    'id': id,
    'name': name,
    'sku': sku,
    'barcode': barcode,
    'category_id': categoryId,
    'category_name': categoryName,
    'price': price,
    'cost': cost,
    'track_stock': trackStock,
    'stock_qty': stockQty,
    'low_stock_threshold': lowStockThreshold,
    'is_active': isActive,
    'image_url': imageUrl,
  };

  /// Body for POST/PUT /api/products.
  Json toInput() => {
    'name': name,
    'sku': sku,
    'barcode': barcode,
    'category_id': categoryId,
    'price': price,
    'cost': cost,
    'track_stock': trackStock,
    'low_stock_threshold': lowStockThreshold,
    'is_active': isActive,
  };
}

class Customer {
  const Customer({required this.id, required this.name, this.phone, this.points = 0});
  factory Customer.fromJson(Json j) => Customer(id: j['id'], name: j['name'], phone: j['phone'], points: j['points'] ?? 0);
  final int id;
  final String name;
  final String? phone;
  final int points;
}

class SaleSummary {
  const SaleSummary({
    required this.id,
    required this.receiptNo,
    required this.cashierName,
    this.customerName,
    required this.total,
    required this.refundedTotal,
    required this.status,
    required this.createdAt,
  });

  factory SaleSummary.fromJson(Json j) => SaleSummary(
    id: j['id'],
    receiptNo: j['receipt_no'],
    cashierName: j['cashier_name'],
    customerName: j['customer_name'],
    total: j['total'],
    refundedTotal: j['refunded_total'],
    status: j['status'],
    createdAt: DateTime.parse(j['created_at']),
  );

  final int id, total, refundedTotal;
  final String receiptNo, cashierName, status;
  final String? customerName;
  final DateTime createdAt;
}

class SaleItem {
  const SaleItem({
    required this.id,
    required this.productName,
    required this.qty,
    required this.unitPrice,
    required this.discount,
    required this.lineTotal,
    required this.refundedQty,
  });

  factory SaleItem.fromJson(Json j) => SaleItem(
    id: j['id'],
    productName: j['product_name'],
    qty: j['qty'],
    unitPrice: j['unit_price'],
    discount: j['discount'],
    lineTotal: j['line_total'],
    refundedQty: j['refunded_qty'],
  );

  final int id, qty, unitPrice, discount, lineTotal, refundedQty;
  final String productName;
  int get refundableQty => qty - refundedQty;
}

class Payment {
  const Payment({required this.method, required this.currency, required this.amount, this.amountUsd = 0});
  factory Payment.fromJson(Json j) =>
      Payment(method: j['method'], currency: j['currency'], amount: j['amount'], amountUsd: j['amount_usd']);
  final String method, currency;
  final int amount, amountUsd;
  Json toJson() => {'method': method, 'currency': currency, 'amount': amount};
}

class Sale {
  const Sale({
    required this.id,
    required this.receiptNo,
    required this.cashierName,
    this.customerName,
    required this.subtotal,
    required this.discountTotal,
    required this.taxTotal,
    required this.total,
    required this.paidTotal,
    required this.changeDue,
    required this.changeDueKhr,
    required this.refundedTotal,
    required this.status,
    required this.createdAt,
    required this.items,
    required this.payments,
  });

  factory Sale.fromJson(Json j) => Sale(
    id: j['id'],
    receiptNo: j['receipt_no'],
    cashierName: j['cashier_name'],
    customerName: j['customer_name'],
    subtotal: j['subtotal'],
    discountTotal: j['discount_total'],
    taxTotal: j['tax_total'],
    total: j['total'],
    paidTotal: j['paid_total'],
    changeDue: j['change_due'],
    changeDueKhr: j['change_due_khr'],
    refundedTotal: j['refunded_total'],
    status: j['status'],
    createdAt: DateTime.parse(j['created_at']),
    items: [for (final i in j['items']) SaleItem.fromJson(i)],
    payments: [for (final p in j['payments']) Payment.fromJson(p)],
  );

  final int id, subtotal, discountTotal, taxTotal, total, paidTotal, changeDue, changeDueKhr, refundedTotal;
  final String receiptNo, cashierName, status;
  final String? customerName;
  final DateTime createdAt;
  final List<SaleItem> items;
  final List<Payment> payments;

  bool get canRefund => items.any((i) => i.refundableQty > 0);
}

class ShiftReport {
  const ShiftReport({
    required this.id,
    required this.cashierName,
    required this.openedAt,
    this.closedAt,
    required this.isOpen,
    required this.salesCount,
    required this.openingCash,
    required this.cashSales,
    required this.cardSales,
    required this.khqrSales,
    required this.cashIn,
    required this.cashOut,
    required this.cashRefunds,
    required this.expectedCash,
    this.countedCash,
    this.variance,
  });

  factory ShiftReport.fromJson(Json j) => ShiftReport(
    id: j['id'],
    cashierName: j['cashier_name'],
    openedAt: DateTime.parse(j['opened_at']),
    closedAt: j['closed_at'] == null ? null : DateTime.parse(j['closed_at']),
    isOpen: j['is_open'],
    salesCount: j['sales_count'],
    openingCash: j['opening_cash'],
    cashSales: j['cash_sales'],
    cardSales: j['card_sales'],
    khqrSales: j['khqr_sales'],
    cashIn: j['cash_in'],
    cashOut: j['cash_out'],
    cashRefunds: j['cash_refunds'],
    expectedCash: j['expected_cash'],
    countedCash: j['counted_cash'],
    variance: j['variance'],
  );

  final int id, salesCount, openingCash, cashSales, cardSales, khqrSales, cashIn, cashOut, cashRefunds, expectedCash;
  final int? countedCash, variance;
  final String cashierName;
  final DateTime openedAt;
  final DateTime? closedAt;
  final bool isOpen;
}

class NameAmount {
  const NameAmount(this.name, this.qty, this.count, this.amount);
  factory NameAmount.fromJson(Json j) => NameAmount(j['name'], j['qty'], j['count'], j['amount']);
  final String name;
  final int qty, count, amount;
}

class ReportSummary {
  const ReportSummary({
    required this.salesCount,
    required this.grossSales,
    required this.refunds,
    required this.netSales,
    required this.tax,
    required this.discounts,
    required this.profit,
    required this.averageSale,
    required this.byPayment,
    required this.byCategory,
    required this.topProducts,
    required this.byDay,
  });

  factory ReportSummary.fromJson(Json j) => ReportSummary(
    salesCount: j['sales_count'],
    grossSales: j['gross_sales'],
    refunds: j['refunds'],
    netSales: j['net_sales'],
    tax: j['tax'],
    discounts: j['discounts'],
    profit: j['profit'],
    averageSale: j['average_sale'],
    byPayment: [for (final e in j['by_payment']) NameAmount.fromJson(e)],
    byCategory: [for (final e in j['by_category']) NameAmount.fromJson(e)],
    topProducts: [for (final e in j['top_products']) NameAmount.fromJson(e)],
    byDay: [for (final e in j['by_day']) (day: DateTime.parse(e['day']), amount: e['amount'] as int)],
  );

  final int salesCount, grossSales, refunds, netSales, tax, discounts, profit, averageSale;
  final List<NameAmount> byPayment, byCategory, topProducts;
  final List<({DateTime day, int amount})> byDay;
}
