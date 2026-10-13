# Bala Fashion scalability guide

This project uses React/Vite, Django REST Framework, and Supabase PostgreSQL. Apply the following changes progressively and measure them rather than scaling blindly.

## Implemented in this change

1. **Pagination:** `GET /api/products/` returns at most 30 products by default (up to 60 when requested), plus `has_more` and `next_offset`. The storefront's **Load more styles** control requests subsequent pages. Offset is capped to avoid unbounded requests.
2. **Indexes:** `supabase/scalability_indexes.sql` adds idempotent indexes for public catalog ordering/filtering, customer/vendor/delivery order lists, order items, categories, profiles and push-device lookup. Review the existing index list first, then run the SQL in Supabase SQL Editor. Indexes use storage and add write overhead, so retain only useful ones.
3. **Caching:** product pages are cached for 15 seconds and categories for 60 seconds. Configure `REDIS_URL` to use a shared Redis cache. Without it, Django uses local-memory cache; this fallback is per process and not shared across instances. Checkout always re-reads and validates product price/stock in PostgreSQL.
4. **Query optimization:** product list queries fetch a bounded page, use deterministic ordering (`created_at`, then `id`), and avoid total-count scans. The order and dashboard queries should be reviewed with PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` against production-like data before adding more indexes.
5. **Horizontal scaling / connections:** the backend now enables Django database connection health checks and configurable `DB_CONN_MAX_AGE` (default 60 seconds). Scale Render web instances only after load testing. Keep the database connection budget in mind: app instances × worker processes × concurrent DB connections must fit the Supabase pooler limits. Configure Gunicorn worker count conservatively for the selected Render memory plan.
6. **Background tasks:** push dispatch is registered after transaction commit. When `CELERY_BROKER_URL` is configured and a Celery worker is running, push notifications are queued with retries; without a broker configured, current best-effort inline delivery remains active.

## Production configuration

- `REDIS_URL`: optional shared Redis URL for the Django cache.
- `CELERY_BROKER_URL`: set only after a reachable Redis broker and Celery worker are provisioned. This is separate from `REDIS_URL` intentionally, so enabling cache does not silently queue push messages to a worker that does not exist.
- Worker command from the backend directory: `celery -A config.celery:app worker --loglevel=info --concurrency=2`. Deploy it as a separate background worker and use the same broker URL/environment as the web service.
- `DB_CONN_MAX_AGE`: optional integer seconds, default `60`. If using a transaction-pooling connection pooler, choose a value consistent with its documented connection mode and test reconnect behavior.
- Run the Supabase SQL index file manually. Django does not manage these Supabase-owned tables.

## Verification checklist

1. Request `/api/products/?limit=30&offset=0`; verify at most 30 rows and the `has_more`/`next_offset` fields.
2. Request the returned `next_offset`; verify the next page does not repeat the previous page's last product.
3. Compare cache hit/miss response time and confirm product changes become visible within the short TTL.
4. Use `EXPLAIN (ANALYZE, BUFFERS)` for storefront and order-list SQL; check whether the new indexes are selected.
5. Load test with realistic product/order counts and concurrent users; track p95 latency, 5xx rate, CPU/memory, DB connections and slow queries.
6. Configure Redis and the worker before enabling `CELERY_BROKER_URL`; verify retries and logs. Do not set a broker URL without a running worker.
