<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import TopBar from '@/components/TopBar.vue'
import { onPipelineProgress, onBatchSummary } from '@/bridge'
import { useWorkspaceStore } from '@/stores/workspace'
import { useNotificationStore } from '@/stores/notifications'

const store = useWorkspaceStore()

const activeFilter = ref('all')
const searchQuery = ref('')
const isDragging = ref(false)
const showMoreMenu = ref(false)

// Close dropdown on outside click
function onDocClick(e: MouseEvent) {
  if (showMoreMenu.value && !(e.target as HTMLElement)?.closest?.('.relative')) {
    showMoreMenu.value = false
  }
}

function onDrop(e: DragEvent) {
  isDragging.value = false
  if (e.dataTransfer?.files?.length) {
    store.addDroppedFiles(e.dataTransfer.files)
  }
}

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

// Listen for progress + import events
let removeProgressListener: (() => void) | null = null
let removeSummaryListener: (() => void) | null = null
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
  removeSummaryListener = onBatchSummary((summary) => {
    const n = useNotificationStore()
    if (summary.fail_count === 0) {
      n.add('success', '全部完成', `${summary.success_count} 个视频处理成功`)
    } else {
      const errorDetails = summary.errors.map(e => `${e.video}: ${e.error}`).join('\n')
      n.add('error', `${summary.success_count} 成功, ${summary.fail_count} 失败`, errorDetails)
    }
  })
  window.addEventListener('import-files', onImportEvent)
  document.addEventListener('click', onDocClick)
  await store.detectEncoder()
})

onUnmounted(() => {
  removeProgressListener?.()
  removeSummaryListener?.()
  window.removeEventListener('import-files', onImportEvent)
  document.removeEventListener('click', onDocClick)
})

const notify = useNotificationStore()

