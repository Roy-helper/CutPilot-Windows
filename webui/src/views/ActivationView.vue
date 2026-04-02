<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getMachineId, getLicenseInfo, activateLicense } from '@/bridge'

const emit = defineEmits<{ activated: [] }>()

const machineId = ref('读取中...')
const trialRemaining = ref(0)
const activationCode = ref('')
const activating = ref(false)
const resultMsg = ref('')
const resultOk = ref(false)
const copied = ref(false)

onMounted(async () => {
  machineId.value = await getMachineId()
  const info = await getLicenseInfo() as Record<string, any>
  trialRemaining.value = info.trial_remaining ?? 0
})

function copyMachineId() {
  navigator.clipboard.writeText(machineId.value)
  copied.value = true
  globalThis.setTimeout(() => { copied.value = false }, 2000)
}

async function handleActivate() {
  const code = activationCode.value.trim()
  if (!code) return
  activating.value = true
  resultMsg.value = ''
  try {
    const res = await activateLicense(code)
    resultMsg.value = res.message
    resultOk.value = res.success
    if (res.success) {
      globalThis.setTimeout(() => emit('activated'), 800)
    }
  } catch (e: any) {
    resultMsg.value = e.message || '激活请求失败，请检查网络连接'
    resultOk.value = false
  } finally {
    activating.value = false
  }
}

function skipTrial() {
  emit('activated')
}
</script>

<template>
  <div class="min-h-screen bg-[#2e3132] flex items-center justify-center">
    <div class="w-[460px] bg-surface-container-lowest rounded-2xl shadow-2xl overflow-hidden">
      <!-- Header -->
      <div class="bg-gradient-to-br from-primary to-primary-container px-10 pt-10 pb-8 text-center">
        <h1 class="text-2xl font-bold text-white tracking-tight">CutPilot</h1>
        <p class="text-white/70 text-sm mt-1">AI 短视频智能剪辑工具</p>
      </div>

      <div class="px-10 py-8 space-y-6">
        <!-- Step 1: Machine ID -->
        <div>
          <div class="flex items-center gap-2 mb-3">
            <span class="w-6 h-6 rounded-full bg-primary text-white text-xs font-bold flex items-center justify-center">1</span>
            <span class="text-sm font-semibold text-on-surface">复制你的机器码，发给管理员</span>
          </div>
          <div class="bg-surface-container-highest rounded-lg p-3 flex items-center justify-between group">
            <code class="text-sm font-mono text-on-surface select-all">{{ machineId }}</code>
            <button
              class="px-3 py-1.5 text-xs font-semibold rounded-md transition-all"
              :class="copied ? 'bg-green-100 text-green-700' : 'bg-surface-container text-primary hover:bg-primary-fixed'"
              @click="copyMachineId"
            >{{ copied ? '已复制' : '复制' }}</button>
          </div>
        </div>

        <!-- Step 2: Enter Code -->
        <div>
          <div class="flex items-center gap-2 mb-3">
            <span class="w-6 h-6 rounded-full bg-primary text-white text-xs font-bold flex items-center justify-center">2</span>
            <span class="text-sm font-semibold text-on-surface">输入管理员发来的激活码</span>
          </div>
          <input
            v-model="activationCode"
            class="w-full bg-surface-container-highest border-none rounded-lg py-3 px-4 text-sm font-mono focus:ring-2 focus:ring-primary/30 placeholder:text-outline"
            placeholder="CP-XXXXXXXX-XXXXXXXX-XXXXXXXXXXXX"
            type="text"
            @keyup.enter="handleActivate"
          />
          <p v-if="resultMsg" class="text-xs mt-2 font-medium" :class="resultOk ? 'text-green-600' : 'text-error'">
            {{ resultOk ? '✓ ' : '' }}{{ resultMsg }}
          </p>
        </div>

        <!-- Activate button -->
        <button
          class="w-full py-3 bg-primary text-white font-bold text-sm rounded-xl hover:bg-primary-container active:scale-[0.98] transition-all disabled:opacity-50"
          :disabled="!activationCode.trim() || activating"
          @click="handleActivate"
        >{{ activating ? '验证中...' : '激活' }}</button>

        <!-- Trial skip -->
        <div v-if="trialRemaining > 0" class="text-center">
          <button class="text-xs text-on-surface-variant hover:text-primary transition-colors" @click="skipTrial">
            暂不激活，试用体验（剩余 {{ trialRemaining }} 次）
          </button>
        </div>
      </div>

      <!-- Footer -->
      <div class="px-10 py-4 bg-surface-container-low text-center">
        <p class="text-[10px] text-on-surface-variant/50">CutPilot v4.2 · 如需帮助请联系管理员</p>
      </div>
    </div>
  </div>
</template>
