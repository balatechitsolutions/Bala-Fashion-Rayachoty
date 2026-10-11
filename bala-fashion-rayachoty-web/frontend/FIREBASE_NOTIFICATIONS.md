# Firebase web notifications

The storefront includes a notification bell with an unread badge and a notification panel. Firebase Cloud Messaging (FCM) powers browser push delivery; received foreground messages are saved per signed-in Supabase user in that browser.

## Vercel environment variables

In the Firebase Console, create a Web App under the same Firebase project and enable **Cloud Messaging**. Generate a Web Push certificate key pair under Project Settings → Cloud Messaging. Add these variables to the Vercel project for **Production, Preview, and Development** as needed:

- `VITE_FIREBASE_API_KEY`
- `VITE_FIREBASE_AUTH_DOMAIN`
- `VITE_FIREBASE_PROJECT_ID`
- `VITE_FIREBASE_STORAGE_BUCKET`
- `VITE_FIREBASE_MESSAGING_SENDER_ID`
- `VITE_FIREBASE_APP_ID`
- `VITE_FIREBASE_VAPID_KEY` — the Web Push certificate public key

Redeploy the frontend after setting the variables. Push permission must be granted by each user in a supported browser. The site must be served over HTTPS (Vercel production already is).

## Sending a test notification

After a signed-in user enables push notifications in the bell panel, their browser obtains an FCM registration token. Send a test notification from Firebase Console → Messaging to that device token. The service worker displays notifications when the site is in the background; messages received while the site is open appear in the in-app panel and increase the unread badge. Opening the bell and choosing **Mark all read** clears the badge.

## Scope / security

Firebase web configuration and the VAPID public key are client-side values, not service-account credentials. Never put a Firebase Admin SDK private key in a `VITE_*` variable or frontend code. Automated server-side order notifications require a trusted backend sender configured with Firebase Admin credentials and a device-token registration endpoint; this frontend change does not expose any server credentials.
