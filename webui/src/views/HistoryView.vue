<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import TopBar from '@/components/TopBar.vue'
import { getHistory, clearHistory as bridgeClear, openFolder, deleteHistoryEntry, type HistoryEntry } from '@/bridge'
import { useNotificationStore } from '@/stores/notifications'

interface HistoryRecord {
  time: string
  timeDisplay: string
  name: string
  videoPath: string
  status: 'done' | 'error'
  statusLabel: string
  version: string
  versionsCount: number
  durationSec: number
  success: boolean
  tags: string[]
}

const router = useRouter()
const records = ref<HistoryRecord[]>([])
const notify = useNotificationStore()

// Error message translation — turn technical English into user-friendly Chinese
const ERROR_MAP: [RegExp, string][] = [
  [/视频文件不存在/i, '文件已移动或删除'],
  [/AI response is not valid JSON/i, 'AI 返回格式异常，请重试'],
  [/Expecting value/i, 'AI 返回格式异常，请重试'],
  [/素材太短/i, '素材太短，无法生成'],
  [/No valid versions/i, 'AI 未生成有效版本'],
  [/connection/i, '网络连接失败'],
  [/timeout/i, '请求超时'],
  [/rate.?limit/i, 'API 调用频率过高'],
  [/auth/i, 'API 密钥无效'],
]

function friendlyError(raw: string): string {
  if (!raw) return '处理失败'
  for (const [re, msg] of ERROR_MAP) {
    if (re.test(raw)) return msg
  }
  // Fallback: if it's mostly ASCII/technical, show generic message
  const asciiRatio = (raw.match(/[a-zA-Z{}\[\]:]/g)?.length ?? 0) / raw.length
  if (asciiRatio > 0.5) return '处理异常，请重试'
  return raw.length > 20 ? raw.slice(0, 20) + '...' : raw
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return iso
  }
}

onMounted(async () => {
  await refreshHistory()
})

async function refreshHistory() {
  const entries = await getHistory()
  records.value = entries.map((e: HistoryEntry) => ({
    time: e.timestamp,
    timeDisplay: formatTime(e.timestamp),
    name: e.video_name,
    videoPath: e.video_path,
    status: e.success ? 'done' as const : 'error' as const,
    statusLabel: e.success ? '已完成' : friendlyError(e.error),
    version: e.versions_count > 0 ? `${e.versions_count} 个` : '-',
    versionsCount: e.versions_count,
    durationSec: e.duration_sec,
    success: e.success,
    tags: e.approach_tags,
  }))
}

async function handleClearHistory() {
  if (records.value.length === 0) return
  if (!globalThis.confirm('确定要清空所有历史记录吗？此操作不可撤销。')) return
  try {
    const res = await bridgeClear()
    if (res && res.error) {
      notify.add('error', '清空失败', res.error)
      return
    }
    records.value = []
    notify.add('info', '历史记录已清空')
  } catch (e: any) {
    notify.add('error', '清空失败', e.message || '未知错误')
  }
}

function handleOpen(row: HistoryRecord) {
  if (row.videoPath) openFolder(row.videoPath)
}

async function handleDelete(row: HistoryRecord) {
  if (!globalThis.confirm(`确定要删除「${row.name}」的记录吗？`)) return
  try {
    const res = await deleteHistoryEntry(row.time)
    if (res && res.error) {
      notify.add('error', '删除失败', res.error)
      return
    }
    records.value = records.value.filter(r => r !== row)
    notify.add('info', '已删除', row.name)
  } catch (e: any) {
    notify.add('error', '删除失败', e.message || '未知错误')
  }
}

const statusClass: Record<string, string> = {
  done: 'bg-green-100 text-green-700',
  error: 'bg-error-container text-on-error-container',
}
const statusDotClass: Record<string, string> = {
  done: 'bg-green-500',
  error: 'bg-error',
}

const totalCount = computed(() => records.value.length)
const totalHours = computed(() => {
  const totalSec = records.value.reduce((sum, r) => sum + r.durationSec, 0)
  return (totalSec / 3600).toFixed(1)
})
const avgVersion = computed(() => {
  if (records.value.length === 0) return '0'
  const avg = records.value.reduce((sum, r) => sum + r.versionsCount, 0) / records.value.length
  return avg.toFixed(1)
})
const successRate = computed(() => {
  if (records.value.length === 0) return '0'
  const rate = (records.value.filter(r => r.success).length / records.value.length) * 100
  return rate.toFixed(1)
})

const searchQuery = ref('')
const sortBy = ref<'time' | 'name' | 'status'>('time')
const sortDesc = ref(true)
const filterStatus = ref<'all' | 'done' | 'error'>('all')

