<script setup lang="ts">
import { ref, watch, onMounted, nextTick } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import TopBar from '@/components/TopBar.vue'
import {
  getMachineId, getLicenseInfo, activateLicense, loadSettings, saveSettings as bridgeSave,
  getProviders as bridgeProviders, testConnection as bridgeTest,
  selectDirectory, getEncoderInfo, getMaxParallel, checkAsrStatus, downloadAsrModel,
  type ProviderPreset,
} from '@/bridge'

const provider = ref('deepseek')
const apiKey = ref('')
const showApiKey = ref(false)

const maxVersions = ref(3)
const minSentences = ref(15)
const quality = ref('4K')
const generateFast = ref(true)
const enableHook = ref(false)
const enableDiarization = ref(false)
const hookDuration = ref(3.0)

const hotwords = ref('')
const outputDir = ref('')

// Quality mapping: UI label <-> backend value
const qualityToBackend: Record<string, string> = {
  '720P': 'draft',
  '1080P': 'standard',
  '4K': 'high',
}
const qualityFromBackend: Record<string, string> = {
  draft: '720P',
  standard: '1080P',
  high: '4K',
}

const machineId = ref('...')
const licenseStatus = ref('...')
const licenseExpiry = ref('...')

const activationCode = ref('')
const activating = ref(false)
const activateResult = ref('')

const providers = ref<{ id: string; name: string }[]>([])
const testResult = ref<string | null>(null)
const saving = ref(false)
const saveMsg = ref<string | null>(null)
const saveMsgType = ref<'success' | 'error'>('success')
const detectedEncoder = ref('自动检测中...')
const detectedParallel = ref(0)
const asrEngine = ref('faster-whisper')
const asrModelReady = ref(false)
const asrDownloading = ref(false)
const asrDownloadMsg = ref('')
const isDirty = ref(false)

onMounted(async () => {
  try {
    const p = await bridgeProviders()
    providers.value = p.map((pr: ProviderPreset) => ({ id: pr.id, name: pr.name }))
  } catch { /* dev mode */ }

  try {
    machineId.value = await getMachineId()
    await refreshLicense()
  } catch { /* dev mode */ }

  try {
    const s = await loadSettings()
    if (s.provider) provider.value = s.provider as string
    if (s.api_key) apiKey.value = s.api_key as string
    if (s.max_versions) maxVersions.value = s.max_versions as number
    if (s.min_sentences) minSentences.value = s.min_sentences as number
    if (s.video_quality) quality.value = qualityFromBackend[s.video_quality as string] ?? '1080P'
    if (s.hotwords) hotwords.value = s.hotwords as string
    if (s.output_dir) outputDir.value = s.output_dir as string
    if (s.generate_fast != null) generateFast.value = s.generate_fast as boolean
    if (s.enable_hook_overlay != null) enableHook.value = s.enable_hook_overlay as boolean
    if (s.asr_engine) asrEngine.value = s.asr_engine as string
    if (s.enable_speaker_diarization != null) enableDiarization.value = s.enable_speaker_diarization as boolean
    if (s.hook_duration != null) hookDuration.value = s.hook_duration as number
  } catch { /* dev mode */ }

  try {
    const enc = await getEncoderInfo()
    detectedEncoder.value = enc.is_hardware ? `${enc.name} (${enc.codec})` : `${enc.name}`
    detectedParallel.value = await getMaxParallel()
  } catch { /* dev mode */ }

  try {
    const asr = await checkAsrStatus(asrEngine.value)
    asrModelReady.value = asr.ready
  } catch { /* dev mode */ }

  // Mark clean after initial load, then watch for changes
  await nextTick()
  isDirty.value = false
  watch(
    [provider, apiKey, maxVersions, minSentences, quality,
     generateFast, enableHook, enableDiarization, hookDuration, hotwords,
     outputDir, asrEngine],
    () => { isDirty.value = true },
  )
})

onBeforeRouteLeave((_to, _from, next) => {
  if (isDirty.value && !saving.value) {
    const leave = confirm('有未保存的设置更改，确定要离开吗？')
    next(leave)
  } else {
    next()
  }
})

function copyMachineId() {
  navigator.clipboard.writeText(machineId.value)
}

async function refreshLicense() {
  const license = await getLicenseInfo() as Record<string, any>
  licenseStatus.value = license.is_valid ? '已激活' : (license.status_message ?? '未激活')
  licenseExpiry.value = license.expiry ?? '-'
}

