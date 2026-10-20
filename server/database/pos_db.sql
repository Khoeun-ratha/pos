-- POS database for MySQL 8. Generated from server/migrations (alembic upgrade head --sql).
-- Run in Navicat: right-click the MySQL connection > Execute SQL File > this file.
-- Afterwards start the POS service once: it sees the tables and adds the demo data (POS_SEED=true in .env).

CREATE DATABASE IF NOT EXISTS `pos_db` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `pos_db`;
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 4f7252be595b

CREATE TABLE categories (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    name VARCHAR(100) NOT NULL, 
    sort_order INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (name)
);

CREATE TABLE customers (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    name VARCHAR(100) NOT NULL, 
    phone VARCHAR(30), 
    email VARCHAR(100), 
    points INTEGER NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (phone)
);

CREATE TABLE settings (
    `key` VARCHAR(50) NOT NULL, 
    value TEXT NOT NULL, 
    PRIMARY KEY (`key`)
);

CREATE TABLE users (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    username VARCHAR(50) NOT NULL, 
    full_name VARCHAR(100) NOT NULL, 
    password_hash VARCHAR(100) NOT NULL, 
    pin_hash VARCHAR(100), 
    `role` VARCHAR(20) NOT NULL, 
    is_active BOOL NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE TABLE audit_logs (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    user_id INTEGER, 
    action VARCHAR(50) NOT NULL, 
    detail TEXT NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_audit_logs_action ON audit_logs (action);

CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);

CREATE TABLE products (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    name VARCHAR(200) NOT NULL, 
    sku VARCHAR(64), 
    barcode VARCHAR(64), 
    category_id INTEGER, 
    price INTEGER NOT NULL, 
    cost INTEGER NOT NULL, 
    track_stock BOOL NOT NULL, 
    stock_qty INTEGER NOT NULL, 
    low_stock_threshold INTEGER NOT NULL, 
    is_active BOOL NOT NULL, 
    created_at DATETIME NOT NULL, 
    updated_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(category_id) REFERENCES categories (id) ON DELETE SET NULL, 
    UNIQUE (sku)
);

CREATE UNIQUE INDEX ix_products_barcode ON products (barcode);

CREATE INDEX ix_products_name ON products (name);

CREATE TABLE shifts (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    user_id INTEGER NOT NULL, 
    opened_at DATETIME NOT NULL, 
    closed_at DATETIME, 
    opening_cash INTEGER NOT NULL, 
    expected_cash INTEGER, 
    counted_cash INTEGER, 
    note TEXT, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE cash_movements (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    shift_id INTEGER NOT NULL, 
    user_id INTEGER NOT NULL, 
    amount INTEGER NOT NULL, 
    reason VARCHAR(200) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(shift_id) REFERENCES shifts (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE sales (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    receipt_no VARCHAR(30) NOT NULL, 
    client_uuid VARCHAR(64), 
    user_id INTEGER NOT NULL, 
    shift_id INTEGER, 
    customer_id INTEGER, 
    subtotal INTEGER NOT NULL, 
    discount_total INTEGER NOT NULL, 
    tax_total INTEGER NOT NULL, 
    total INTEGER NOT NULL, 
    paid_total INTEGER NOT NULL, 
    change_due INTEGER NOT NULL, 
    exchange_rate INTEGER NOT NULL, 
    refunded_total INTEGER NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    note TEXT, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(customer_id) REFERENCES customers (id), 
    FOREIGN KEY(shift_id) REFERENCES shifts (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    UNIQUE (client_uuid)
);

CREATE INDEX ix_sales_created_at ON sales (created_at);

CREATE UNIQUE INDEX ix_sales_receipt_no ON sales (receipt_no);

CREATE TABLE stock_movements (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    product_id INTEGER NOT NULL, 
    `change` INTEGER NOT NULL, 
    balance INTEGER NOT NULL, 
    kind VARCHAR(20) NOT NULL, 
    reference VARCHAR(50), 
    note VARCHAR(200), 
    user_id INTEGER, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_stock_movements_product_id ON stock_movements (product_id);

CREATE TABLE payments (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    sale_id INTEGER NOT NULL, 
    method VARCHAR(20) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    amount INTEGER NOT NULL, 
    amount_usd INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(sale_id) REFERENCES sales (id) ON DELETE CASCADE
);

CREATE TABLE refunds (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    sale_id INTEGER NOT NULL, 
    user_id INTEGER NOT NULL, 
    approved_by_id INTEGER NOT NULL, 
    shift_id INTEGER, 
    amount INTEGER NOT NULL, 
    reason VARCHAR(200) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(approved_by_id) REFERENCES users (id), 
    FOREIGN KEY(sale_id) REFERENCES sales (id), 
    FOREIGN KEY(shift_id) REFERENCES shifts (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE sale_items (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    sale_id INTEGER NOT NULL, 
    product_id INTEGER, 
    product_name VARCHAR(200) NOT NULL, 
    qty INTEGER NOT NULL, 
    unit_price INTEGER NOT NULL, 
    unit_cost INTEGER NOT NULL, 
    discount INTEGER NOT NULL, 
    tax INTEGER NOT NULL, 
    line_total INTEGER NOT NULL, 
    refunded_qty INTEGER NOT NULL, 
    refunded_amount INTEGER NOT NULL, 
    note VARCHAR(200), 
    PRIMARY KEY (id), 
    FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE SET NULL, 
    FOREIGN KEY(sale_id) REFERENCES sales (id) ON DELETE CASCADE
);

CREATE TABLE refund_items (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    refund_id INTEGER NOT NULL, 
    sale_item_id INTEGER NOT NULL, 
    qty INTEGER NOT NULL, 
    amount INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(refund_id) REFERENCES refunds (id) ON DELETE CASCADE, 
    FOREIGN KEY(sale_item_id) REFERENCES sale_items (id)
);

INSERT INTO alembic_version (version_num) VALUES ('4f7252be595b');

