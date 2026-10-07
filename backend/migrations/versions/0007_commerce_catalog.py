"""Frozen shopping experience schema and explicit safe history policy."""

from alembic import op

revision = "0007_commerce_catalog"
down_revision = "0006_commerce_history"
branch_labels = None
depends_on = None

FIELD_POLICY = {
    "commerce_categories": ("name", "active", "id", "version", "created_at", "updated_at"),
    "commerce_product_experiences": (
        "product_id",
        "category_id",
        "moderation_hidden",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_product_images": (
        "product_id",
        "position",
        "alt",
        "mime",
        "width",
        "height",
        "digest",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_favorites": (
        "customer_id",
        "product_id",
        "active",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_product_reviews": (
        "customer_id",
        "order_id",
        "order_line_id",
        "product_id",
        "shop_id",
        "rating",
        "body",
        "reply",
        "visible",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
}

DDL = """
CREATE TABLE commerce_categories (
	name VARCHAR(100) NOT NULL, 
	active BOOLEAN NOT NULL, 
	id UUID NOT NULL, 
	version INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (length(trim(name)) BETWEEN 1 AND 100), 
	CHECK (version > 0), 
	UNIQUE (name)
);
CREATE TABLE commerce_product_experiences (
	product_id UUID NOT NULL, 
	category_id UUID, 
	moderation_hidden BOOLEAN DEFAULT 'false' NOT NULL, 
	id UUID NOT NULL, 
	version INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (version > 0), 
	UNIQUE (product_id), 
	FOREIGN KEY(product_id) REFERENCES commerce_products (id), 
	FOREIGN KEY(category_id) REFERENCES commerce_categories (id)
);
CREATE TABLE commerce_product_images (
	product_id UUID NOT NULL, 
	position INTEGER NOT NULL, 
	alt VARCHAR(200) NOT NULL, 
	mime VARCHAR(20) NOT NULL, 
	width INTEGER NOT NULL, 
	height INTEGER NOT NULL, 
	digest VARCHAR(64) NOT NULL, 
	content BYTEA NOT NULL, 
	id UUID NOT NULL, 
	version INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (product_id, position), 
	CHECK (version > 0), 
	CHECK (position BETWEEN 0 AND 7), 
	CHECK (width > 0 AND height > 0 AND width::bigint * height <= 16000000), 
	CHECK (mime IN ('image/png','image/jpeg','image/webp')), 
	CHECK (octet_length(content) BETWEEN 1 AND 8388608), 
	FOREIGN KEY(product_id) REFERENCES commerce_products (id)
);
CREATE TABLE commerce_favorites (
	customer_id UUID NOT NULL, 
	product_id UUID NOT NULL, 
	active BOOLEAN NOT NULL, 
	id UUID NOT NULL, 
	version INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (customer_id, product_id), 
	CHECK (version > 0), 
	FOREIGN KEY(customer_id) REFERENCES commerce_accounts (id), 
	FOREIGN KEY(product_id) REFERENCES commerce_products (id)
);
CREATE TABLE commerce_product_reviews (
	customer_id UUID NOT NULL, 
	order_id UUID NOT NULL, 
	order_line_id UUID NOT NULL, 
	product_id UUID NOT NULL, 
	shop_id UUID NOT NULL, 
	rating INTEGER NOT NULL, 
	body TEXT NOT NULL, 
	reply TEXT, 
	visible BOOLEAN NOT NULL, 
	id UUID NOT NULL, 
	version INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id, customer_id, shop_id) 
        REFERENCES commerce_orders (id, customer_id, shop_id), 
	FOREIGN KEY(order_line_id, order_id) REFERENCES commerce_order_lines (id, order_id), 
	FOREIGN KEY(product_id, shop_id) REFERENCES commerce_products (id, shop_id), 
	CHECK (rating BETWEEN 1 AND 5), 
	CHECK (version > 0), 
	CHECK (length(trim(body)) BETWEEN 1 AND 2000), 
	CHECK (reply IS NULL OR length(trim(reply)) BETWEEN 1 AND 2000), 
	FOREIGN KEY(customer_id) REFERENCES commerce_accounts (id), 
	FOREIGN KEY(order_id) REFERENCES commerce_orders (id), 
	UNIQUE (order_line_id), 
	FOREIGN KEY(order_line_id) REFERENCES commerce_order_lines (id), 
	FOREIGN KEY(product_id) REFERENCES commerce_products (id), 
	FOREIGN KEY(shop_id) REFERENCES commerce_shops (id)
);
"""


def upgrade():
    op.execute(DDL)
    for table, fields in FIELD_POLICY.items():
        safe = ",".join(fields)
        op.execute(
            f"CREATE TRIGGER commerce_history_record AFTER INSERT OR UPDATE OR DELETE "
            f"ON {table} FOR EACH ROW EXECUTE FUNCTION "
            f"commerce_history_record('{safe}','')"
        )


def downgrade():
    for table in reversed(FIELD_POLICY):
        op.execute(f"DROP TABLE {table}")