const filteredRecords = computed(() => {
  let list = records.value

  // Status filter
  if (filterStatus.value !== 'all') {
    list = list.filter(r => r.status === filterStatus.value)
  }

  // Search
  const q = searchQuery.value.toLowerCase().trim()
  if (q) {
    list = list.filter(r =>
      r.name.toLowerCase().includes(q) ||
      r.tags.some(t => t.toLowerCase().includes(q))
    )
  }

  // Sort
  const sorted = [...list]
  sorted.sort((a, b) => {
    let cmp = 0
    if (sortBy.value === 'time') cmp = a.time.localeCompare(b.time)
    else if (sortBy.value === 'name') cmp = a.name.localeCompare(b.name)
    else if (sortBy.value === 'status') cmp = Number(a.success) - Number(b.success)
    return sortDesc.value ? -cmp : cmp
  })

  return sorted
})

function toggleSort(field: 'time' | 'name' | 'status') {
  if (sortBy.value === field) {
    sortDesc.value = !sortDesc.value
  } else {
    sortBy.value = field
    sortDesc.value = true
  }
}

function cycleFilter() {
  const order: Array<'all' | 'done' | 'error'> = ['all', 'done', 'error']
  const idx = order.indexOf(filterStatus.value)
  filterStatus.value = order[(idx + 1) % order.length]!
}

const filterLabel = computed(() => {
  if (filterStatus.value === 'done') return '仅成功'
  if (filterStatus.value === 'error') return '仅失败'
  return ''
})

</script>