async function handleActivate() {
  if (!activationCode.value.trim()) return
  activating.value = true
  activateResult.value = ''
  const res = await activateLicense(activationCode.value.trim())
  activateResult.value = res.message ?? (res.success ? '激活成功！' : '激活失败')
  if (res.success) {
    await refreshLicense()
    activationCode.value = ''
  }
  activating.value = false
}

async function handleAsrDownload() {
  asrDownloading.value = true
  asrDownloadMsg.value = '正在下载语音模型...'
  const res = await downloadAsrModel(asrEngine.value)
  asrDownloadMsg.value = res.message
  asrModelReady.value = res.success
  asrDownloading.value = false
}

async function handleEngineChange() {
  asrDownloadMsg.value = ''
  try {
    const asr = await checkAsrStatus(asrEngine.value)
    asrModelReady.value = asr.ready
  } catch { /* dev mode */ }
}

async function testConnection() {
  testResult.value = '测试中...'
  const res = await bridgeTest(provider.value, apiKey.value)
  testResult.value = res.success ? `连接成功 (${res.model})` : `失败: ${res.error}`
  setTimeout(() => { testResult.value = null }, 5000)
}

async function saveAllSettings() {
  saving.value = true
  saveMsg.value = null
  try {
    const res = await bridgeSave({
      provider: provider.value,
      api_key: apiKey.value,
      max_versions: maxVersions.value,
      min_sentences: minSentences.value,
      video_quality: qualityToBackend[quality.value] ?? 'standard',
      asr_engine: asrEngine.value,
      hotwords: hotwords.value,
      output_dir: outputDir.value,
      generate_fast: generateFast.value,
      enable_hook_overlay: enableHook.value,
      enable_speaker_diarization: enableDiarization.value,
      hook_duration: hookDuration.value,
    })
    if (res && res.error) {
      saveMsgType.value = 'error'
      saveMsg.value = `保存失败: ${res.error}`
    } else {
      saveMsgType.value = 'success'
      saveMsg.value = '保存完成'
      isDirty.value = false
    }
  } catch (e: any) {
    saveMsgType.value = 'error'
    saveMsg.value = `保存失败: ${e.message || e}`
  }
  saving.value = false
  setTimeout(() => { saveMsg.value = null }, 3000)
}

function resetToDefaults() {
  if (!globalThis.confirm('确定要恢复所有设置为默认值吗？')) return
  provider.value = 'deepseek'
  apiKey.value = ''
  maxVersions.value = 3
  minSentences.value = 15
  quality.value = '4K'
  generateFast.value = true
  enableHook.value = false
  asrEngine.value = 'faster-whisper'
  enableDiarization.value = false
  hookDuration.value = 3.0
  hotwords.value = ''
  outputDir.value = ''
  saveAllSettings()
}

async function browseOutputDir() {
  const dir = await selectDirectory()
  if (dir) outputDir.value = dir
}
</script>

