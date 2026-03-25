<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  UploadOutlined,
  PlayCircleOutlined,
  ExportOutlined,
  DeleteOutlined,
  CopyOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  LoadingOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

// State
const videoFiles = ref<{ name: string; path: string; status: 'pending' | 'processing' | 'done' | 'error' }[]>([])
const versions = ref<any[]>([])
const processing = ref(false)
const progress = ref(0)
const progressText = ref('就绪')
const selectAll = ref(true)

// Drag and drop
const dragOver = ref(false)

function onDrop(e: DragEvent) {
  dragOver.value = false
  // In production, pywebview bridge will handle file paths
  message.info('拖入功能将通过 pywebview bridge 连接 Python 后端')
}

function addDemoData() {
  // Demo data for skeleton preview
  videoFiles.value = [
    { name: '产品介绍_01.mp4', path: '/demo/01.mp4', status: 'done' },
    { name: '直播切片_02.mp4', path: '/demo/02.mp4', status: 'done' },
    { name: '新品上架_03.mp4', path: '/demo/03.mp4', status: 'pending' },
  ]
  versions.value = [
    {
      videoName: '产品介绍_01',
      versionId: 1,
      approachTag: '痛点解决',
      coverTitle: '卡粉救星',
      publishText: '又干又油还卡粉？妆前用它敷一下，底妆直接焊在脸上！',
      tags: ['#护肤', '#底妆', '#卡粉', '#妆前乳', '#油皮'],
      duration: 35,
      score: 81,
      selected: true,
      exportNormal: true,
      exportFast: false,
      enableHook: false,
    },
    {
      videoName: '产品介绍_01',
      versionId: 2,
      approachTag: '价格冲击',
      coverTitle: '49.9抢100克',
      publishText: '49.9到手100克！这个贴贴霜性价比高到离谱…',
      tags: ['#平价', '#贴贴霜', '#性价比', '#护肤好物', '#学生党'],
      duration: 31,
      score: 73,
      selected: true,
      exportNormal: true,
      exportFast: true,
      enableHook: false,
    },
    {
      videoName: '直播切片_02',
      versionId: 1,
      approachTag: '外观颜值',
      coverTitle: '百搭神瞳',
      publishText: '这副美瞳我戴了快一年没换过，前置后置都绝美！',
      tags: ['#美瞳', '#自然款', '#素颜美瞳', '#日抛', '#混血感'],
      duration: 28,
      score: 88,
      selected: true,
      exportNormal: true,
      exportFast: false,
      enableHook: true,
    },
  ]
  progress.value = 100
  progressText.value = '处理完成: 2/3 个视频成功'
}

const selectedCount = computed(() => versions.value.filter(v => v.selected).length)
const totalCount = computed(() => versions.value.length)

function toggleAll() {
  versions.value.forEach(v => (v.selected = selectAll.value))
}

function copyText(v: any) {
  const text = `发布文案: ${v.publishText}\n封面主标题: ${v.coverTitle}\n标签: ${v.tags.join(' ')}`
  navigator.clipboard.writeText(text)
  message.success('文案已复制')
}

// Load demo on mount
addDemoData()
</script>