<template>
  <TopBar v-model="searchQuery" search-placeholder="搜索视频名称、标签...">
    <template #actions>
      <router-link to="/" class="px-4 py-2 bg-primary text-white text-sm font-medium rounded-xl hover:bg-primary-container transition-all">
        去工作台
      </router-link>
    </template>
  </TopBar>

  <div class="max-w-[1280px] mx-auto p-8 space-y-8">
    <!-- Stats -->
    <section class="grid grid-cols-4 gap-6">
      <div class="bg-surface-container-lowest p-6 rounded-xl shadow-sm border-l-4 border-primary">
        <p class="text-[11px] font-bold text-on-surface-variant uppercase tracking-widest mb-2">总生成次数</p>
        <span class="text-3xl font-bold text-on-surface">{{ totalCount }}</span>
      </div>
      <div class="bg-surface-container-lowest p-6 rounded-xl shadow-sm">
        <p class="text-[11px] font-bold text-on-surface-variant uppercase tracking-widest mb-2">计算时长 (Hrs)</p>
        <span class="text-3xl font-bold text-on-surface">{{ totalHours }}</span>
      </div>
      <div class="bg-surface-container-lowest p-6 rounded-xl shadow-sm">
        <p class="text-[11px] font-bold text-on-surface-variant uppercase tracking-widest mb-2">平均版本数</p>
        <span class="text-3xl font-bold text-on-surface">{{ avgVersion }}</span>
      </div>
      <div class="bg-surface-container-lowest p-6 rounded-xl shadow-sm">
        <p class="text-[11px] font-bold text-on-surface-variant uppercase tracking-widest mb-2">成功率</p>
        <div class="flex items-end gap-2">
          <span class="text-3xl font-bold text-on-surface">{{ successRate }}%</span>
          <div class="w-16 h-1 bg-surface-container-high rounded-full mb-2 overflow-hidden">
            <div class="bg-primary h-full" :style="{ width: successRate + '%' }"></div>
          </div>
        </div>
      </div>
    </section>

    <!-- Table -->
    <section class="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
      <div class="px-6 py-4 border-b border-surface-container flex justify-between items-center">
        <h2 class="text-lg font-semibold text-on-surface">所有历史记录</h2>
        <div class="flex gap-2 items-center">
          <span v-if="filterLabel" class="text-[10px] font-bold text-primary bg-primary-fixed px-2 py-0.5 rounded-full">{{ filterLabel }}</span>
          <button
            class="px-3 py-1.5 text-xs font-medium text-error hover:bg-error-container rounded-md transition-colors"
            @click="handleClearHistory"
          >清空历史</button>
          <button
            class="p-2 text-on-surface-variant hover:bg-surface-container-low rounded-md transition-colors"
            title="筛选状态"
            @click="cycleFilter"
          >
            <span class="material-symbols-outlined text-[20px]">filter_list</span>
          </button>
          <button
            class="p-2 text-on-surface-variant hover:bg-surface-container-low rounded-md transition-colors"
            title="切换排序"
            @click="sortDesc = !sortDesc"
          >
            <span class="material-symbols-outlined text-[20px]">{{ sortDesc ? 'arrow_downward' : 'arrow_upward' }}</span>
          </button>
        </div>
      </div>
      <table class="w-full text-left border-collapse">
        <thead>
          <tr class="bg-surface-container-low">
            <th class="px-6 py-4 text-[11px] font-bold text-on-surface-variant uppercase tracking-widest cursor-pointer hover:text-primary" @click="toggleSort('time')">
              时间 {{ sortBy === 'time' ? (sortDesc ? '↓' : '↑') : '' }}
            </th>
            <th class="px-6 py-4 text-[11px] font-bold text-on-surface-variant uppercase tracking-widest cursor-pointer hover:text-primary" @click="toggleSort('name')">
              视频名称 {{ sortBy === 'name' ? (sortDesc ? '↓' : '↑') : '' }}
            </th>
            <th class="px-6 py-4 text-[11px] font-bold text-on-surface-variant uppercase tracking-widest cursor-pointer hover:text-primary" @click="toggleSort('status')">
              状态 {{ sortBy === 'status' ? (sortDesc ? '↓' : '↑') : '' }}
            </th>
            <th class="px-6 py-4 text-[11px] font-bold text-on-surface-variant uppercase tracking-widest text-center">版本</th>
            <th class="px-6 py-4 text-[11px] font-bold text-on-surface-variant uppercase tracking-widest">切入角度</th>
            <th class="px-6 py-4 text-[11px] font-bold text-on-surface-variant uppercase tracking-widest text-right">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-surface-container">
          <tr v-if="filteredRecords.length === 0">
            <td colspan="6" class="px-6 py-16 text-center">
              <div v-if="records.length === 0" class="flex flex-col items-center gap-3">
                <span class="material-symbols-outlined text-4xl text-on-surface-variant/30">movie_edit</span>
                <p class="text-sm text-on-surface-variant/60">还没有处理记录</p>
                <button
                  class="mt-1 px-4 py-2 text-xs font-bold text-primary bg-primary-fixed/20 rounded-lg hover:bg-primary-fixed/30 transition-colors"
                  @click="router.push('/')"
                >去工作台导入视频</button>
              </div>
              <p v-else class="text-sm text-on-surface-variant">无匹配结果</p>
            </td>
          </tr>
          <tr
            v-for="(row, idx) in filteredRecords"
            :key="idx"
            class="hover:bg-surface-container-low transition-colors group"
          >
            <td class="px-6 py-5 text-sm text-on-surface-variant whitespace-nowrap">{{ row.timeDisplay }}</td>
            <td class="px-6 py-5">
              <div class="flex items-center gap-3">
                <div class="w-12 h-8 bg-surface-container rounded overflow-hidden flex-shrink-0 flex items-center justify-center">
                  <span class="material-symbols-outlined text-on-surface-variant text-sm">movie</span>
                </div>
                <span class="text-sm font-semibold text-on-surface truncate max-w-[200px]" :title="row.name">{{ row.name }}</span>
              </div>
            </td>
            <td class="px-6 py-5">
              <span
                class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold"
                :class="statusClass[row.status]"
                :title="row.status === 'error' ? row.statusLabel : ''"
              >
                <span class="w-1.5 h-1.5 rounded-full mr-1.5" :class="statusDotClass[row.status]"></span>
                {{ row.statusLabel }}
              </span>
            </td>
            <td class="px-6 py-5 text-sm text-center">{{ row.version }}</td>
            <td class="px-6 py-5">
              <div class="flex gap-1.5 flex-wrap">
                <span
                  v-for="tag in row.tags"
                  :key="tag"
                  class="px-2 py-0.5 bg-primary-fixed text-on-primary-fixed text-[10px] font-semibold rounded-md"
                >{{ tag }}</span>
                <span v-if="row.tags.length === 0" class="text-[10px] text-on-surface-variant">-</span>
              </div>
            </td>
            <td class="px-6 py-5 text-right">
              <div class="flex justify-end gap-1">
                <button
                  v-if="row.status === 'done'"
                  class="p-2 text-primary hover:bg-primary-fixed rounded-md transition-colors"
                  title="打开文件夹"
                  @click="handleOpen(row)"
                >
                  <span class="material-symbols-outlined text-[20px]">folder_open</span>
                </button>
                <button
                  class="p-2 text-on-surface-variant hover:bg-error-container/30 hover:text-error rounded-md transition-colors"
                  title="删除记录"
                  @click="handleDelete(row)"
                >
                  <span class="material-symbols-outlined text-[20px]">delete</span>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="px-6 py-4 flex items-center justify-between bg-surface-container-low border-t border-surface-container">
        <span class="text-xs text-on-surface-variant font-medium">
          显示 {{ filteredRecords.length }} / {{ records.length }} 条
        </span>
      </div>
    </section>
  </div>
</template>