<template>
  <TopBar search-placeholder="" />

  <div class="max-w-[1280px] mx-auto p-12">
    <div class="mb-10">
      <h2 class="text-3xl font-bold tracking-tight text-on-surface">系统设置</h2>
      <p class="text-on-surface-variant mt-2 text-sm">管理您的 AI 处理引擎、模型权限及导出首选项</p>
    </div>

    <div class="grid grid-cols-12 gap-8">
      <!-- Left Column -->
      <section class="col-span-12 lg:col-span-4 space-y-6">
        <!-- License -->
        <div class="bg-surface-container-low p-8 rounded-xl">
          <div class="flex items-center gap-3 mb-6">
            <span class="material-symbols-outlined text-primary">verified</span>
            <h3 class="font-semibold text-sm uppercase tracking-widest text-on-surface-variant">授权详情</h3>
          </div>
          <div class="space-y-6">
            <div>
              <label class="block text-[10px] uppercase font-bold text-outline tracking-wider mb-2">机器码 (Hardware ID)</label>
              <div class="bg-surface-container-highest font-mono text-xs p-3 rounded-md flex justify-between items-center group">
                <span class="truncate">{{ machineId }}</span>
                <button class="opacity-0 group-hover:opacity-100 transition-opacity" @click="copyMachineId">
                  <span class="material-symbols-outlined text-sm">content_copy</span>
                </button>
              </div>
            </div>
            <div class="flex justify-between items-center py-2 border-b border-outline-variant/10">
              <span class="text-sm font-medium">授权状态</span>
              <span class="px-2 py-0.5 text-[10px] font-bold rounded uppercase" :class="licenseStatus === '未激活' || licenseStatus.includes('过期') ? 'bg-error-container text-on-error-container' : 'bg-green-100 text-green-700'">{{ licenseStatus }}</span>
            </div>
            <div class="flex justify-between items-center py-2 border-b border-outline-variant/10">
              <span class="text-sm font-medium">到期日期</span>
              <span class="text-sm text-on-surface-variant">{{ licenseExpiry }}</span>
            </div>
            <!-- Activation code input -->
            <div class="pt-2">
              <label class="block text-[10px] uppercase font-bold text-outline tracking-wider mb-2">输入激活码</label>
              <div class="flex gap-2">
                <input
                  v-model="activationCode"
                  class="flex-1 bg-surface-container-highest border-none rounded-md py-2.5 px-4 text-sm font-mono focus:ring-2 focus:ring-primary/20"
                  placeholder="CP-XXXXXXXX-XXXXXXXX-XXXXXXXXXXXX"
                  type="text"
                />
                <button
                  class="px-4 py-2 bg-primary text-white text-sm font-semibold rounded-md hover:bg-primary-container transition-all disabled:opacity-50"
                  :disabled="!activationCode.trim() || activating"
                  @click="handleActivate"
                >{{ activating ? '验证中...' : '激活' }}</button>
              </div>
              <p v-if="activateResult" class="text-xs mt-2" :class="activateResult.startsWith('激活成功') ? 'text-green-600' : 'text-error'">{{ activateResult }}</p>
            </div>
          </div>
        </div>

        <!-- ASR -->
        <div class="bg-surface-container-low p-8 rounded-xl">
          <div class="flex items-center gap-3 mb-6">
            <span class="material-symbols-outlined text-primary">mic</span>
            <h3 class="font-semibold text-sm uppercase tracking-widest text-on-surface-variant">语音识别</h3>
          </div>
          <div class="space-y-4">
            <!-- ASR engine selector -->
            <div class="space-y-2">
              <label class="block text-[10px] uppercase font-bold text-outline tracking-wider">识别引擎</label>
              <select
                v-model="asrEngine"
                class="w-full bg-surface-container-highest border-none rounded-md py-3 px-4 text-sm focus:ring-2 focus:ring-primary/20"
                @change="handleEngineChange"
              >
                <option value="faster-whisper">Faster Whisper (轻量推荐)</option>
                <option value="funasr">FunASR (中文增强, 需下载 2GB+)</option>
              </select>
            </div>
            <!-- ASR model status -->
            <div class="flex justify-between items-center py-2 border-b border-outline-variant/10">
              <span class="text-sm font-medium">语音模型</span>
              <div class="flex items-center gap-2">
                <span v-if="asrModelReady" class="px-2 py-0.5 bg-green-100 text-green-700 text-[10px] font-bold rounded uppercase">已就绪</span>
                <span v-else class="px-2 py-0.5 bg-error-container text-on-error-container text-[10px] font-bold rounded uppercase">未安装</span>
                <button
                  v-if="!asrModelReady"
                  class="text-xs font-bold text-primary hover:underline"
                  :disabled="asrDownloading"
                  @click="handleAsrDownload"
                >{{ asrDownloading ? '下载中...' : asrEngine === 'funasr' ? '下载 FunASR (~2GB)' : '下载 (461MB)' }}</button>
              </div>
            </div>
            <p v-if="asrDownloadMsg" class="text-xs" :class="asrModelReady ? 'text-green-600' : 'text-error'">{{ asrDownloadMsg }}</p>

            <label class="block text-[10px] uppercase font-bold text-outline tracking-wider">专有热词输入 (Hotwords)</label>
            <textarea
              v-model="hotwords"
              class="w-full bg-surface-container-highest border-none rounded-md p-4 text-sm focus:ring-2 focus:ring-primary/20 focus:bg-surface-container-lowest transition-all resize-none"
              placeholder="输入行业术语、人名或品牌名，以逗号分隔..."
              rows="4"
            ></textarea>
            <p class="text-[10px] text-on-surface-variant italic">提示：输入精确热词可显著提升专业术语识别率</p>
          </div>
        </div>
      </section>

      <!-- Right Column -->
      <div class="col-span-12 lg:col-span-8 space-y-8">
        <!-- AI Model -->
        <div class="bg-surface-container-low p-8 rounded-xl">
          <div class="flex items-center justify-between mb-8">
            <div class="flex items-center gap-3">
              <span class="material-symbols-outlined text-primary">hub</span>
              <h3 class="font-semibold text-sm uppercase tracking-widest text-on-surface-variant">AI 模型配置</h3>
            </div>
            <div class="flex items-center gap-3">
              <span v-if="testResult" class="text-xs font-medium" :class="testResult.startsWith('连接') ? 'text-green-600' : testResult === '测试中...' ? 'text-primary' : 'text-error'">{{ testResult }}</span>
              <button class="text-xs font-bold text-primary flex items-center gap-1 hover:underline" @click="testConnection">
                <span class="material-symbols-outlined text-sm">bolt</span> 测试连接
              </button>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-6">
            <div class="space-y-2">
              <label class="block text-[10px] uppercase font-bold text-outline tracking-wider">供应商 (Provider)</label>
              <select
                v-model="provider"
                class="w-full bg-surface-container-highest border-none rounded-md py-3 px-4 text-sm focus:ring-2 focus:ring-primary/20"
              >
                <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
              </select>
            </div>
            <div class="space-y-2">
              <label class="block text-[10px] uppercase font-bold text-outline tracking-wider">API Key</label>
              <div class="relative">
                <input
                  v-model="apiKey"
                  class="w-full bg-surface-container-highest border-none rounded-md py-3 px-4 text-sm focus:ring-2 focus:ring-primary/20"
                  :type="showApiKey ? 'text' : 'password'"
                  placeholder="sk-..."
                />
                <button class="absolute right-3 top-1/2 -translate-y-1/2" @click="showApiKey = !showApiKey">
                  <span class="material-symbols-outlined text-on-surface-variant text-sm">
                    {{ showApiKey ? 'visibility_off' : 'visibility' }}
                  </span>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Processing -->
        <div class="bg-surface-container-low p-8 rounded-xl">
          <div class="flex items-center gap-3 mb-8">
            <span class="material-symbols-outlined text-primary">settings_input_component</span>
            <h3 class="font-semibold text-sm uppercase tracking-widest text-on-surface-variant">处理参数</h3>
          </div>
          <div class="grid grid-cols-2 gap-x-12 gap-y-8">
            <!-- 版本迭代数 slider -->
            <div class="space-y-4">
              <div class="flex justify-between items-center">
                <label class="text-sm font-medium">版本迭代数</label>
                <span class="text-primary font-bold">{{ maxVersions }}</span>
              </div>
              <input
                v-model.number="maxVersions"
                class="w-full h-1.5 bg-surface-container-highest rounded-lg appearance-none cursor-pointer accent-primary"
                type="range" min="1" max="12"
              />
            </div>
            <!-- 最少句数 stepper -->
            <div class="space-y-4">
              <div class="flex justify-between items-center">
                <label class="text-sm font-medium">最少句数</label>
                <span class="text-primary font-bold">{{ minSentences }}</span>
              </div>
              <div class="flex gap-2">
                <button class="flex-1 py-2 rounded bg-surface-container-highest text-sm font-bold hover:bg-surface-container-high" @click="minSentences = Math.max(1, minSentences - 1)">-</button>
                <input v-model.number="minSentences" class="w-16 bg-transparent border-none text-center font-bold text-sm" type="text" />
                <button class="flex-1 py-2 rounded bg-surface-container-highest text-sm font-bold hover:bg-surface-container-high" @click="minSentences = Math.min(50, minSentences + 1)">+</button>
              </div>
            </div>
            <!-- 视频质量 segmented control -->
            <div class="space-y-2">
              <label class="block text-[10px] uppercase font-bold text-outline tracking-wider">视频质量</label>
              <div class="flex gap-2 p-1 bg-surface-container-highest rounded-lg">
                <button
                  v-for="q in ['720P', '1080P', '4K']" :key="q"
                  class="flex-1 py-2 text-xs font-bold rounded-md transition-all"
                  :class="quality === q ? 'bg-white shadow-sm text-primary' : ''"
                  @click="quality = q"
                >{{ q }}</button>
              </div>
            </div>
            <!-- 导出引擎 — read-only auto-detect display -->
            <div class="space-y-2">
              <label class="block text-[10px] uppercase font-bold text-outline tracking-wider">导出引擎</label>
              <div class="flex items-center gap-2 bg-surface-container-highest rounded-md py-2 px-4 text-sm text-on-surface-variant">
                <span class="material-symbols-outlined text-primary text-base">auto_awesome</span>
                <span>{{ detectedEncoder }}</span>
                <span v-if="detectedParallel > 0" class="text-[10px] text-outline ml-auto">并行 {{ detectedParallel }} 路</span>
              </div>
            </div>
            <!-- Toggle switches row -->
            <div class="col-span-2 grid grid-cols-3 gap-6 pt-2">
              <!-- 生成加速版 toggle -->
              <label class="flex items-center justify-between gap-3 cursor-pointer">
                <span class="text-sm font-medium">生成加速版 (1.25x)</span>
                <button
                  type="button"
                  class="relative w-10 h-5 rounded-full transition-colors"
                  :class="generateFast ? 'bg-primary' : 'bg-surface-container-highest'"
                  @click="generateFast = !generateFast"
                >
                  <span
                    class="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform"
                    :class="generateFast ? 'translate-x-5' : ''"
                  />
                </button>
              </label>
              <!-- Hook 文字叠加 toggle -->
              <label class="flex items-center justify-between gap-3 cursor-pointer">
                <span class="text-sm font-medium">Hook 文字叠加</span>
                <button
                  type="button"
                  class="relative w-10 h-5 rounded-full transition-colors"
                  :class="enableHook ? 'bg-primary' : 'bg-surface-container-highest'"
                  @click="enableHook = !enableHook"
                >
                  <span
                    class="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform"
                    :class="enableHook ? 'translate-x-5' : ''"
                  />
                </button>
              </label>
              <!-- 说话人识别 toggle -->
              <label class="flex items-center justify-between gap-3 cursor-pointer">
                <span class="text-sm font-medium">说话人识别</span>
                <button
                  type="button"
                  class="relative w-10 h-5 rounded-full transition-colors"
                  :class="enableDiarization ? 'bg-primary' : 'bg-surface-container-highest'"
                  @click="enableDiarization = !enableDiarization"
                >
                  <span
                    class="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform"
                    :class="enableDiarization ? 'translate-x-5' : ''"
                  />
                </button>
              </label>
            </div>
            <!-- Hook 配置 (conditionally shown when enableHook is true) -->
            <div v-if="enableHook" class="col-span-2 grid grid-cols-2 gap-x-12 gap-y-4 pt-2 pl-1 border-l-2 border-primary/20">
              <div class="space-y-4">
                <div class="flex justify-between items-center">
                  <label class="text-sm font-medium">Hook 持续时间</label>
                  <span class="text-primary font-bold">{{ hookDuration.toFixed(1) }}s</span>
                </div>
                <input
                  v-model.number="hookDuration"
                  class="w-full h-1.5 bg-surface-container-highest rounded-lg appearance-none cursor-pointer accent-primary"
                  type="range" min="1.0" max="10.0" step="0.5"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- Output -->
        <div class="bg-surface-container-low p-8 rounded-xl">
          <div class="flex items-center gap-3 mb-6">
            <span class="material-symbols-outlined text-primary">folder_open</span>
            <h3 class="font-semibold text-sm uppercase tracking-widest text-on-surface-variant">输出管理</h3>
          </div>
          <div class="space-y-4">
            <label class="block text-[10px] uppercase font-bold text-outline tracking-wider">默认目录 (Output Path)</label>
            <div class="flex gap-3">
              <input v-model="outputDir" class="flex-1 bg-surface-container-highest border-none rounded-md py-3 px-4 text-sm text-on-surface-variant" placeholder="默认: 视频所在目录/output/" type="text" />
              <button class="px-6 py-2 bg-white text-on-surface font-semibold text-sm rounded-md shadow-sm border border-outline-variant/10 hover:bg-surface-bright transition-all" @click="browseOutputDir">浏览</button>
            </div>
          </div>
        </div>

        <!-- Save -->
        <div class="flex justify-end items-center gap-4 pt-6">
          <span v-if="saveMsg" class="text-sm font-semibold transition-opacity" :class="saveMsgType === 'success' ? 'text-green-600' : 'text-error'">{{ saveMsg }}</span>
          <button class="px-8 py-3 text-sm font-bold text-on-surface-variant hover:text-on-surface transition-colors" @click="resetToDefaults">恢复默认</button>
          <button class="px-12 py-3 bg-primary text-white font-bold text-sm rounded-xl shadow-lg shadow-primary/20 hover:scale-105 active:scale-95 transition-all" :class="{ 'opacity-50': saving }" @click="saveAllSettings">{{ saving ? '保存中...' : '保存全部更改' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
