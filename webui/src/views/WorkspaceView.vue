<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import TopBar from '@/components/TopBar.vue'
import { onPipelineProgress } from '@/bridge'
import { useWorkspaceStore } from '@/stores/workspace'
import { useNotificationStore } from '@/stores/notifications'

const store = useWorkspaceStore()

const isDragging = ref(false)
const activeFilter = ref('all')
const searchQuery = ref('')

const filteredVersions = computed(() => {
  let list = store.versions
  // Search filter
  const q = searchQuery.value.toLowerCase().trim()
  if (q) {
    list = list.filter(v =>
      v.title.toLowerCase().includes(q) ||
      v.description.toLowerCase().includes(q) ||
      v.tags.some(t => t.toLowerCase().includes(q)) ||
      v.hashtags.some(h => h.toLowerCase().includes(q))
    )
  }
  // Sort filter
  if (activeFilter.value === 'top') {
    list = [...list].sort((a, b) => b.score - a.score)
  }
  return list
})

function handleDrop(e: DragEvent) {
  isDragging.value = false
  const droppedFiles = e.dataTransfer?.files
  if (droppedFiles) store.addDroppedFiles(droppedFiles)
}

// Listen for progress + import events
let removeProgressListener: (() => void) | null = null
function onImportEvent() { store.importFiles() }

onMounted(async () => {
  removeProgressListener = onPipelineProgress((e) => {
    store.progress = e.percent
    if (e.index != null && e.total != null) {
      store.progressText = `正在处理第 ${e.index + 1}/${e.total} 个视频 (${e.percent}%)`
    } else if (e.index != null) {
      store.progressText = `正在处理第 ${e.index + 1}/${store.files.length} 个视频 (${e.percent}%)`
    } else if (e.label) {
      store.progressText = `${e.label} ${e.percent}%`
    }
    if (e.index != null) store.updateFileProgress(e.index, e.label, e.percent)
  })
  window.addEventListener('import-files', onImportEvent)
  await store.detectEncoder()
})

onUnmounted(() => {
  removeProgressListener?.()
  window.removeEventListener('import-files', onImportEvent)
})

const notify = useNotificationStore()

function copyVersionText(ver: { title: string; description: string; hashtags: string[] }) {
  const text = `${ver.title}\n\n${ver.description}\n\n${ver.hashtags.join(' ')}`
  navigator.clipboard.writeText(text)
  notify.add('info', '已复制到剪贴板', ver.title)
}

const fileStatusDot: Record<string, string> = {
  processing: 'bg-blue-500',
  done: 'bg-green-500',
  pending: 'bg-slate-400',
  error: 'bg-error',
}
</script>

