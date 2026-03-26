<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { checkAsrStatus, downloadAsrModel, runBenchmark, type BenchmarkResult } from '@/bridge'

const emit = defineEmits<{ ready: [] }>()

// Benchmark state
const benchmarkDone = ref(false)
const benchmark = ref<BenchmarkResult | null>(null)
const benchmarking = ref(true)

// ASR state
const asrCached = ref(false)
const asrEngine = ref<'whisper' | 'funasr'>('whisper')
const whisperAvailable = ref(false)
const funasr_available = ref(false)
const downloading = ref(false)
const downloadResult = ref('')
const downloadOk = ref(false)

const allReady = computed(() => benchmarkDone.value && asrCached.value)

onMounted(async () => {
  // Run benchmark
  benchmarking.value = true
  try {
    benchmark.value = await runBenchmark()
  } catch {
    benchmark.value = { max_parallel: 1, cpu_cores: 1, ram_gb: 0, encoder: 'unknown', is_hardware: false, reason: '检测失败' }
  }
  benchmarkDone.value = true
  benchmarking.value = false

  // Check ASR
  const asr = await checkAsrStatus() as Record<string, any>
  asrCached.value = asr.models_cached
  whisperAvailable.value = asr.whisper_available ?? false
  funasr_available.value = asr.funasr_available ?? false

  // Default to whichever is available
  if (whisperAvailable.value) asrEngine.value = 'whisper'
  else if (funasr_available.value) asrEngine.value = 'funasr'
})

async function handleDownload() {
  downloading.value = true
  downloadResult.value = ''
  const res = await downloadAsrModel(asrEngine.value)
  downloadResult.value = res.message
  downloadOk.value = res.success
  if (res.success) asrCached.value = true
  downloading.value = false
}
</script>

