# Supabase migration-source reconciliation

Audited against the connected production project's `supabase_migrations.schema_migrations` table on 2026-10-14.

## Source of truth

The production migration table stores each applied migration's `version`, `name`, and SQL `statements` array. The versioned SQL files in `migrations/` are restored from those stored statements, not guessed from the current schema and not regenerated as new migration history. The existing database history is left unchanged.

The production history contains **22 records**:

| Version | Recorded migration |
| --- | --- |
| 20261011110650 | bootstrap_profiles_and_protect_roles |
| 20261011110711 | restrict_internal_profile_trigger_functions |
| 20261011111038 | lock_down_django_internal_tables |
| 20261011111059 | lock_down_django_system_tables |
| 20261011154230 | account_notifications |
| 20261011154452 | lock_down_account_notifications |
| 20261012034658 | vendor_delivery_locations |
| 20261013032529 | customer_addresses_delivery_otp |
| 20261013040439 | customer_addresses_delivery_otp |
| 20261013055113 | repair_customer_address_location_columns |
| 20261013072728 | delivery_staff_activation_location_notifications |
| 20261013111631 | push_notification_devices |
| 20261014032027 | repair_legacy_order_address_snapshots |
| 20261014033818 | enforce_one_customer_default_address |
| 20261014053020 | freeze_order_addresses |
| 20261014053250 | audit_order_address_corrections |
| 20261014054924 | secure_delivery_assignment_notifications_and_index_order_queries |
| 20261014055408 | secure_delivery_assignment_notifications |
| 20261014082934 | remove_duplicate_delivery_notification_index |
| 20261014083904 | least_privilege_public_table_grants |
| 20261014084011 | restrict_profile_client_write_columns |
| 20261014084514 | restrict_direct_order_table_reads |

## Important reconciliation notes

- The two `customer_addresses_delivery_otp` records at versions `20261013032529` and `20261013040439` are both retained because both versions exist in production. Their stored SQL is identical and idempotent; neither history row is deleted or rewritten.
- Earlier files with date-only or mismatched timestamps did not match the production migration versions. Canonical files use the exact recorded 14-digit versions and names.
- The previous `20261012_delivery_boy_role.sql` file was not present in the production migration history. It is archived under `manual_sql/legacy/` rather than left in the active migration directory, where it would appear as an unrecorded migration. Its role/assignment definitions are already present in the current `schema.sql` baseline.
- `schema.sql` remains the documented core-schema bootstrap. The versioned migration files are the subsequent production history. For a fresh environment, follow the project's bootstrap procedure and then apply the recorded migrations in version order.
- Do not manually insert/delete rows in `supabase_migrations.schema_migrations` to force parity. Validate source parity by comparing the version/name list and each SQL file against the stored `statements` value.

## Security posture represented by recent recorded migrations

- Public catalog reads are granted to `anon` and `authenticated`, with RLS policies limiting rows to approved vendors and active categories/products.
- Customers can access only their own saved addresses and own order rows through RLS. Order/order-item direct client table grants are revoked so role-filtered order details are served by Django APIs.
- Profile inserts/updates are column-restricted for authenticated clients to `id, full_name, phone` on insert and `full_name, phone` on update; role, activation, availability, and live-location changes remain backend/admin controlled.
- Django internal tables, order-address audit, and notification tables remain backend-only for direct PostgREST client access. RLS is enabled without client policies intentionally; the trusted backend connection is not forced under RLS, preserving Django Admin and migrations.

## Remaining operational verification

Restoring SQL source does not itself prove the latest backend/frontend commits are deployed or that a real authenticated checkout-to-delivery flow succeeds. Verify deployments and run authenticated staging/safe test-order checks for checkout snapshot persistence, vendor/admin visibility, assignment, and OTP before marking production end-to-end validation complete.
