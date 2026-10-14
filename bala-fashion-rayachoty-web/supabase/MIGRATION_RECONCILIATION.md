# Supabase migration source reconciliation

Audit date: 2026-10-14  
Project: `iikogznarstzoovxpzfg`  
Canonical schema/migration location: `bala-fashion-rayachoty-web/supabase/`

## Rules used

- The live migration ledger is authoritative for **version and migration name**, not for the SQL body. It does not contain the original SQL text.
- Existing SQL files with a version/path mismatch are preserved under `migration-recovery-candidates/`; they are **not executable migrations** until their body is verified against an authoritative original.
- No SQL was invented to fill historical gaps.
- `schema.sql` is a bootstrap/current-schema file, not a replacement for the ordered historical migration chain.
- Do not run a fresh `supabase db push` from a newly initialized project until the missing historical source is recovered or a deliberately documented baseline strategy is chosen.

## Live migration ledger inventory

| Recorded version | Recorded name | Source status |
|---|---|---|
| 20261011110650 | bootstrap_profiles_and_protect_roles | Missing SQL source |
| 20261011110711 | restrict_internal_profile_trigger_functions | Missing SQL source |
| 20261011111038 | lock_down_django_internal_tables | Missing SQL source |
| 20261011111059 | lock_down_django_system_tables | Missing SQL source |
| 20261011154230 | account_notifications | Missing SQL source |
| 20261011154452 | lock_down_account_notifications | Missing SQL source |
| 20261012034658 | vendor_delivery_locations | Missing SQL source |
| 20261013032529 | customer_addresses_delivery_otp | Missing SQL source |
| 20261013040439 | customer_addresses_delivery_otp | Missing SQL source; distinct recorded version, not deduplicated |
| 20261013055113 | repair_customer_address_location_columns | Missing SQL source |
| 20261013072728 | delivery_staff_activation_location_notifications | Missing SQL source |
| 20261013111631 | push_notification_devices | Missing SQL source |
| 20261014032027 | repair_legacy_order_address_snapshots | Candidate source archived; original applied SQL body not independently verified |
| 20261014033818 | enforce_one_customer_default_address | Candidate source archived; original applied SQL body not independently verified |
| 20261014053020 | freeze_order_addresses | Candidate source archived; original applied SQL body not independently verified |
| 20261014053250 | audit_order_address_corrections | Candidate source archived; original applied SQL body not independently verified |
| 20261014054924 | secure_delivery_assignment_notifications_and_index_order_queries | Missing SQL source |
| 20261014055408 | secure_delivery_assignment_notifications | Missing SQL source |
| 20261014082934 | remove_duplicate_delivery_notification_index | SQL source aligned to the applied statement and recorded version |
| 20261014083904 | least_privilege_public_table_grants | SQL source recorded from the statement applied to the live project |
| 20261014084011 | restrict_profile_client_write_columns | SQL source recorded from the statement applied to the live project |

## Recovery candidates

The four candidate files were preserved without editing their SQL bodies. They had different filename timestamps and/or lived outside the app's canonical Supabase folder. Their filenames and paths are evidence, not proof that their contents exactly match the SQL originally applied to the corresponding live versions.

## Remaining source recovery

There are 14 recorded versions whose SQL bodies are not currently present in the repository or recoverable from the checked Git history. Recover those from an authoritative original (developer machine/export, saved SQL, or database/audit backup where available). If exact originals cannot be recovered, create a separately named **new baseline/snapshot** from the live schema and keep the historical gaps explicitly documented; do not backfill invented files under old migration timestamps.
