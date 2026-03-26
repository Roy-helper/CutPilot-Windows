/**
 * Notification store — global toast/bell notifications.
 * Persists across route changes.
 */
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export interface Notification {
  id: number
  type: 'success' | 'error' | 'info'
  icon: string
  title: string
  detail: string
  time: string
  read: boolean
}

let _nextId = 1

export const useNotificationStore = defineStore('notifications', () => {
  const items = ref<Notification[]>([])
  const showPanel = ref(false)

  const unreadCount = computed(() => items.value.filter(n => !n.read).length)

  function add(type: Notification['type'], title: string, detail: string = '') {
    const icons: Record<string, string> = { success: 'check_circle', error: 'error', info: 'info' }
    const now = new Date()
    const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
    items.value.unshift({
      id: _nextId++,
      type, icon: icons[type] ?? 'info',
      title, detail, time, read: false,
    })
    // Keep max 50
    if (items.value.length > 50) items.value.length = 50
  }

  function markAllRead() {
    for (const n of items.value) n.read = true
  }

  function clearAll() {
    items.value = []
  }

  function toggle() {
    showPanel.value = !showPanel.value
    if (showPanel.value) markAllRead()
  }

  return { items, showPanel, unreadCount, add, markAllRead, clearAll, toggle }
})
