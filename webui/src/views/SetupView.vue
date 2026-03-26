<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { checkAsrStatus, downloadAsrModel, runBenchmark, type BenchmarkResult } from '@/bridge'

const emit = defineEmits<{ ready: [] }>()

const benchmark = ref<BenchmarkResult | null>(null)
const benchmarking = ref(true)

const modelReady = ref(false)
const downloading = ref(false)
const downloadMsg = ref('')
const downloadOk = ref(false)

const allReady = computed(() => !benchmarking.value && modelReady.value)

onMounted(async () => {
  // Benchmark
  try {
    benchmark.value = await runBenchmark()
  } catch {
    benchmark.value = { max_parallel: 1, cpu_cores: 1, ram_gb: 0, encoder: 'unknown', is_hardware: false, reason: '检测失败' }
  }
  benchmarking.value = false

  // ASR model
  const status = await checkAsrStatus()
  modelReady.value = status.ready
})

const downloadFailed = ref(false)

async function handleDownload() {
  downloading.value = true
  downloadFailed.value = false
  downloadMsg.value = '正在下载语音模型（约 500MB），请耐心等待...'
  try {
    const res = await downloadAsrModel()
    downloadMsg.value = res.message
    downloadOk.value = res.success
    downloadFailed.value = !res.success
    if (res.success) modelReady.value = true
  } catch (e: any) {
    downloadMsg.value = e.message || '下载失败，请检查网络连接'
    downloadOk.value = false
    downloadFailed.value = true
  } finally {
    downloading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-[#2e3132] flex items-center justify-center">
    <div class="w-[500px] bg-surface-container-lowest rounded-2xl shadow-2xl overflow-hidden">
      <div class="bg-gradient-to-br from-primary to-primary-container px-10 pt-8 pb-6 text-center">
        <h1 class="text-2xl font-bold text-white tracking-tight">环境配置</h1>
        <p class="text-white/70 text-sm mt-1">首次使用需要下载语音识别模型</p>
      </div>

      <div class="px-10 py-6 space-y-5">
        <!-- Hardware info -->
        <div v-if="benchmark" class="grid grid-cols-3 gap-3">
          <div class="p-3 rounded-xl bg-surface-container-low text-center">
            <p class="text-2xl font-bold text-primary">{{ benchmark.cpu_cores }}</p>
            <p class="text-[10px] font-bold text-on-surface-variant uppercase">CPU 核心</p>
          </div>
          <div class="p-3 rounded-xl bg-surface-container-low text-center">
            <p class="text-2xl font-bold text-primary">{{ benchmark.ram_gb }}</p>
            <p class="text-[10px] font-bold text-on-surface-variant uppercase">可用内存 GB</p>
          </div>
          <div class="p-3 rounded-xl bg-surface-container-low text-center">
            <p class="text-2xl font-bold text-primary">{{ benchmark.max_parallel }}</p>
            <p class="text-[10px] font-bold text-on-surface-variant uppercase">最大并行</p>
          </div>
        </div>

        <!-- Model status -->
        <div v-if="modelReady" class="flex items-center gap-3 p-4 rounded-xl bg-green-50">
          <span class="material-symbols-outlined text-green-600" style="font-variation-settings: 'FILL' 1">check_circle</span>
          <span class="text-sm font-medium text-green-700">语音模型已就绪，可以开始使用</span>
        </div>

        <div v-else class="space-y-3">
          <div class="p-4 rounded-xl bg-surface-container-low">
            <div class="flex items-start gap-3">
              <span class="material-symbols-outlined text-primary mt-0.5">mic</span>
              <div>
                <p class="text-sm font-semibold text-on-surface">语音识别模型</p>
                <p class="text-xs text-on-surface-variant mt-1">Whisper 语音识别引擎，下载约 500MB，下载后可完全离线使用</p>
              </div>
            </div>
          </div>

          <button
            class="w-full py-3 bg-primary text-white font-bold text-sm rounded-xl hover:bg-primary-container active:scale-[0.98] transition-all disabled:opacity-50"
            :disabled="downloading"
            @click="handleDownload"
          >
            <template v-if="downloading">
              <span class="material-symbols-outlined text-sm align-middle mr-1 animate-spin" style="animation-duration: 1.5s">progress_activity</span>
              下载中，请勿关闭...
            </template>
            <template v-else>
              <span class="material-symbols-outlined text-sm align-middle mr-1">download</span>
              {{ downloadFailed ? '重试下载 (500MB)' : '下载语音模型 (500MB)' }}
            </template>
          </button>

          <p v-if="downloadMsg" class="text-xs text-center" :class="downloadOk ? 'text-green-600' : downloading ? 'text-on-surface-variant' : 'text-error'">
            {{ downloadMsg }}
          </p>
        </div>

        <!-- Continue -->
        <button
          v-if="allReady"
          class="w-full py-3 bg-primary text-white font-bold text-sm rounded-xl hover:bg-primary-container active:scale-[0.98] transition-all"
          @click="emit('ready')"
        >
          开始使用 CutPilot
          <span class="material-symbols-outlined text-sm align-middle ml-1">arrow_forward</span>
        </button>

        <div v-if="!modelReady" class="text-center">
          <button class="text-xs text-on-surface-variant hover:text-primary" @click="emit('ready')">跳过，稍后在设置中下载</button>
        </div>
      </div>

      <div class="px-10 py-3 bg-surface-container-low text-center">
        <p class="text-[10px] text-on-surface-variant/50">模型保存在本地，后续使用无需重复下载</p>
      </div>
    </div>
  </div>
</template>
