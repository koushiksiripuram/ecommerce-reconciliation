.\.venv\Scripts\python.exe : INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
At line:15 char:4098
+ ... yContinue'; .\.venv\Scripts\python.exe -m alembic upgrade head --sql  ...
+                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (INFO  [alembic....PostgresqlImpl.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
INFO  [alembic.runtime.migration] Generating static SQL
INFO  [alembic.runtime.migration] Will assume transactional DDL.
BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

INFO  [alembic.runtime.migration] Running upgrade  -> 6e9f95855415, create initial schema
-- Running upgrade  -> 6e9f95855415

CREATE TABLE orders (
    id SERIAL NOT NULL, 
    external_order_id VARCHAR(128) NOT NULL, 
    marketplace VARCHAR(64) NOT NULL, 
    order_date TIMESTAMP WITH TIME ZONE NOT NULL, 
    status VARCHAR(9) DEFAULT 'pending' NOT NULL, 
    currency VARCHAR(3) DEFAULT 'INR' NOT NULL, 
    gross_amount NUMERIC(14, 2) DEFAULT 0 NOT NULL, 
    discount_amount NUMERIC(14, 2) DEFAULT 0 NOT NULL, 
    shipping_amount NUMERIC(14, 2) DEFAULT 0 NOT NULL, 
    tax_amount NUMERIC(14, 2) DEFAULT 0 NOT NULL, 
    net_amount NUMERIC(14, 2) DEFAULT 0 NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_orders PRIMARY KEY (id), 
    CONSTRAINT uq_orders_marketplace_external_order_id UNIQUE (marketplace, external_order_id), 
    CONSTRAINT ck_orders_order_status CHECK (status IN ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled', 'returned'))
);

CREATE INDEX ix_orders_marketplace_order_date ON orders (marketplace, order_date);

CREATE TABLE roles (
    id SERIAL NOT NULL, 
    name VARCHAR(50) NOT NULL, 
    description TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_roles PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_roles_name ON roles (name);

INSERT INTO roles (name, description) VALUES ('finance_executive', 'Finance executive handling day-to-day reconciliation.');

INSERT INTO roles (name, description) VALUES ('co_founder', 'Co-founder with full visibility across reconciliation results.');

CREATE TABLE users (
    id SERIAL NOT NULL, 
    email VARCHAR(255) NOT NULL, 
    full_name VARCHAR(255) NOT NULL, 
    role_id INTEGER NOT NULL, 
    is_active BOOLEAN DEFAULT (true) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_users PRIMARY KEY (id), 
    CONSTRAINT fk_users_role_id_roles FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE INDEX ix_users_role_id ON users (role_id);

CREATE TABLE uploaded_files (
    id SERIAL NOT NULL, 
    original_filename VARCHAR(512) NOT NULL, 
    storage_path VARCHAR(1024), 
    content_type VARCHAR(128), 
    size_bytes BIGINT, 
    checksum_sha256 VARCHAR(64), 
    uploaded_by_user_id INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_uploaded_files PRIMARY KEY (id), 
    CONSTRAINT fk_uploaded_files_uploaded_by_user_id_users FOREIGN KEY(uploaded_by_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_uploaded_files_checksum_sha256 ON uploaded_files (checksum_sha256);

CREATE INDEX ix_uploaded_files_uploaded_by_user_id ON uploaded_files (uploaded_by_user_id);

CREATE TABLE import_batches (
    id SERIAL NOT NULL, 
    uploaded_file_id INTEGER NOT NULL, 
    source_type VARCHAR(11) NOT NULL, 
    marketplace VARCHAR(64), 
    status VARCHAR(10) DEFAULT 'pending' NOT NULL, 
    total_rows INTEGER DEFAULT 0 NOT NULL, 
    processed_rows INTEGER DEFAULT 0 NOT NULL, 
    failed_rows INTEGER DEFAULT 0 NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    error_message TEXT, 
    created_by_user_id INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_import_batches PRIMARY KEY (id), 
    CONSTRAINT fk_import_batches_created_by_user_id_users FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE SET NULL, 
    CONSTRAINT fk_import_batches_uploaded_file_id_uploaded_files FOREIGN KEY(uploaded_file_id) REFERENCES uploaded_files (id) ON DELETE CASCADE, 
    CONSTRAINT ck_import_batches_import_source_type CHECK (source_type IN ('orders', 'settlements', 'returns', 'claims')), 
    CONSTRAINT ck_import_batches_import_batch_status CHECK (status IN ('pending', 'processing', 'completed', 'failed'))
);

CREATE INDEX ix_import_batches_created_by_user_id ON import_batches (created_by_user_id);

CREATE INDEX ix_import_batches_marketplace ON import_batches (marketplace);

CREATE INDEX ix_import_batches_source_status ON import_batches (source_type, status);

CREATE INDEX ix_import_batches_uploaded_file_id ON import_batches (uploaded_file_id);

CREATE TABLE raw_imported_records (
    id SERIAL NOT NULL, 
    import_batch_id INTEGER NOT NULL, 
    row_number INTEGER NOT NULL, 
    external_reference VARCHAR(128), 
    raw_data JSON NOT NULL, 
    is_valid BOOLEAN DEFAULT (true) NOT NULL, 
    validation_errors TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_raw_imported_records PRIMARY KEY (id), 
    CONSTRAINT fk_raw_imported_records_import_batch_id_import_batches FOREIGN KEY(import_batch_id) REFERENCES import_batches (id) ON DELETE CASCADE
);

CREATE INDEX ix_raw_imported_records_batch_row ON raw_imported_records (import_batch_id, row_number);

CREATE INDEX ix_raw_imported_records_external_reference ON raw_imported_records (external_reference);

INFO  [alembic.runtime.migration] Running upgrade 6e9f95855415 -> 533d946dd507, add password hash to users
INFO  [alembic.runtime.migration] Running upgrade 533d946dd507 -> a4f1c8b9d2e3, add import mapping support
INFO  [alembic.runtime.migration] Running upgrade a4f1c8b9d2e3 -> b7c2e1f4a6d9, add reconciliation engine
CREATE INDEX ix_raw_imported_records_import_batch_id ON raw_imported_records (import_batch_id);

CREATE TABLE settlement_records (
    id SERIAL NOT NULL, 
    marketplace VARCHAR(64) NOT NULL, 
    external_reference VARCHAR(128) NOT NULL, 
    order_id INTEGER, 
    import_batch_id INTEGER, 
    raw_record_id INTEGER, 
    transaction_type VARCHAR(10) NOT NULL, 
    settlement_date TIMESTAMP WITH TIME ZONE NOT NULL, 
    currency VARCHAR(3) DEFAULT 'INR' NOT NULL, 
    gross_amount NUMERIC(14, 2) DEFAULT 0 NOT NULL, 
    fee_amount NUMERIC(14, 2) DEFAULT 0 NOT NULL, 
    tax_amount NUMERIC(14, 2) DEFAULT 0 NOT NULL, 
    net_amount NUMERIC(14, 2) DEFAULT 0 NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_settlement_records PRIMARY KEY (id), 
    CONSTRAINT fk_settlement_records_import_batch_id_import_batches FOREIGN KEY(import_batch_id) REFERENCES import_batches (id) ON DELETE SET NULL, 
    CONSTRAINT fk_settlement_records_order_id_orders FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE SET NULL, 
    CONSTRAINT fk_settlement_records_raw_record_id_raw_imported_records FOREIGN KEY(raw_record_id) REFERENCES raw_imported_records (id) ON DELETE SET NULL, 
    CONSTRAINT uq_settlement_records_marketplace_external UNIQUE (marketplace, external_reference), 
    CONSTRAINT ck_settlement_records_settlement_transaction_type CHECK (transaction_type IN ('sale', 'refund', 'chargeback', 'fee', 'adjustment'))
);

CREATE INDEX ix_settlement_records_import_batch_id ON settlement_records (import_batch_id);

CREATE INDEX ix_settlement_records_marketplace_settlement_date ON settlement_records (marketplace, settlement_date);

CREATE INDEX ix_settlement_records_order_id ON settlement_records (order_id);

CREATE INDEX ix_settlement_records_raw_record_id ON settlement_records (raw_record_id);

CREATE TABLE reconciliation_results (
    id SERIAL NOT NULL, 
    order_id INTEGER, 
    settlement_record_id INTEGER, 
    import_batch_id INTEGER, 
    status VARCHAR(21) NOT NULL, 
    currency VARCHAR(3) DEFAULT 'INR' NOT NULL, 
    expected_amount NUMERIC(14, 2) DEFAULT 0 NOT NULL, 
    actual_amount NUMERIC(14, 2) DEFAULT 0 NOT NULL, 
    difference_amount NUMERIC(14, 2) DEFAULT 0 NOT NULL, 
    notes TEXT, 
    reconciled_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_reconciliation_results PRIMARY KEY (id), 
    CONSTRAINT fk_reconciliation_results_import_batch_id_import_batches FOREIGN KEY(import_batch_id) REFERENCES import_batches (id) ON DELETE SET NULL, 
    CONSTRAINT fk_reconciliation_results_order_id_orders FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE CASCADE, 
    CONSTRAINT fk_reconciliation_results_settlement_record_id_settleme_6a7f FOREIGN KEY(settlement_record_id) REFERENCES settlement_records (id) ON DELETE CASCADE, 
    CONSTRAINT ck_reconciliation_results_reconciliation_status CHECK (status IN ('matched', 'amount_mismatch', 'missing_in_settlement', 'missing_in_orders', 'partial', 'unmatched'))
);

CREATE INDEX ix_reconciliation_results_import_batch_id ON reconciliation_results (import_batch_id);

CREATE INDEX ix_reconciliation_results_order_id ON reconciliation_results (order_id);

CREATE INDEX ix_reconciliation_results_run_status ON reconciliation_results (import_batch_id, status);

CREATE INDEX ix_reconciliation_results_settlement_record_id ON reconciliation_results (settlement_record_id);

CREATE INDEX ix_reconciliation_results_status ON reconciliation_results (status);

INSERT INTO alembic_version (version_num) VALUES ('6e9f95855415') RETURNING alembic_version.version_num;

-- Running upgrade 6e9f95855415 -> 533d946dd507

ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NOT NULL;

UPDATE alembic_version SET version_num='533d946dd507' WHERE alembic_version.version_num = '6e9f95855415';

-- Running upgrade 533d946dd507 -> a4f1c8b9d2e3

CREATE TABLE import_column_mappings (
    id SERIAL NOT NULL, 
    source_type VARCHAR(16) NOT NULL, 
    partner VARCHAR(64) NOT NULL, 
    mapping JSON NOT NULL, 
    created_by_user_id INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_import_column_mappings PRIMARY KEY (id), 
    CONSTRAINT fk_import_column_mappings_created_by_user_id_users FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE SET NULL, 
    CONSTRAINT uq_import_column_mappings_source_type_partner UNIQUE (source_type, partner), 
    CONSTRAINT ck_import_column_mappings_import_source_type CHECK (source_type IN ('orders', 'settlements', 'cod_remittances', 'freight_invoices', 'returns', 'claims'))
);

CREATE INDEX ix_import_column_mappings_created_by_user_id ON import_column_mappings (created_by_user_id);

ALTER TABLE import_batches ADD COLUMN column_mapping JSON;

ALTER TABLE raw_imported_records ADD COLUMN normalized_data JSON;

ALTER TABLE import_batches DROP CONSTRAINT ck_import_batches_import_source_type;

ALTER TABLE import_batches DROP CONSTRAINT ck_import_batches_import_batch_status;

ALTER TABLE import_batches ALTER COLUMN source_type TYPE VARCHAR(16);

ALTER TABLE import_batches ALTER COLUMN status TYPE VARCHAR(16);

ALTER TABLE import_batches ALTER COLUMN status SET DEFAULT 'uploaded';

ALTER TABLE import_batches ADD CONSTRAINT ck_import_batches_import_source_type CHECK (source_type IN ('orders', 'settlements', 'cod_remittances', 'freight_invoices', 'returns', 'claims'));

ALTER TABLE import_batches ADD CONSTRAINT ck_import_batches_import_batch_status CHECK (status IN ('uploaded', 'mapping_required', 'processing', 'completed', 'failed'));

UPDATE alembic_version SET version_num='a4f1c8b9d2e3' WHERE alembic_version.version_num = '533d946dd507';

-- Running upgrade a4f1c8b9d2e3 -> b7c2e1f4a6d9

CREATE TABLE freight_rate_cards (
    id SERIAL NOT NULL, 
    courier VARCHAR(64) NOT NULL, 
    zone VARCHAR(32) NOT NULL, 
    service_type VARCHAR(7) DEFAULT 'forward' NOT NULL, 
    payment_type VARCHAR(7) DEFAULT 'prepaid' NOT NULL, 
    min_weight_grams NUMERIC(10, 3) DEFAULT 0 NOT NULL, 
    max_weight_grams NUMERIC(10, 3) NOT NULL, 
    rate NUMERIC(14, 2) NOT NULL, 
    currency VARCHAR(3) DEFAULT 'INR' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_freight_rate_cards PRIMARY KEY (id), 
    CONSTRAINT uq_freight_rate_cards_slab UNIQUE (courier, zone, service_type, payment_type, min_weight_grams), 
    CONSTRAINT ck_freight_rate_cards_freight_service_type CHECK (service_type IN ('forward', 'reverse')), 
    CONSTRAINT ck_freight_rate_cards_freight_payment_type CHECK (payment_type IN ('prepaid', 'cod'))
);

INFO  [alembic.runtime.migration] Running upgrade b7c2e1f4a6d9 -> c1d2e3f4a5b6, add reconciliation run history
CREATE INDEX ix_freight_rate_cards_courier ON freight_rate_cards (courier);

ALTER TABLE settlement_records ADD COLUMN order_reference VARCHAR(128);

CREATE INDEX ix_settlement_records_order_reference ON settlement_records (order_reference);

ALTER TABLE reconciliation_results DROP CONSTRAINT ck_reconciliation_results_reconciliation_status;

ALTER TABLE reconciliation_results ALTER COLUMN status TYPE VARCHAR(17);

ALTER TABLE reconciliation_results ADD COLUMN expected_freight_amount NUMERIC(14, 2) DEFAULT 0 NOT NULL;

ALTER TABLE reconciliation_results ADD COLUMN actual_freight_amount NUMERIC(14, 2) DEFAULT 0 NOT NULL;

ALTER TABLE reconciliation_results ADD COLUMN tcs_amount NUMERIC(14, 2) DEFAULT 0 NOT NULL;

ALTER TABLE reconciliation_results ADD COLUMN tds_amount NUMERIC(14, 2) DEFAULT 0 NOT NULL;

ALTER TABLE reconciliation_results ADD COLUMN issues JSON;

ALTER TABLE reconciliation_results ADD CONSTRAINT ck_reconciliation_results_reconciliation_status CHECK (status IN ('settled', 'short_paid', 'unpaid_past_due', 'pending', 'missing_in_orders'));

UPDATE alembic_version SET version_num='b7c2e1f4a6d9' WHERE alembic_version.version_num = 'a4f1c8b9d2e3';

-- Running upgrade b7c2e1f4a6d9 -> c1d2e3f4a5b6

CREATE TABLE reconciliation_runs (
    id SERIAL NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    triggered_by_user_id INTEGER, 
    source_watermark INTEGER, 
    orders_reconciled INTEGER DEFAULT 0 NOT NULL, 
    settlements_matched INTEGER DEFAULT 0 NOT NULL, 
    unmatched_settlements INTEGER DEFAULT 0 NOT NULL, 
    results_created INTEGER DEFAULT 0 NOT NULL, 
    by_status JSON, 
    is_current BOOLEAN DEFAULT false NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_reconciliation_runs PRIMARY KEY (id), 
    CONSTRAINT fk_reconciliation_runs_triggered_by_user_id_users FOREIGN KEY(triggered_by_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_reconciliation_runs_triggered_by_user_id ON reconciliation_runs (triggered_by_user_id);

CREATE INDEX ix_reconciliation_runs_is_current ON reconciliation_runs (is_current);

ALTER TABLE reconciliation_results ADD COLUMN run_id INTEGER;

ALTER TABLE reconciliation_results ADD COLUMN is_current BOOLEAN DEFAULT true NOT NULL;

CREATE INDEX ix_reconciliation_results_run_id ON reconciliation_results (run_id);

CREATE INDEX ix_reconciliation_results_is_current ON reconciliation_results (is_current);

ALTER TABLE reconciliation_results ADD CONSTRAINT fk_reconciliation_results_run_id_reconciliation_runs FOREIGN KEY(run_id) REFERENCES reconciliation_runs (id) ON DELETE CASCADE;

UPDATE alembic_version SET version_num='c1d2e3f4a5b6' WHERE alembic_version.version_num = 'b7c2e1f4a6d9';

COMMIT;

