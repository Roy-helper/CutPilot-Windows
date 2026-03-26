/**
 * Workspace store — persists file list, versions, and processing state
 * across route changes. This is the single source of truth for the
 * workspace page.
 */
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import {
  selectFiles, processBatch, exportVersions, getEncoderInfo, getMaxParallel,
  previewVideo, openFolder, checkAsrStatus, runBenchmark,
  type ProcessResult, type EncoderInfo,
} from '@/bridge'
import { useNotificationStore } from './notifications'

export interface VideoFile {
  name: string
  path: string
  icon: string
  status: 'processing' | 'done' | 'pending' | 'error'
  statusLabel: string
  result?: ProcessResult
}

export interface Version {
  versionId: number
  videoPath: string
  title: string
  description: string
  duration: string
  score: number
  tags: string[]
  hashtags: string[]
  selected: boolean
  autoExport: boolean
  outputPath: string  // path to the generated video file
}

export const useWorkspaceStore = defineStore('workspace', () => {
  const files = ref<VideoFile[]>([])
  const versions = ref<Version[]>([])
  const progress = ref(0)
  const progressText = ref('')
  const isProcessing = ref(false)

  const encoderName = ref('检测中...')
  const maxParallel = ref(2)
  const encoderDetected = ref(false)

  // Computed helpers
  const pendingFiles = computed(() => files.value.filter(f => f.status === 'pending' || f.status === 'error'))
  const selectedVersions = computed(() => versions.value.filter(v => v.selected))
  const hasFiles = computed(() => files.value.length > 0)
  const hasVersions = computed(() => versions.value.length > 0)

  async function detectEncoder() {
    if (encoderDetected.value) return
    // Run full benchmark for accurate parallel count
    const bench = await runBenchmark()
    encoderName.value = bench.is_hardware ? `${bench.encoder} (硬件加速)` : bench.encoder
    maxParallel.value = bench.max_parallel
    encoderDetected.value = true
  }

  async function importFiles() {
    const paths = await selectFiles()
    const videoExts = ['.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv']
    const invalidExts = ['.downloading', '.tmp', '.part', '.crdownload']
    const notify = useNotificationStore()

    for (const p of paths) {
      const name = p.split('/').pop() ?? p
      const lower = name.toLowerCase()

      // Reject files still downloading
      if (invalidExts.some(ext => lower.endsWith(ext))) {
        notify.add('error', '文件未下载完成', `${name} 还在下载中，请等下载完成后再导入`)
        continue
      }

      // Reject non-video files
      if (!videoExts.some(ext => lower.endsWith(ext))) {
        notify.add('error', '不支持的文件格式', `${name} 不是支持的视频格式`)
        continue
      }

      if (!files.value.some(f => f.path === p)) {
        files.value.push({
          name, path: p, icon: 'video_library',
          status: 'pending', statusLabel: '待处理',
        })
      }
    }
  }

  async function addDroppedFiles(droppedFiles: FileList) {
    // HTML5 File API doesn't expose full paths in pywebview.
    // Electron exposes f.path, but pywebview doesn't.
    // Check if paths are available; if not, fall back to file picker.
    const videoExts = ['.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv']
    let hasRealPaths = false

    for (const f of Array.from(droppedFiles)) {
      const ext = '.' + f.name.split('.').pop()?.toLowerCase()
      if (!videoExts.includes(ext)) continue

      const fullPath = (f as any).path
      if (fullPath && fullPath !== f.name && fullPath.startsWith('/')) {
        hasRealPaths = true
        if (!files.value.some(vf => vf.path === fullPath)) {
          files.value.push({
            name: f.name, path: fullPath, icon: 'video_library',
            status: 'pending', statusLabel: '待处理',
          })
        }
      }
    }

    // If no real paths (pywebview), fall back to native file picker
    if (!hasRealPaths) {
      await importFiles()
    }
  }

  async function generate() {
    if (isProcessing.value) return
    if (pendingFiles.value.length === 0) return

    // Check ASR model
    const asrStatus = await checkAsrStatus()
    if (!asrStatus.ready) {
      const notify = useNotificationStore()
      notify.add('error', '语音模型未下载', '请先在设置页或环境配置页下载语音模型')
      return
    }

    isProcessing.value = true
    const pending = pendingFiles.value

    for (const file of pending) {
      file.status = 'processing'
      file.statusLabel = '排队中...'
      file.icon = 'video_library'
    }

    progressText.value = `正在处理 0/${pending.length} 个视频...`
    progress.value = 5

    try {
      const paths = pending.map(f => f.path)
      const results = await processBatch(paths)

      for (let i = 0; i < pending.length; i++) {
        const file = pending[i]!
        const result = results[i]!
        file.result = result

        if (result.success) {
          file.status = 'done'
          file.statusLabel = `${result.versions.length} 个版本`
          // Build output path lookup from result
          const outputMap = new Map<number, string>()
          for (const of_ of (result.output_files ?? [])) {
            if (!outputMap.has(of_.version_id)) {
              outputMap.set(of_.version_id, of_.path)
            }
          }
          for (const v of result.versions) {
            const mins = Math.floor(v.estimated_duration / 60)
            const secs = Math.round(v.estimated_duration % 60)
            versions.value.push({
              versionId: v.version_id,
              videoPath: file.path,
              title: v.cover_title || v.title,
              description: v.publish_text,
              duration: `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`,
              score: v.score,
              tags: [v.approach_tag],
              hashtags: v.tags.map(t => `#${t}`),
              selected: true,
              autoExport: false,
              outputPath: outputMap.get(v.version_id) ?? '',
            })
          }
        } else {
          file.status = 'error'
          file.statusLabel = result.error || '处理失败'
          file.icon = 'error'
        }
      }
      // Notify results
      const notify = useNotificationStore()
      const doneCount = pending.filter(f => f.status === 'done').length
      const errCount = pending.filter(f => f.status === 'error').length
      if (doneCount > 0) {
        const totalVersions = versions.value.length
        notify.add('success', `${doneCount} 个视频处理完成`, `共生成 ${totalVersions} 个版本`)
      }
      if (errCount > 0) {
        notify.add('error', `${errCount} 个视频处理失败`, '请检查文件格式或网络连接')
      }
    } finally {
      progress.value = 0
      progressText.value = ''
      isProcessing.value = false
    }
  }

  async function exportSelected() {
    const selected = selectedVersions.value
    if (selected.length === 0) return

    const groups = new Map<string, number[]>()
    for (const v of selected) {
      const ids = groups.get(v.videoPath) ?? []
      ids.push(v.versionId)
      groups.set(v.videoPath, ids)
    }
    let exportCount = 0
    for (const [videoPath, versionIds] of groups) {
      const res = await exportVersions(videoPath, versionIds)
      if (res.success) exportCount += versionIds.length
    }
    const notify = useNotificationStore()
    if (exportCount > 0) {
      notify.add('success', '导出完成', `${exportCount} 个版本已导出`)
    }
  }

  function clear() {
    if (isProcessing.value) return
    files.value = []
    versions.value = []
    progress.value = 0
    progressText.value = ''
  }

  function updateFileProgress(index: number, label: string, percent: number) {
    const f = files.value[index]
    if (f) f.statusLabel = `${label} ${percent}%`
  }

  async function preview(ver: Version) {
    if (!ver.outputPath) {
      const notify = useNotificationStore()
      notify.add('error', '无法预览', '未找到输出文件，请先导出')
      return
    }
    await previewVideo(ver.outputPath)
  }

  async function openOutputFolder() {
    // Open the output directory for the first done file
    const doneFile = files.value.find(f => f.status === 'done')
    if (doneFile?.result?.output_files?.[0]) {
      const firstPath = doneFile.result.output_files[0].path
      const dir = firstPath.substring(0, firstPath.lastIndexOf('/'))
      await openFolder(dir)
    }
  }

  return {
    files, versions, progress, progressText, isProcessing,
    encoderName, maxParallel,
    pendingFiles, selectedVersions, hasFiles, hasVersions,
    detectEncoder, importFiles, addDroppedFiles, generate,
    exportSelected, clear, updateFileProgress, preview, openOutputFolder,
  }
})