<template>
  <TopBar v-model="searchQuery" search-placeholder="搜索版本标题、标签...">
    <template #actions>
      <button
        class="px-4 py-2 text-on-surface-variant text-sm font-medium hover:bg-surface-variant rounded-md transition-all disabled:opacity-30"
        :disabled="store.isProcessing || !store.hasFiles"
        @click="store.clear()"
      >清空</button>
      <button
        v-if="store.hasVersions"
        class="px-4 py-2 text-on-surface-variant text-sm font-medium hover:bg-surface-variant rounded-md transition-all"
        @click="store.openOutputFolder()"
      >打开目录</button>
      <button
        class="px-4 py-2 bg-surface-container-high text-on-surface text-sm font-medium rounded-md hover:bg-surface-container-highest transition-all disabled:opacity-30"
        :disabled="store.selectedVersions.length === 0"
        @click="store.exportSelected()"
      >导出选中 {{ store.selectedVersions.length > 0 ? `(${store.selectedVersions.length})` : '' }}</button>
      <button
        class="px-6 py-2 text-white text-sm font-bold rounded-xl shadow-lg shadow-primary/20 active:scale-95 transition-all disabled:opacity-50"
        :class="store.isProcessing ? 'bg-outline animate-pulse' : 'bg-gradient-to-b from-primary to-primary-container'"
        :disabled="store.isProcessing || store.pendingFiles.length === 0"
        @click="store.generate()"
      >{{ store.isProcessing ? '处理中...' : '一键生成' }}</button>
    </template>
  </TopBar>

  <!-- Processing banner (visible even if navigating back) -->
  <div v-if="store.isProcessing || store.progress > 0" class="px-8 pt-2 pb-4">
    <div class="bg-surface-container-low rounded-full h-1 w-full overflow-hidden">
      <div
        class="bg-primary h-full shadow-[0_0_8px_rgba(53,37,205,0.4)] transition-all duration-500"
        :style="{ width: store.progress + '%' }"
      ></div>
    </div>
    <div class="flex justify-between mt-2">
      <span class="text-[10px] font-bold text-primary uppercase tracking-widest">{{ store.progressText }} {{ store.progress }}%</span>
      <span v-if="store.isProcessing" class="text-[10px] font-medium text-on-surface-variant uppercase tracking-widest">
        切换页面不影响处理
      </span>
    </div>
  </div>

  <!-- Main Content -->
  <div class="flex gap-6 px-8 pb-8 overflow-hidden" style="height: calc(100vh - 7.5rem)">
    <!-- Left: File List -->
    <section class="w-72 flex flex-col gap-4">
      <div class="flex items-center justify-between mb-2">
        <h2 class="text-sm font-bold tracking-tight text-on-surface uppercase">文件列表 ({{ store.files.length }})</h2>
        <button
          v-if="store.hasFiles"
          class="material-symbols-outlined text-sm text-primary cursor-pointer hover:bg-primary-fixed rounded-md p-1 transition-colors"
          title="添加文件"
          :disabled="store.isProcessing"
          @click="store.importFiles()"
        >add</button>
      </div>

      <!-- Empty: Drop zone -->
      <div
        v-if="!store.hasFiles"
        class="flex-1 flex flex-col items-center justify-center border-2 border-dashed border-outline-variant/40 rounded-xl cursor-pointer hover:border-primary hover:bg-primary-fixed/10 transition-all group"
        :class="{ 'border-primary bg-primary-fixed/10': isDragging }"
        @click="store.importFiles()"
        @dragover.prevent="isDragging = true"
        @dragleave="isDragging = false"
        @drop.prevent="handleDrop"
      >
        <span class="material-symbols-outlined text-4xl text-on-surface-variant/30 group-hover:text-primary transition-colors mb-3">upload_file</span>
        <p class="text-sm font-semibold text-on-surface-variant/60 group-hover:text-on-surface transition-colors">拖入视频文件</p>
        <p class="text-[10px] text-on-surface-variant/40 mt-1">或点击选择文件</p>
        <p class="text-[10px] text-outline mt-3">支持 MP4 / MOV / AVI / MKV</p>
      </div>

      <!-- File list -->
      <div v-else class="flex-1 space-y-2 overflow-y-auto custom-scrollbar pr-2">
        <div
          v-for="(file, i) in store.files"
          :key="i"
          class="p-3 rounded-xl flex items-center gap-3"
          :class="{
            'bg-surface-container-lowest border-l-4 border-primary': file.status === 'processing',
            'bg-surface-container': file.status === 'done' || file.status === 'pending',
            'bg-error-container/20 border-l-4 border-error': file.status === 'error',
          }"
        >
          <div
            class="w-10 h-10 rounded-lg flex items-center justify-center"
            :class="{
              'bg-surface-container-highest text-primary': file.status === 'processing',
              'bg-surface-container-highest text-on-surface-variant': file.status === 'done' || file.status === 'pending',
              'bg-error-container/40 text-error': file.status === 'error',
            }"
          >
            <span class="material-symbols-outlined">{{ file.icon }}</span>
          </div>
          <div class="flex-1 overflow-hidden" :class="{ 'opacity-60': file.status === 'pending' }">
            <p class="text-xs font-bold truncate">{{ file.name }}</p>
            <div class="flex items-center gap-1.5 mt-1">
              <span class="w-1.5 h-1.5 rounded-full" :class="fileStatusDot[file.status]"></span>
              <span class="text-[10px] font-medium" :class="file.status === 'error' ? 'text-error' : 'text-on-surface-variant'">{{ file.statusLabel }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Right: Version Cards -->
    <section class="flex-1 flex flex-col gap-4 overflow-hidden">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-bold tracking-tight text-on-surface uppercase">生成版本</h2>
        <div class="flex gap-2">
          <button
            v-for="f in [{ id: 'all', label: '全部' }, { id: 'top', label: '高分优先' }, { id: 'new', label: '最新' }]"
            :key="f.id"
            class="px-3 py-1 text-[10px] font-bold rounded-full uppercase"
            :class="activeFilter === f.id ? 'bg-surface-container text-on-surface' : 'text-on-surface-variant'"
            @click="activeFilter = f.id"
          >{{ f.label }}</button>
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="!store.hasVersions && !store.isProcessing" class="flex-1 flex flex-col items-center justify-center text-center">
        <span class="material-symbols-outlined text-6xl text-on-surface-variant/20 mb-4">auto_awesome</span>
        <p class="text-sm font-semibold text-on-surface-variant/50">还没有生成版本</p>
        <p class="text-xs text-on-surface-variant/30 mt-1">导入视频后点击「一键生成」开始</p>
      </div>

      <!-- Processing state -->
      <div v-else-if="!store.hasVersions && store.isProcessing" class="flex-1 flex flex-col items-center justify-center text-center">
        <span class="material-symbols-outlined text-6xl text-primary/40 mb-4 animate-spin" style="animation-duration: 3s;">progress_activity</span>
        <p class="text-sm font-semibold text-on-surface-variant/60">AI 正在处理中...</p>
        <p class="text-xs text-on-surface-variant/30 mt-1">可以切换到其他页面，处理不会中断</p>
      </div>

      <div v-else class="grid grid-cols-2 gap-4 overflow-y-auto custom-scrollbar pr-2 pb-4">
        <div
          v-for="(ver, i) in filteredVersions"
          :key="i"
          class="group relative bg-surface-container-lowest rounded-xl overflow-hidden hover:shadow-2xl hover:shadow-on-surface/5 transition-all duration-300"
        >
          <div class="absolute top-3 left-3 z-10">
            <input v-model="ver.selected" class="w-4 h-4 rounded-md border-outline-variant text-primary focus:ring-primary cursor-pointer" type="checkbox" />
          </div>
          <div class="absolute top-3 right-3 z-10">
            <span class="px-2 py-0.5 bg-black/60 backdrop-blur-md text-white text-[10px] font-bold rounded-full border border-white/20">时长 {{ ver.duration }}</span>
          </div>

          <div class="aspect-video relative bg-surface-container-high flex items-center justify-center">
            <span class="material-symbols-outlined text-4xl text-on-surface-variant/30">movie</span>
            <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
              <button class="p-3 bg-white/20 backdrop-blur-xl rounded-full text-white hover:bg-white/40 transition-colors" @click.stop="store.preview(ver)">
                <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1;">play_arrow</span>
              </button>
            </div>
          </div>

          <div class="p-4">
            <div class="flex items-center justify-between mb-3">
              <div class="flex gap-2">
                <span v-for="tag in ver.tags" :key="tag" class="px-2 py-0.5 bg-primary/10 text-primary text-[10px] font-bold rounded uppercase">{{ tag }}</span>
              </div>
              <div class="flex items-center gap-1">
                <span class="material-symbols-outlined text-amber-500 text-xs" style="font-variation-settings: 'FILL' 1;">star</span>
                <span class="text-xs font-bold">{{ ver.score }}</span>
              </div>
            </div>
            <h3 class="text-sm font-bold mb-2 truncate">{{ ver.title }}</h3>
            <p class="text-xs text-on-surface-variant line-clamp-2 mb-3 leading-relaxed">{{ ver.description }}</p>
            <div class="flex flex-wrap gap-1.5 mb-4">
              <span v-for="h in ver.hashtags" :key="h" class="text-[10px] text-on-surface-variant">{{ h }}</span>
            </div>
            <div class="pt-4 border-t border-surface-container flex items-center justify-between">
              <label class="relative inline-flex items-center cursor-pointer">
                <input v-model="ver.autoExport" class="sr-only peer" type="checkbox" />
                <div class="w-8 h-4 bg-surface-container-high peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-primary"></div>
                <span class="ms-2 text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">自动导出</span>
              </label>
              <button class="text-primary hover:underline text-[10px] font-bold uppercase tracking-wider" @click="copyVersionText(ver)">复制文案</button>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>

  <!-- Footer -->
  <footer class="h-12 bg-surface-container-low border-t border-outline-variant/10 px-8 flex items-center justify-between">
    <div class="flex gap-6">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_4px_#22c55e]"></span>
        <span class="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest">编码器: {{ store.encoderName }}</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="material-symbols-outlined text-[12px] text-on-surface-variant">speed</span>
        <span class="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest">并行: 最多 {{ store.maxParallel }} 路</span>
      </div>
    </div>
    <p class="text-[10px] font-medium text-on-surface-variant/60 uppercase tracking-[0.2em]">CutPilot v4.0.1</p>
  </footer>
</template>