<template>
  <div class="min-h-screen bg-[#2e3132] flex items-center justify-center">
    <div class="w-[540px] bg-surface-container-lowest rounded-2xl shadow-2xl overflow-hidden">
      <!-- Header -->
      <div class="bg-gradient-to-br from-primary to-primary-container px-10 pt-8 pb-6 text-center">
        <h1 class="text-2xl font-bold text-white tracking-tight">环境检测</h1>
        <p class="text-white/70 text-sm mt-1">检测您的电脑性能，配置最佳运行方案</p>
      </div>

      <div class="px-10 py-6 space-y-5">
        <!-- Section 1: Hardware Benchmark -->
        <div>
          <h3 class="text-xs font-bold text-on-surface-variant uppercase tracking-widest mb-3">硬件性能</h3>

          <div v-if="benchmarking" class="flex items-center gap-3 p-4 rounded-xl bg-surface-container-low">
            <span class="material-symbols-outlined text-primary animate-spin" style="animation-duration: 1.5s">progress_activity</span>
            <span class="text-sm text-on-surface-variant">正在检测电脑性能...</span>
          </div>

          <div v-else-if="benchmark" class="space-y-2">
            <div class="grid grid-cols-3 gap-3">
              <div class="p-3 rounded-xl bg-surface-container-low text-center">
                <p class="text-2xl font-bold text-primary">{{ benchmark.cpu_cores }}</p>
                <p class="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">CPU 核心</p>
              </div>
              <div class="p-3 rounded-xl bg-surface-container-low text-center">
                <p class="text-2xl font-bold text-primary">{{ benchmark.ram_gb }}</p>
                <p class="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">可用内存 GB</p>
              </div>
              <div class="p-3 rounded-xl bg-surface-container-low text-center">
                <p class="text-2xl font-bold text-primary">{{ benchmark.max_parallel }}</p>
                <p class="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">最大并行</p>
              </div>
            </div>
            <div class="flex items-center gap-2 px-1">
              <span class="material-symbols-outlined text-sm" :class="benchmark.is_hardware ? 'text-green-600' : 'text-on-surface-variant'" style="font-variation-settings: 'FILL' 1">{{ benchmark.is_hardware ? 'check_circle' : 'info' }}</span>
              <span class="text-xs text-on-surface-variant">
                编码器: {{ benchmark.encoder }}{{ benchmark.is_hardware ? ' (硬件加速)' : '' }}
                · {{ benchmark.reason }}
              </span>
            </div>
          </div>
        </div>

        <!-- Section 2: ASR Engine -->
        <div>
          <h3 class="text-xs font-bold text-on-surface-variant uppercase tracking-widest mb-3">语音识别引擎</h3>

          <div v-if="asrCached" class="flex items-center gap-3 p-4 rounded-xl bg-green-50">
            <span class="material-symbols-outlined text-green-600" style="font-variation-settings: 'FILL' 1">check_circle</span>
            <span class="text-sm font-medium text-green-700">语音识别已就绪</span>
          </div>

          <div v-else class="space-y-3">
            <!-- Whisper option (only if importable) -->
            <label
              v-if="whisperAvailable"
              class="flex items-start gap-4 p-4 rounded-xl border-2 cursor-pointer transition-all"
              :class="asrEngine === 'whisper' ? 'border-primary bg-primary-fixed/10' : 'border-surface-container hover:border-outline-variant'"
            >
              <input v-model="asrEngine" type="radio" value="whisper" class="mt-1 text-primary focus:ring-primary" />
              <div class="flex-1">
                <p class="text-sm font-semibold text-on-surface">Whisper <span class="text-xs font-normal text-on-surface-variant ml-1">推荐</span></p>
                <p class="text-xs text-on-surface-variant mt-1">OpenAI 开源语音识别 · 下载 461MB · 中文识别效果好 · 速度快</p>
              </div>
              <span class="text-xs text-outline whitespace-nowrap">461 MB</span>
            </label>

            <!-- FunASR option (only if importable) -->
            <label
              v-if="funasr_available"
              class="flex items-start gap-4 p-4 rounded-xl border-2 cursor-pointer transition-all"
              :class="asrEngine === 'funasr' ? 'border-primary bg-primary-fixed/10' : 'border-surface-container hover:border-outline-variant'"
            >
              <input v-model="asrEngine" type="radio" value="funasr" class="mt-1 text-primary focus:ring-primary" />
              <div class="flex-1">
                <p class="text-sm font-semibold text-on-surface">FunASR <span class="text-xs font-normal text-on-surface-variant ml-1">专业版</span></p>
                <p class="text-xs text-on-surface-variant mt-1">阿里达摩院语音识别 · 下载约 2GB · 中文最优 · 支持热词和说话人识别</p>
              </div>
              <span class="text-xs text-outline whitespace-nowrap">~2 GB</span>
            </label>

            <!-- Neither available -->
            <div v-if="!whisperAvailable && !funasr_available" class="p-4 rounded-xl bg-error-container/20 text-center">
              <p class="text-sm text-error font-medium">语音识别引擎未安装</p>
              <p class="text-xs text-on-surface-variant mt-1">请联系管理员检查安装包</p>
            </div>

            <!-- Download button -->
            <button
              class="w-full py-3 bg-primary text-white font-bold text-sm rounded-xl hover:bg-primary-container active:scale-[0.98] transition-all disabled:opacity-50"
              :disabled="downloading"
              @click="handleDownload"
            >
              <template v-if="downloading">
                <span class="material-symbols-outlined text-sm align-middle mr-1 animate-spin" style="animation-duration: 1.5s">progress_activity</span>
                正在下载，请勿关闭...
              </template>
              <template v-else>
                <span class="material-symbols-outlined text-sm align-middle mr-1">download</span>
                下载 {{ asrEngine === 'whisper' ? 'Whisper (461MB)' : 'FunASR (~2GB)' }}
              </template>
            </button>

            <p v-if="downloadResult" class="text-xs text-center" :class="downloadOk ? 'text-green-600' : 'text-error'">
              {{ downloadResult }}
            </p>
          </div>
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

        <div v-if="!allReady" class="text-center">
          <button class="text-xs text-on-surface-variant hover:text-primary transition-colors" @click="emit('ready')">
            跳过，稍后在设置中配置
          </button>
        </div>
      </div>

      <div class="px-10 py-3 bg-surface-container-low text-center">
        <p class="text-[10px] text-on-surface-variant/50">模型下载后保存在本地，后续使用无需重复下载</p>
      </div>
    </div>
  </div>
</template>
