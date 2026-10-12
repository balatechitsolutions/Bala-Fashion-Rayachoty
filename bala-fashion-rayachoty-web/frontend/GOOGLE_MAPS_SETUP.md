# Google Maps setup

The storefront location picker uses the Google Maps JavaScript API.

## Required Google Cloud setup

1. In Google Cloud Console, select or create a project with billing enabled.
2. Enable **Maps JavaScript API**.
3. Create an API key.
4. Restrict the key to **Websites (HTTP referrers)** and allow the production storefront:
   - `https://bala-fashion-rayachoty-omega.vercel.app/*`
   - Add only the exact Vercel preview domains you actually use for testing.
5. Restrict the key to the **Maps JavaScript API** where supported by the API-key restriction settings.

## Vercel

In the `bala-fashion-rayachoty` project, open **Settings → Environment Variables** and add:

- Name: `VITE_GOOGLE_MAPS_API_KEY`
- Value: the restricted browser API key
- Environment: Production (and Preview only if preview deployments need the map)

Redeploy the frontend after saving the variable. Vite exposes `VITE_*` values in browser code, so this must be a browser-restricted key, never a server/service-account secret.

## Delivery-distance behavior

This change replaces the map picker UI only. Existing Django delivery-quote validation and its road-distance provider/rules remain unchanged: Rayachoty local delivery, up to 5 km road distance, ₹5 per started 500 m, and ₹250 minimum order. Do not treat map display as a substitute for the server-side delivery quote.
