<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterView } from 'vue-router'
import SideNav from '@/components/SideNav.vue'
import ActivationView from '@/views/ActivationView.vue'
import { getLicenseInfo } from '@/bridge'
import { useNotificationStore } from '@/stores/notifications'

const devMode = ref(false)
const licenseBanner = ref('')
const licenseBannerLevel = ref<'info' | 'error'>('info')

// License gate: show activation screen if not licensed and no trial left
const licenseChecked = ref(false)
const needsActivation = ref(false)
const trialMode = ref(false)

onMounted(async () => {
  // pywebview detection
  if (window.pywebview?.api) {
    devMode.value = false
  } else {
    window.addEventListener('pywebviewready', () => { devMode.value = false }, { once: true })
    globalThis.setTimeout(() => { devMode.value = !window.pywebview?.api }, 2000)
  }

  // License check
  try {
    const info = await getLicenseInfo() as Record<string, any>
    const isValid = info.is_valid === true
    const trialLeft = (info.trial_remaining as number) ?? 0

    if (isValid) {
      needsActivation.value = false
      // Check near-expiry
      if (info.expiry) {
        const expDate = new Date(info.expiry as string)
        const daysLeft = Math.ceil((expDate.getTime() - Date.now()) / 86400000)
        if (daysLeft <= 7 && daysLeft > 0) {
          licenseBanner.value = `授权将在 ${daysLeft} 天后到期，请及时续费`
          licenseBannerLevel.value = 'info'
        }
      }
    } else if (trialLeft > 0) {
      // Has trial remaining — let them in but show banner
      needsActivation.value = false
      trialMode.value = true
      licenseBanner.value = `试用模式: 剩余 ${trialLeft} 次免费使用`
      licenseBannerLevel.value = 'info'
    } else {
      // No license, no trial — must activate
      needsActivation.value = true
    }
  } catch {
    // Bridge not ready (dev mode) — let them in
    needsActivation.value = false
  }
  licenseChecked.value = true

  // Listen for license warnings from pywebview bridge
  window.addEventListener('license-warning', (evt: Event) => {
    const detail = (evt as CustomEvent).detail
    licenseBanner.value = detail.message
    licenseBannerLevel.value = detail.level ?? 'info'
    const notify = useNotificationStore()
    notify.add(detail.level === 'error' ? 'error' : 'info', detail.message)
  })
})

function onActivated() {
  needsActivation.value = false
  licenseBanner.value = ''
}
</script>

<template>
  <!-- Loading state -->
  <div v-if="!licenseChecked" class="min-h-screen bg-[#2e3132] flex items-center justify-center">
    <div class="text-center">
      <h1 class="text-xl font-bold text-white tracking-tight mb-2">CutPilot</h1>
      <p class="text-sm text-slate-400">正在启动...</p>
    </div>
  </div>

  <!-- Activation gate -->
  <ActivationView v-else-if="needsActivation" @activated="onActivated" />

  <!-- Main app -->
  <div v-else class="min-h-screen">
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
