/**
 * Request permission for browser notifications
 */
export async function requestNotificationPermission() {
  if (!('Notification' in window)) {
    console.warn('Browser does not support notifications')
    return false
  }

  if (Notification.permission === 'granted') {
    return true
  }

  if (Notification.permission !== 'denied') {
    try {
      const permission = await Notification.requestPermission()
      return permission === 'granted'
    } catch (error) {
      console.error('Error requesting notification permission:', error)
      return false
    }
  }

  return false
}

/**
 * Show a browser notification
 */
export function showNotification(title, options = {}) {
  if (!('Notification' in window)) {
    console.warn('Browser does not support notifications')
    return
  }

  if (Notification.permission !== 'granted') {
    console.warn('Notification permission not granted')
    return
  }

  try {
    const notification = new Notification(title, {
      icon: '/favicon.ico', // Add your app icon
      ...options,
    })

    // Auto-close notification after 5 seconds
    setTimeout(() => notification.close(), 5000)

    return notification
  } catch (error) {
    console.error('Error showing notification:', error)
  }
}

