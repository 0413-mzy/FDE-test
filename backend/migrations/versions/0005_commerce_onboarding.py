"""Frozen additive onboarding schema; preserve existing commerce rows."""

from alembic import op

revision = "0005_commerce_onboarding"
down_revision = "0004_commerce_after_sales"
branch_labels = None
depends_on = None

DDL = (
    """
CREATE TABLE commerce_account_profiles (
	account_id UUID NOT NULL,
	display_name VARCHAR(100) NOT NULL,
	phone VARCHAR(32) NOT NULL,
	email VARCHAR(254),
	email_verified BOOLEAN NOT NULL,
	review_enabled BOOLEAN NOT NULL,
	id UUID NOT NULL,
	version INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (account_id),
	FOREIGN KEY(account_id) REFERENCES commerce_accounts (id),
	UNIQUE (email)
)
    """,
    """
CREATE TABLE commerce_email_challenges (
	account_id UUID NOT NULL,
	email VARCHAR(254) NOT NULL,
	purpose VARCHAR(20) NOT NULL,
	token_digest VARCHAR(64) NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	consumed_at TIMESTAMP WITH TIME ZONE,
	id UUID NOT NULL,
	version INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (purpose IN ('REGISTER','BIND','RESET')),
	FOREIGN KEY(account_id) REFERENCES commerce_accounts (id),
	UNIQUE (token_digest)
)
    """,
    """
CREATE TABLE commerce_anonymous_requests (
	operation VARCHAR(100) NOT NULL,
	key VARCHAR(200) NOT NULL,
	request_hash VARCHAR(64) NOT NULL,
	response_payload JSONB NOT NULL,
	response_status INTEGER NOT NULL,
	id UUID NOT NULL,
	version INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (operation, key)
)
    """,
    """
CREATE TABLE commerce_auth_rate_events (
	purpose VARCHAR(100) NOT NULL,
	ip_digest VARCHAR(64) NOT NULL,
	email_digest VARCHAR(64),
	id UUID NOT NULL,
	version INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id)
)
    """,
    """
CREATE TABLE commerce_address_book (
	customer_id UUID NOT NULL,
	address JSONB NOT NULL,
	is_default BOOLEAN NOT NULL,
	active BOOLEAN NOT NULL,
	id UUID NOT NULL,
	version INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(customer_id) REFERENCES commerce_accounts (id)
)
    """,
    """
CREATE UNIQUE INDEX commerce_one_default_address
ON commerce_address_book (customer_id) WHERE active AND is_default
    """,
    """
CREATE TABLE commerce_merchant_applications (
	customer_id UUID NOT NULL,
	state VARCHAR(20) NOT NULL,
	shop_name VARCHAR(200) NOT NULL,
	business_scope VARCHAR(500) NOT NULL,
	contact_name VARCHAR(100) NOT NULL,
	contact_phone VARCHAR(32) NOT NULL,
	description TEXT NOT NULL,
	decision_reason VARCHAR(500),
	shop_id UUID,
	id UUID NOT NULL,
	version INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (state IN ('PENDING','APPROVED','REJECTED','WITHDRAWN')),
	FOREIGN KEY(customer_id) REFERENCES commerce_accounts (id),
	FOREIGN KEY(shop_id) REFERENCES commerce_shops (id)
)
    """,
    """
CREATE UNIQUE INDEX commerce_one_pending_application
ON commerce_merchant_applications (customer_id) WHERE state='PENDING'
    """,
)


def upgrade():
    for statement in DDL:
        op.execute(statement)


def downgrade():
    for table in (
        "commerce_merchant_applications",
        "commerce_address_book",
        "commerce_auth_rate_events",
        "commerce_anonymous_requests",
        "commerce_email_challenges",
        "commerce_account_profiles",
    ):
        op.drop_table(table)
