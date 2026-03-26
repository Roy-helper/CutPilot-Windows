<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { checkAsrStatus, downloadAsrModel, getEncoderInfo } from '@/bridge'

const emit = defineEmits<{ ready: [] }>()

interface CheckItem {
  label: string
  icon: string
  status: 'checking' | 'ok' | 'missing' | 'downloading' | 'error'
  detail: string
  action?: string
}

const items = ref<CheckItem[]>([
  { label: 'FFmpeg 视频引擎', icon: 'movie', status: 'checking', detail: '检测中...' },
  { label: '硬件加速编码器', icon: 'speed', status: 'checking', detail: '检测中...' },
  { label: '语音识别模型', icon: 'mic', status: 'checking', detail: '检测中...' },
])

const allReady = ref(false)
const hasAction = ref(false)

onMounted(async () => {
  // Check FFmpeg
  const ffmpeg = items.value[0]!
  try {
    const enc = await getEncoderInfo()
    ffmpeg.status = 'ok'
    ffmpeg.detail = enc.name
  } catch {
    ffmpeg.status = 'error'
    ffmpeg.detail = '未检测到 FFmpeg，请安装后重启'
  }

  // Check encoder
  const encoder = items.value[1]!
  try {
    const enc = await getEncoderInfo()
    encoder.status = 'ok'
    encoder.detail = enc.is_hardware ? `${enc.name} (硬件加速)` : enc.name
  } catch {
    encoder.status = 'ok'
    encoder.detail = 'Software x264'
  }

  // Check ASR
  const asr = items.value[2]!
  const asrStatus = await checkAsrStatus()
  if (asrStatus.models_cached) {
    asr.status = 'ok'
    asr.detail = asrStatus.message
  } else if (asrStatus.installed) {
    asr.status = 'missing'
    asr.detail = '需要下载语音模型（约 461MB）'
    asr.action = 'download'
    hasAction.value = true
  } else {
    asr.status = 'error'
    asr.detail = '语音识别引擎未安装'
  }

  checkAllReady()
})

function checkAllReady() {
  allReady.value = items.value.every(i => i.status === 'ok')
  hasAction.value = items.value.some(i => i.action)
}

async function installAll() {
  const asr = items.value[2]!
  if (asr.status === 'missing' || asr.action === 'download') {
    asr.status = 'downloading'
    asr.detail = '正在下载语音模型（约 461MB），请勿关闭...'
    asr.action = undefined

    const res = await downloadAsrModel()
    if (res.success) {
      asr.status = 'ok'
      asr.detail = '语音识别就绪'
    } else {
      asr.status = 'error'
      asr.detail = res.message
    }
  }
  hasAction.value = false
  checkAllReady()
}

const statusIcon: Record<string, string> = {
  checking: 'hourglass_empty',
  ok: 'check_circle',
  missing: 'download',
  downloading: 'progress_activity',
  error: 'error',
}

const statusColor: Record<string, string> = {
  checking: 'text-on-surface-variant',
  ok: 'text-green-600',
  missing: 'text-primary',
  downloading: 'text-primary animate-spin',
  error: 'text-error',
}
</script>

<template>
  <div class="min-h-screen bg-[#2e3132] flex items-center justify-center">
    <div class="w-[500px] bg-surface-container-lowest rounded-2xl shadow-2xl overflow-hidden">
      <!-- Header -->
      <div class="bg-gradient-to-br from-primary to-primary-container px-10 pt-10 pb-8 text-center">
        <h1 class="text-2xl font-bold text-white tracking-tight">环境检测</h1>
        <p class="text-white/70 text-sm mt-1">首次启动需要配置运行环境</p>
      </div>

      <div class="px-10 py-8 space-y-4">
        <div
          v-for="(item, i) in items"
          :key="i"
          class="flex items-center gap-4 p-4 rounded-xl bg-surface-container-low"
        >
          <span class="material-symbols-outlined text-on-surface-variant">{{ item.icon }}</span>
          <div class="flex-1 min-w-0">
            <p class="text-sm font-semibold text-on-surface">{{ item.label }}</p>
            <p class="text-xs text-on-surface-variant truncate">{{ item.detail }}</p>
          </div>
          <span
            class="material-symbols-outlined text-xl"
            :class="statusColor[item.status]"
            :style="item.status === 'downloading' ? 'animation-duration: 1.5s' : ''"
            style="font-variation-settings: 'FILL' 1"
          >{{ statusIcon[item.status] }}</span>
        </div>

        <!-- Install button -->
        <button
          v-if="hasAction"
          class="w-full py-3 bg-primary text-white font-bold text-sm rounded-xl hover:bg-primary-container active:scale-[0.98] transition-all mt-4"
          @click="installAll"
        >
          <span class="material-symbols-outlined text-sm align-middle mr-1">download</span>
          一键安装所有依赖
        </button>

        <!-- Continue button -->
        <button
          v-if="allReady"
          class="w-full py-3 bg-primary text-white font-bold text-sm rounded-xl hover:bg-primary-container active:scale-[0.98] transition-all mt-4"
          @click="emit('ready')"
        >
          开始使用 CutPilot
          <span class="material-symbols-outlined text-sm align-middle ml-1">arrow_forward</span>
        </button>

        <!-- Skip (if only ASR missing, can still use app for other things) -->
        <div v-if="!allReady && !hasAction" class="text-center pt-2">
          <button class="text-xs text-on-surface-variant hover:text-primary" @click="emit('ready')">
            跳过，稍后再安装
          </button>
        </div>
      </div>

      <div class="px-10 py-4 bg-surface-container-low text-center">
        <p class="text-[10px] text-on-surface-variant/50">首次下载后，后续使用无需联网</p>
      </div>
    </div>
  </div>
</template>
