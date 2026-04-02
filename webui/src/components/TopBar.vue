<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useNotificationStore } from '@/stores/notifications'

const props = defineProps<{
  searchPlaceholder?: string
  modelValue?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const router = useRouter()
const notify = useNotificationStore()
const showAccountMenu = ref(false)

function goToSettings() {
  showAccountMenu.value = false
  router.push('/settings')
}

function closeMenuDelayed() {
  globalThis.setTimeout(() => { showAccountMenu.value = false }, 150)
}

function onClickOutsideNotify(e: MouseEvent) {
  const panel = document.querySelector('.notify-panel-root')
  if (panel && !panel.contains(e.target as Node)) {
    notify.showPanel = false
  }
}

function onSearch(e: Event) {
  emit('update:modelValue', (e.target as HTMLInputElement).value)
}

onMounted(() => document.addEventListener('click', onClickOutsideNotify))
onUnmounted(() => document.removeEventListener('click', onClickOutsideNotify))

const notifyTypeColor: Record<string, string> = {
  success: 'text-green-600',
  error: 'text-error',
  info: 'text-primary',
}
</script>

<template>
  <header class="flex justify-between items-center w-full px-8 h-16 bg-[#f8f9fa] sticky top-0 z-40">
    <div class="flex items-center flex-1">
      <div class="relative w-96">
        <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-sm">search</span>
        <input
          class="w-full bg-surface-container-highest border-none rounded-md py-2 pl-10 pr-4 text-sm focus:ring-2 focus:ring-primary/20 focus:bg-surface-container-lowest transition-all"
          :placeholder="searchPlaceholder ?? '搜索...'"
          :value="modelValue"
          type="text"
          @input="onSearch"
        />
      </div>
    </div>
    <div class="flex items-center gap-3">
      <slot name="actions" />
      <div class="h-6 w-px bg-outline-variant/30 mx-2"></div>

      <!-- Notifications -->
      <div class="relative notify-panel-root">
        <button
          class="p-2 text-on-surface-variant hover:bg-surface-container-high rounded-full transition-colors relative"
          title="通知"
          @click="notify.toggle()"
        >
          <span class="material-symbols-outlined">notifications</span>
          <span
            v-if="notify.unreadCount > 0"
            class="absolute top-1 right-1 w-4 h-4 bg-error text-white text-[9px] font-bold rounded-full flex items-center justify-center"
          >{{ notify.unreadCount > 9 ? '9+' : notify.unreadCount }}</span>
        </button>

        <!-- Notification panel -->
        <Transition name="dropdown">
          <div
            v-if="notify.showPanel"
            class="absolute right-0 top-full mt-2 w-80 max-h-96 bg-surface-container-lowest rounded-xl shadow-xl border border-outline-variant/10 overflow-hidden z-50 flex flex-col"
          >
            <div class="px-4 py-3 border-b border-surface-container flex justify-between items-center">
              <span class="text-sm font-semibold text-on-surface">通知</span>
              <button
                v-if="notify.items.length > 0"
                class="text-[10px] font-bold text-primary hover:underline uppercase"
                @click="notify.clearAll()"
              >清空</button>
            </div>
            <div v-if="notify.items.length === 0" class="px-4 py-8 text-center">
              <span class="material-symbols-outlined text-3xl text-on-surface-variant/20 mb-2">notifications_none</span>
              <p class="text-xs text-on-surface-variant/50">暂无通知</p>
            </div>
            <div v-else class="overflow-y-auto flex-1">
              <div
                v-for="n in notify.items"
                :key="n.id"
                class="px-4 py-3 hover:bg-surface-container-low transition-colors border-b border-surface-container last:border-0"
                :class="{ 'bg-primary-fixed/5': !n.read }"
              >
                <div class="flex items-start gap-3">
                  <span class="material-symbols-outlined text-sm mt-0.5" :class="notifyTypeColor[n.type]" style="font-variation-settings: 'FILL' 1;">{{ n.icon }}</span>
                  <div class="flex-1 min-w-0">
                    <p class="text-xs font-semibold text-on-surface">{{ n.title }}</p>
                    <p v-if="n.detail" class="text-[10px] text-on-surface-variant mt-0.5 truncate">{{ n.detail }}</p>
                  </div>
                  <span class="text-[10px] text-outline whitespace-nowrap">{{ n.time }}</span>
                </div>
              </div>
            </div>
          </div>
        </Transition>
      </div>

      <!-- Account -->
      <div class="relative">
        <button
          class="p-2 text-on-surface-variant hover:bg-surface-container-high rounded-full transition-colors"
          title="账户"
          @click="showAccountMenu = !showAccountMenu"
          @blur="closeMenuDelayed"
        >
          <span class="material-symbols-outlined">account_circle</span>
        </button>

        <Transition name="dropdown">
          <div
            v-if="showAccountMenu"
            class="absolute right-0 top-full mt-2 w-56 bg-surface-container-lowest rounded-xl shadow-xl border border-outline-variant/10 overflow-hidden z-50"
          >
            <div class="px-4 py-3 border-b border-surface-container">
              <p class="text-sm font-semibold text-on-surface">管理员账户</p>
            </div>
            <button class="flex items-center gap-3 px-4 py-3 text-on-surface hover:bg-surface-container-low transition-colors text-sm w-full text-left" @click="goToSettings">
              <span class="material-symbols-outlined text-sm">settings</span>
              账户与授权
            </button>
          </div>
        </Transition>
      </div>
    </div>
  </header>
</template>

<style scoped>
.dropdown-enter-active, .dropdown-leave-active {
  transition: opacity 0.15s, transform 0.15s;
}
.dropdown-enter-from, .dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
