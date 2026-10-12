# Bala Fashion Rayachoty — Web Marketplace

React/Vite storefront (Vercel), Django REST API (Render), Supabase Auth + PostgreSQL, and Cloudinary image uploads.

## Included
- Responsive storefront, product search/categories, cart, product details, Google OAuth sign-in, COD checkout and order history.
- Django REST API with Supabase JWT verification, server-side Postgres checkout transactions and row locking.
- Vendor/admin product creation and signed Cloudinary image uploads.
- Supabase schema and row-level security policies in `supabase/schema.sql`.
- Django API tests and deployment configuration.

## Supabase
Project URL: `https://iikogznarstzoovxpzfg.supabase.co`. The core schema and policies have already been created in the connected project.

Get the Postgres connection string from Supabase Dashboard → Project Settings → Database → Connect. Set it as `DATABASE_URL` in Render only, with SSL enabled. Do not put it in the React environment.

## Google OAuth
1. Supabase Dashboard → Authentication → Sign In / Providers → Google → enable.
2. Create an OAuth Client ID in Google Cloud Console and copy its Client ID and Client Secret into the Supabase Google provider settings.
3. In Supabase Auth → URL Configuration, set your production Vercel URL as Site URL and allow `http://localhost:5173` plus your production and preview callback URLs.
4. Use the redirect URI shown in the Supabase Google provider settings in Google Cloud Console.
5. Frontend Google login is initiated by Supabase Auth; Google credentials are never put in frontend code.

## Render backend
Set the service root directory to `backend`.
- Build: `pip install -r requirements.txt`
- Start: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`
- Health check: `/api/health/`

Environment variables:
- `DJANGO_SECRET_KEY`: long random secret
- `DEBUG`: `False`
- `ALLOWED_HOSTS`: your Render hostname
- `CORS_ALLOWED_ORIGINS`: your Vercel site URL
- `DATABASE_URL`: Supabase Postgres connection string (server only)
- `SUPABASE_URL`: `https://iikogznarstzoovxpzfg.supabase.co`
- `SUPABASE_PUBLISHABLE_KEY`: same public publishable key used by the frontend
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`: Cloudinary Console values
- `DELIVERY_FEE`: optional, defaults to `0`

## Vercel frontend
Import the repository and set Root Directory to `frontend`. Build command `npm run build`; output directory `dist`.
Set:
- `VITE_API_BASE_URL`: your Render API URL ending in `/api`
- `VITE_SUPABASE_URL`: `https://iikogznarstzoovxpzfg.supabase.co`
- `VITE_SUPABASE_PUBLISHABLE_KEY`: Supabase publishable key
- `VITE_DEMO_MODE`: `false` for production

The publishable key is intentionally public. Never expose the database password or Cloudinary API secret in a `VITE_` variable.

## Local run
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py check
python manage.py test
python manage.py runserver
```
In a second terminal:
```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
npm run build
```

## Launch checklist
- Enable Google provider in Supabase.
- Configure Render environment variables, then deploy and verify `/api/health/`.
- Configure Vercel variables, then deploy the frontend.
- Create an approved vendor and active products before launch.
- Promote a verified auth user to admin using Supabase SQL Editor: `insert into public.profiles(id, role) values ('<verified-auth-user-uuid>', 'admin') on conflict (id) do update set role='admin';`
- Place and verify a test COD order before accepting customers.
- Add business phone, privacy policy, returns policy, and delivery terms before launch.

Checkout only allows products from one seller per order, revalidates prices/stock server-side, locks inventory rows, and runs in a database transaction. Online payments are not enabled. This starter still needs real-account end-to-end testing and an operational/security review before production.


## Copy Supabase user UUIDs in Django Admin

The storefront authenticates through Supabase Auth. Vendor `owner_id` references `auth.users.id`, so the UUID in the built-in Django **Users** list is not the correct value. Staff can use **Supabase Auth users — copy user UUIDs** in the Django Admin header to view paginated Supabase user UUIDs and copy the correct one.

Set `SUPABASE_SERVICE_ROLE_KEY` as a secret environment variable on the Render backend. Obtain it from Supabase Dashboard → Project Settings → API Keys. Never put this key in frontend `VITE_*` variables, commit it to GitHub, or show it in admin pages. Keep `SUPABASE_URL` configured as well. If the secret is missing, the page displays setup guidance and does not reveal credentials.


## Delivery-boy role

Delivery staff use the same Supabase Auth sign-in as other users, but have a separate `delivery_boy` profile role and a dedicated delivery dashboard. Admins authorize an existing customer account by UUID, then assign packed or out-for-delivery orders to that person. Delivery staff can see only their assigned orders and can mark an order delivered only after it is `out_for_delivery`. They cannot manage products, vendors, or unassigned orders. COD payment is marked paid when delivery is confirmed; customer and admin delivery notifications use the existing notification system.

### Required database migration

Before deploying this feature, open Supabase Dashboard → SQL Editor and run `supabase/migrations/20261012_delivery_boy_role.sql` from this repository. It adds the delivery role to the profile constraint and the nullable order assignment column/index. Do not deploy the new backend before this migration is applied.

### Setup and use

1. Create a delivery person's Supabase Auth account in Authentication → Users (or use an existing customer account).
2. Sign in as admin on the storefront and open **Delivery staff**.
3. Enter the person's Supabase Auth user UUID to authorize the delivery role. Admin/vendor accounts cannot be converted into delivery accounts.
4. In the same panel, assign an order once it is packed or out for delivery. The vendor/admin still controls the existing order progression to `out_for_delivery`.
5. The delivery person signs in to the storefront and opens **Delivery dashboard** from Account. They can view the assigned customer's address/phone, open turn-by-turn directions in Google Maps via a regular URL (no Maps API key required), and mark the order delivered.

Delivery assignment is enforced server-side. A production release should include API tests, a test account for each role, and end-to-end validation before handling live orders.