<template>
  <div class="workspace">
    <!-- Top bar -->
    <div class="top-bar">
      <div class="top-left">
        <h2>工作台</h2>
        <span class="subtitle">拖入视频素材，AI 自动生成多版本短视频</span>
      </div>
      <div class="top-right">
        <a-button type="primary" :loading="processing" @click="message.info('连接 Python 后端后可用')">
          <template #icon><PlayCircleOutlined /></template>
          一键生成
        </a-button>
        <a-button @click="message.info('导出功能待连接')">
          <template #icon><ExportOutlined /></template>
          导出选中 ({{ selectedCount }})
        </a-button>
        <a-button danger @click="videoFiles = []; versions = []">
          <template #icon><DeleteOutlined /></template>
          清空
        </a-button>
      </div>
    </div>

    <!-- Progress -->
    <div v-if="progress > 0" class="progress-bar">
      <span class="progress-text">{{ progressText }}</span>
      <a-progress :percent="progress" :stroke-color="{ '0%': '#6c5ce7', '100%': '#a29bfe' }" :show-info="false" size="small" />
    </div>

    <!-- Main area -->
    <div class="main-area">
      <!-- Left: file list + drop zone -->
      <div class="file-panel">
        <!-- Drop zone -->
        <div
          class="drop-zone"
          :class="{ 'drag-over': dragOver }"
          @dragover.prevent="dragOver = true"
          @dragleave="dragOver = false"
          @drop.prevent="onDrop"
        >
          <UploadOutlined class="drop-icon" />
          <p class="drop-title">拖入视频或文件夹</p>
          <p class="drop-hint">支持 MP4 / MOV / AVI / MKV</p>
          <div class="drop-actions">
            <a-button size="small"><FolderOpenOutlined /> 选择文件夹</a-button>
          </div>
        </div>

        <!-- File list -->
        <div class="file-list">
          <div class="file-list-header">已导入素材 ({{ videoFiles.length }})</div>
          <div v-for="file in videoFiles" :key="file.path" class="file-item">
            <CheckCircleFilled v-if="file.status === 'done'" style="color: var(--success)" />
            <CloseCircleFilled v-else-if="file.status === 'error'" style="color: var(--danger)" />
            <LoadingOutlined v-else-if="file.status === 'processing'" style="color: var(--accent)" spin />
            <span v-else class="dot">○</span>
            <span class="file-name">{{ file.name }}</span>
          </div>
          <div v-if="!videoFiles.length" class="empty-hint">暂无素材</div>
        </div>
      </div>

      <!-- Right: version cards -->
      <div class="version-panel">
        <div class="version-header">
          <span>成品预览</span>
          <a-checkbox v-model:checked="selectAll" @change="toggleAll">
            全选
          </a-checkbox>
          <span class="count">{{ selectedCount }}/{{ totalCount }}</span>
        </div>

        <div class="version-list">
          <template v-for="(v, idx) in versions" :key="`${v.videoName}-${v.versionId}`">
            <!-- Product header (show when videoName changes) -->
            <div v-if="idx === 0 || versions[idx - 1].videoName !== v.videoName" class="product-header">
              {{ v.videoName }}
            </div>

            <!-- Version card -->
            <div class="version-card" :class="{ selected: v.selected }">
              <div class="card-header">
                <a-checkbox v-model:checked="v.selected" />
                <span class="card-title">版本 {{ v.versionId }}</span>
                <a-tag :color="v.score >= 80 ? 'green' : v.score >= 60 ? 'orange' : 'red'">
                  {{ v.score }}分
                </a-tag>
                <a-tag color="purple">{{ v.approachTag }}</a-tag>
                <span class="card-duration">{{ v.duration }}s</span>
                <a-button size="small" type="text" @click="copyText(v)">
                  <CopyOutlined /> 复制文案
                </a-button>
              </div>

              <div class="card-body">
                <div class="cover-title">{{ v.coverTitle }}</div>
                <div class="publish-text">{{ v.publishText }}</div>
                <div class="tags">
                  <a-tag v-for="tag in v.tags" :key="tag" size="small">{{ tag }}</a-tag>
                </div>
              </div>

              <div class="card-options">
                <a-checkbox v-model:checked="v.exportNormal" size="small">原速</a-checkbox>
                <a-checkbox v-model:checked="v.exportFast" size="small">加速</a-checkbox>
                <a-checkbox v-model:checked="v.enableHook" size="small">Hook</a-checkbox>
              </div>
            </div>
          </template>

          <div v-if="!versions.length" class="empty-versions">
            <ScissorOutlined style="font-size: 48px; color: #ccc" />
            <p>处理完成后在此展示成品</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Layout — structural only, no color hardcoding */
.workspace { display: flex; flex-direction: column; gap: 16px; height: 100%; }

.top-bar { display: flex; justify-content: space-between; align-items: center; }
.top-left h2 { margin: 0; font-size: 20px; }
.subtitle { font-size: 12px; color: #999; margin-left: 12px; }
.top-right { display: flex; gap: 8px; }

.progress-bar { background: #fafafa; padding: 12px 16px; border-radius: 8px; display: flex; align-items: center; gap: 12px; }
.progress-text { font-size: 12px; color: #666; white-space: nowrap; }

.main-area { display: flex; gap: 16px; flex: 1; min-height: 0; }

.file-panel { width: 280px; flex-shrink: 0; display: flex; flex-direction: column; gap: 12px; }

.drop-zone {
  background: #fafafa;
  border: 2px dashed #d9d9d9;
  border-radius: 12px;
  padding: 32px 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}
.drop-zone:hover, .drop-zone.drag-over { border-color: #6c5ce7; background: #f0f0ff; }
.drop-icon { font-size: 36px; color: #6c5ce7; margin-bottom: 8px; }
.drop-title { font-size: 14px; margin: 8px 0 4px; }
.drop-hint { font-size: 11px; color: #999; }
.drop-actions { margin-top: 12px; }

.file-list { background: #fafafa; border-radius: 8px; padding: 12px; flex: 1; overflow-y: auto; }
.file-list-header { font-size: 13px; font-weight: 600; color: #666; margin-bottom: 8px; }
.file-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px; font-size: 13px; }
.file-item:hover { background: #f0f0f0; }
.file-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dot { color: #ccc; }
.empty-hint { color: #999; font-size: 12px; text-align: center; padding: 20px; }

.version-panel { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.version-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; font-size: 16px; font-weight: 600; }
.count { font-size: 12px; color: #999; }

.version-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }

.product-header { font-size: 13px; font-weight: 600; color: #666; padding: 8px 0 4px; border-bottom: 1px solid #eee; }

.version-card {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 10px;
  padding: 14px 16px;
  transition: all 0.2s;
}
.version-card:hover { border-color: #6c5ce7; }
.version-card.selected { border-color: rgba(108, 92, 231, 0.4); box-shadow: 0 0 0 1px rgba(108, 92, 231, 0.1); }

.card-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.card-title { font-weight: 600; font-size: 14px; }
.card-duration { font-size: 12px; color: #999; margin-left: auto; }

.card-body { margin: 10px 0; padding-left: 24px; }
.cover-title { font-size: 16px; font-weight: 700; color: #e94560; margin-bottom: 6px; }
.publish-text { font-size: 13px; color: #666; line-height: 1.5; margin-bottom: 8px; }
.tags { display: flex; flex-wrap: wrap; gap: 4px; }

.card-options { padding-left: 24px; display: flex; gap: 16px; }

.empty-versions { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; gap: 12px; color: #ccc; }
</style>
