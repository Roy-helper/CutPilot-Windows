<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterView } from 'vue-router'
import SideNav from '@/components/SideNav.vue'
import { useNotificationStore } from '@/stores/notifications'

const devMode = ref(false)
const licenseBanner = ref('')
const licenseBannerLevel = ref<'info' | 'error'>('info')

onMounted(() => {
  // pywebview injects window.pywebview AFTER DOM load via pywebviewready event.
  // Check with delay to avoid false "dev mode" detection.
  const checkNative = () => {
    devMode.value = !window.pywebview?.api
  }

  // If already injected (fast load), check now
  if (window.pywebview?.api) {
    devMode.value = false
  } else {
    // Wait for pywebview to inject, or confirm dev mode after timeout
    window.addEventListener('pywebviewready', () => { devMode.value = false }, { once: true })
    globalThis.setTimeout(checkNative, 2000)
  }

  // Listen for license warnings from pywebview bridge
  window.addEventListener('license-warning', (evt: Event) => {
    const detail = (evt as CustomEvent).detail
    licenseBanner.value = detail.message
    licenseBannerLevel.value = detail.level ?? 'info'
    const notify = useNotificationStore()
    notify.add(detail.level === 'error' ? 'error' : 'info', detail.message)
  })
})
</script>

<template>
  <div class="min-h-screen">
    <!-- Dev mode banner -->
    <div v-if="devMode" class="fixed top-0 left-64 right-0 z-[60] bg-amber-500 text-white text-center text-xs py-1 font-medium">
      开发模式 — 后端未连接，数据为模拟值
    </div>
    <!-- License banner -->
    <div v-if="licenseBanner" class="fixed top-0 left-64 right-0 z-[59] text-center text-xs py-1.5 font-medium"
      :class="licenseBannerLevel === 'error' ? 'bg-error text-white' : 'bg-primary-fixed text-on-primary-fixed'">
      {{ licenseBanner }}
      <button class="ml-4 underline" @click="licenseBanner = ''">关闭</button>
    </div>
    <SideNav />
    <main class="pl-64 min-h-screen" :class="{ 'pt-6': devMode || licenseBanner }">
      <RouterView />
    </main>
  </div>
</template>
