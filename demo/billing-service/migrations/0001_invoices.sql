CREATE TABLE invoices (
    id BIGSERIAL PRIMARY KEY,
    customer TEXT NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    lines JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
