/* Firebase Cloud Messaging service worker. Public Firebase config is passed via the registration URL. */
importScripts('https://www.gstatic.com/firebasejs/11.10.0/firebase-app-compat.js')
importScripts('https://www.gstatic.com/firebasejs/11.10.0/firebase-messaging-compat.js')

const params = new URL(self.location.href).searchParams
const firebaseConfig = {
  apiKey: params.get('apiKey'),
  authDomain: params.get('authDomain'),
  projectId: params.get('projectId'),
  storageBucket: params.get('storageBucket'),
  messagingSenderId: params.get('messagingSenderId'),
  appId: params.get('appId'),
}
if (firebaseConfig.apiKey && firebaseConfig.projectId && firebaseConfig.messagingSenderId && firebaseConfig.appId) {
  firebase.initializeApp(firebaseConfig)
  const messaging = firebase.messaging()
  messaging.onBackgroundMessage((payload) => {
    const title = payload?.notification?.title || payload?.data?.title || 'Bala Fashion'
    const options = {
      body: payload?.notification?.body || payload?.data?.body || 'You have a new notification.',
      icon: '/b-tech-logo.png',
      badge: '/b-tech-logo.png',
      data: payload?.data || {},
      tag: payload?.data?.notificationId || `bala-${Date.now()}`,
    }
    self.registration.showNotification(title, options)
  })
}
self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const target = event.notification?.data?.url || '/'
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    for (const client of windows) {
      if ('focus' in client) {
        await client.focus()
        if ('navigate' in client) await client.navigate(target)
        return
      }
    }
    if (self.clients.openWindow) await self.clients.openWindow(target)
  })())
})
