import { getApp, getApps, initializeApp } from 'firebase/app'
import { getMessaging, getToken, isSupported, onMessage } from 'firebase/messaging'

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
}

export const firebaseConfigured = Object.values(config).every(Boolean)
export const firebaseVapidKey = import.meta.env.VITE_FIREBASE_VAPID_KEY || ''

function firebaseApp() {
  if (!firebaseConfigured) throw new Error('Firebase is not configured for this deployment yet.')
  return getApps().length ? getApp() : initializeApp(config)
}

export async function enableFirebaseNotifications() {
  if (!firebaseConfigured) throw new Error('Add the VITE_FIREBASE_* settings in Vercel before enabling notifications.')
  if (!firebaseVapidKey) throw new Error('Add VITE_FIREBASE_VAPID_KEY in Vercel to enable browser notifications.')
  if (!('Notification' in window) || !('serviceWorker' in navigator)) {
    throw new Error('This browser does not support push notifications.')
  }
  if (!(await isSupported())) throw new Error('Push notifications are not supported in this browser.')
  if (Notification.permission === 'denied') {
    throw new Error('Notifications are blocked in browser settings. Allow them for Bala Fashion and try again.')
  }
  const permission = Notification.permission === 'granted' ? 'granted' : await Notification.requestPermission()
  if (permission !== 'granted') throw new Error('Allow notifications to receive Bala Fashion alerts.')

  const query = new URLSearchParams(config).toString()
  const registration = await navigator.serviceWorker.register(`/firebase-messaging-sw.js?${query}`)
  await navigator.serviceWorker.ready
  const messaging = getMessaging(firebaseApp())
  const token = await getToken(messaging, { vapidKey: firebaseVapidKey, serviceWorkerRegistration: registration })
  if (!token) throw new Error('Firebase did not issue a device token. Please try again.')
  return token
}

export async function subscribeToFirebaseMessages(callback) {
  if (!firebaseConfigured || !(await isSupported())) return () => {}
  const messaging = getMessaging(firebaseApp())
  return onMessage(messaging, callback)
}