function copyAllVersionText() {
  const blocks = store.versions.map((v, i) => {
    return `=== V${i + 1} [${v.tags.join(', ')}] ===\n发布文案: ${v.description}\n封面主标题: ${v.title}\n标签: ${v.hashtags.join(' ')}`
  })
  navigator.clipboard.writeText(blocks.join('\n\n'))
  notify.add('info', '已复制全部文案', `${store.versions.length} 个版本`)
}

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
      <!-- More menu (清空/打开目录/复制文案) -->
      <div class="relative" v-if="store.hasFiles">
        <button
          class="px-3 py-2 text-on-surface-variant text-sm font-medium hover:bg-surface-variant rounded-md transition-all flex items-center gap-1"
          @click="showMoreMenu = !showMoreMenu"
        >
          <span class="material-symbols-outlined text-base">more_horiz</span>
          <span>更多</span>
        </button>
        <div
          v-if="showMoreMenu"
          class="absolute right-0 top-full mt-1 w-40 bg-surface-container-lowest rounded-xl shadow-xl border border-outline-variant/20 py-1 z-50"
        >
          <button
            class="w-full px-4 py-2.5 text-left text-sm text-on-surface-variant hover:bg-surface-variant/50 transition-colors disabled:opacity-30"
            :disabled="store.isProcessing"
            @click="store.clear(); showMoreMenu = false"
          >清空文件</button>
          <button
            v-if="store.hasVersions"
            class="w-full px-4 py-2.5 text-left text-sm text-on-surface-variant hover:bg-surface-variant/50 transition-colors"
            @click="store.openOutputFolder(); showMoreMenu = false"
          >打开输出目录</button>
          <button
            v-if="store.hasVersions"
            class="w-full px-4 py-2.5 text-left text-sm text-on-surface-variant hover:bg-surface-variant/50 transition-colors"
            @click="copyAllVersionText(); showMoreMenu = false"
          >复制全部文案</button>
        </div>
      </div>
      <!-- Export -->
      <button
        class="px-4 py-2 bg-surface-container-high text-on-surface text-sm font-medium rounded-md hover:bg-surface-container-highest transition-all disabled:opacity-30"
        :disabled="store.selectedVersions.length === 0 || store.isExporting"
        @click="store.exportSelected()"
      >{{ store.isExporting ? '导出中...' : `导出选中${store.selectedVersions.length > 0 ? ` (${store.selectedVersions.length})` : ''}` }}</button>
      <!-- Cancel / Generate -->
      <button
        v-if="store.isProcessing"
        class="px-6 py-2 text-white text-sm font-bold rounded-xl shadow-lg shadow-error/20 active:scale-95 transition-all bg-error hover:bg-error/80 flex items-center gap-1.5"
        @click="store.cancelGenerate()"
      ><span class="material-symbols-outlined text-base">stop_circle</span>取消处理</button>
      <button
        v-else
        class="px-6 py-2 text-white text-sm font-bold rounded-xl shadow-lg shadow-primary/20 active:scale-95 transition-all disabled:opacity-50 bg-gradient-to-b from-primary to-primary-container"
        :disabled="store.pendingFiles.length === 0"
        @click="store.generate()"
      >一键生成</button>
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
        class="flex-1 flex flex-col items-center justify-center border-2 border-dashed rounded-xl cursor-pointer transition-all group"
        :class="isDragging ? 'border-primary bg-primary-fixed/20 scale-[1.01]' : 'border-outline-variant/40 hover:border-primary hover:bg-primary-fixed/10'"
        @click="store.importFiles()"
        @dragover.prevent="isDragging = true"
        @dragenter.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="onDrop"
      >
        <span class="material-symbols-outlined text-4xl transition-colors mb-3" :class="isDragging ? 'text-primary' : 'text-on-surface-variant/30 group-hover:text-primary'">upload_file</span>
        <p class="text-sm font-semibold transition-colors" :class="isDragging ? 'text-primary' : 'text-on-surface-variant/60 group-hover:text-on-surface'">{{ isDragging ? '松开即可导入' : '拖入或点击选择视频' }}</p>
        <p class="text-[10px] text-on-surface-variant/40 mt-1">支持批量拖入多个文件</p>
        <p class="text-[10px] text-outline mt-3">MP4 / MOV / AVI / MKV</p>
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
              <span class="text-[10px] font-medium truncate" :class="file.status === 'error' ? 'text-error' : 'text-on-surface-variant'" :title="file.statusLabel">{{ file.statusLabel }}</span>
            </div>
          </div>
        </div>
        <!-- Retry failed button -->
        <button
          v-if="store.failedFiles.length > 0 && !store.isProcessing"
          class="mt-2 w-full py-2 text-xs font-bold text-error bg-error-container/30 rounded-lg hover:bg-error-container/50 transition-colors flex items-center justify-center gap-1.5 shrink-0"
          @click="store.retryFailed()"
        >
          <span class="material-symbols-outlined text-sm">refresh</span>
          重试失败 ({{ store.failedFiles.length }})
        </button>
      </div>
    </section>

    <!-- Right: Version Cards -->
    <section class="flex-1 flex flex-col gap-4 overflow-hidden">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-bold tracking-tight text-on-surface uppercase">生成版本</h2>
        <div class="flex gap-2">
          <button
            v-for="f in [{ id: 'all', label: '全部' }, { id: 'top', label: '高分优先' }]"
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

      <!-- Processing state: skeleton cards -->
      <div v-else-if="!store.hasVersions && store.isProcessing" class="grid grid-cols-2 gap-4 overflow-y-auto custom-scrollbar pr-2 pb-4">
        <div v-for="n in 3" :key="n" class="bg-surface-container-lowest rounded-xl overflow-hidden animate-pulse">
          <!-- Thumbnail skeleton -->
          <div class="aspect-video bg-surface-container-high flex items-center justify-center">
            <span class="material-symbols-outlined text-3xl text-on-surface-variant/15">movie</span>
          </div>
          <!-- Content skeleton -->
          <div class="p-4 space-y-3">
            <div class="h-4 bg-surface-container-high rounded w-3/4"></div>
            <div class="space-y-2">
              <div class="h-3 bg-surface-container rounded w-full"></div>
              <div class="h-3 bg-surface-container rounded w-5/6"></div>
              <div class="h-3 bg-surface-container rounded w-2/3"></div>
            </div>
            <div class="flex gap-2 pt-1">
              <div class="h-5 bg-surface-container rounded-full w-16"></div>
              <div class="h-5 bg-surface-container rounded-full w-12"></div>
              <div class="h-5 bg-surface-container rounded-full w-14"></div>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="grid grid-cols-2 gap-4 overflow-y-auto custom-scrollbar pr-2 pb-4">
        <div
          v-for="(ver, i) in filteredVersions"
          :key="i"
          class="group relative bg-surface-container-lowest rounded-xl overflow-hidden hover:shadow-2xl hover:shadow-on-surface/5 transition-all duration-300"
        >
          <div class="absolute top-3 left-3 z-10">
            <input v-model="ver.selected" class="w-4 h-4 rounded-md border-outline-variant text-primary focus:ring-primary cursor-pointer" type="checkbox" title="选中导出" />
          </div>
          <div class="absolute top-3 right-3 z-10">
            <span class="px-2 py-0.5 bg-black/60 backdrop-blur-md text-white text-[10px] font-bold rounded-full border border-white/20">时长 {{ ver.duration }}</span>
          </div>

          <div class="aspect-video relative bg-surface-container-high flex items-center justify-center overflow-hidden">
            <img v-if="ver.thumbnail" :src="ver.thumbnail" class="w-full h-full object-cover" alt="" />
            <span v-else class="material-symbols-outlined text-4xl text-on-surface-variant/30">movie</span>
            <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
              <button class="p-3 bg-white/20 backdrop-blur-xl rounded-full text-white hover:bg-white/40 transition-colors" title="预览视频" @click.stop="store.preview(ver)">
                <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1;">play_arrow</span>
              </button>
            </div>
          </div>

          <div class="p-4 space-y-3">
            <!-- Source video + score -->
            <div class="flex items-center justify-between">
              <p class="text-[10px] text-on-surface-variant truncate flex-1 mr-2" :title="ver.videoPath">
                <span class="material-symbols-outlined text-[10px] align-middle mr-0.5">video_file</span>
                {{ ver.videoPath.split(/[/\\]/).pop() }}
              </p>
              <div class="flex items-center gap-2 flex-shrink-0">
                <span v-for="tag in ver.tags" :key="tag" class="px-2 py-0.5 bg-primary/10 text-primary text-[10px] font-bold rounded">{{ tag }}</span>
                <span class="material-symbols-outlined text-amber-500 text-xs" style="font-variation-settings: 'FILL' 1;">star</span>
                <span class="text-xs font-bold">{{ ver.score }}</span>
              </div>
            </div>

            <!-- Cover title (封面主标题) -->
            <h3 class="text-sm font-bold leading-snug">{{ ver.title }}</h3>

            <!-- Publish text (发布文案) -->
            <div class="bg-surface-container-low rounded-lg p-3">
              <p class="text-[10px] font-bold text-outline uppercase tracking-wider mb-1">发布文案</p>
              <p class="text-xs text-on-surface leading-relaxed">{{ ver.description }}</p>
            </div>

            <!-- Tags (标签) -->
            <div class="flex flex-wrap gap-1.5">
              <span v-for="h in ver.hashtags" :key="h" class="px-2 py-0.5 bg-surface-container-high text-on-surface-variant text-[10px] font-medium rounded-full">{{ h }}</span>
            </div>

            <!-- Actions -->
            <div class="pt-3 border-t border-surface-container flex items-center justify-end">
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
    <p class="text-[10px] font-medium text-on-surface-variant/60 uppercase tracking-[0.2em]">CutPilot v4.2.1</p>
  </footer>
</template>
