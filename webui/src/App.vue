<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterView } from 'vue-router'
import SideNav from '@/components/SideNav.vue'
import ActivationView from '@/views/ActivationView.vue'
import SetupView from '@/views/SetupView.vue'
import { getLicenseInfo, checkAsrStatus } from '@/bridge'
import { useNotificationStore } from '@/stores/notifications'

const devMode = ref(false)
const licenseBanner = ref('')
const licenseBannerLevel = ref<'info' | 'error'>('info')

// Startup flow: Loading → Activation → Setup → Main
type AppState = 'loading' | 'activation' | 'setup' | 'main'
const state = ref<AppState>('loading')

onMounted(async () => {
  // pywebview detection
  if (window.pywebview?.api) {
    devMode.value = false
  } else {
    window.addEventListener('pywebviewready', () => { devMode.value = false }, { once: true })
    globalThis.setTimeout(() => { devMode.value = !window.pywebview?.api }, 2000)
  }

  // Step 1: License check
  try {
    const info = await getLicenseInfo() as Record<string, any>
    const isValid = info.is_valid === true
    const trialLeft = (info.trial_remaining as number) ?? 0

    if (!isValid && trialLeft <= 0) {
      state.value = 'activation'
      return
    }

    if (isValid && info.expiry) {
      const expDate = new Date(info.expiry as string)
      const daysLeft = Math.ceil((expDate.getTime() - Date.now()) / 86400000)
      if (daysLeft <= 7 && daysLeft > 0) {
        licenseBanner.value = `授权将在 ${daysLeft} 天后到期，请及时续费`
        licenseBannerLevel.value = 'info'
      }
    } else if (!isValid && trialLeft > 0) {
      licenseBanner.value = `试用模式: 剩余 ${trialLeft} 次免费使用`
      licenseBannerLevel.value = 'info'
    }
  } catch {
    // Dev mode — skip license
  }

  // Step 2: Check if setup needed (ASR model missing)
  try {
    const asr = await checkAsrStatus()
    if (!asr.models_cached) {
      state.value = 'setup'
      return
    }
  } catch {
    // Dev mode — skip setup
  }

  // All good
  state.value = 'main'

  // Listen for license warnings
  window.addEventListener('license-warning', (evt: Event) => {
    const detail = (evt as CustomEvent).detail
    licenseBanner.value = detail.message
    licenseBannerLevel.value = detail.level ?? 'info'
    const notify = useNotificationStore()
    notify.add(detail.level === 'error' ? 'error' : 'info', detail.message)
  })
})

function onActivated() {
  // After activation, check if setup needed
  state.value = 'setup'
  checkAsrStatus().then(asr => {
    if (asr.models_cached) state.value = 'main'
  }).catch(() => { state.value = 'main' })
}

function onSetupReady() {
  state.value = 'main'
}
</script>

<template>
  <!-- Loading -->
  <div v-if="state === 'loading'" class="min-h-screen bg-[#2e3132] flex items-center justify-center">
    <div class="text-center">
      <h1 class="text-xl font-bold text-white tracking-tight mb-2">CutPilot</h1>
      <p class="text-sm text-slate-400">正在启动...</p>
    </div>
  </div>

  <!-- Activation -->
  <ActivationView v-else-if="state === 'activation'" @activated="onActivated" />

  <!-- Setup wizard -->
  <SetupView v-else-if="state === 'setup'" @ready="onSetupReady" />

  <!-- Main app -->
  <div v-else class="min-h-screen">
    <div v-if="devMode" class="fixed top-0 left-64 right-0 z-[60] bg-amber-500 text-white text-center text-xs py-1 font-medium">
      开发模式 — 后端未连接，数据为模拟值
    </div>
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
