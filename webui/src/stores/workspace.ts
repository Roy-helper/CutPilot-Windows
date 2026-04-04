/**
 * Workspace store — persists file list, versions, and processing state
 * across route changes. This is the single source of truth for the
 * workspace page.
 */
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import {
  selectFiles, processBatch, exportVersions, getEncoderInfo, getMaxParallel,
  previewVideo, openFolder, checkAsrStatus, checkAllModelStatus, runBenchmark,
  generateThumbnail, cancelProcessing, loadSettings,
  type ProcessResult, type EncoderInfo,
} from '@/bridge'
import { useNotificationStore } from './notifications'

export interface VideoFile {
  name: string
  path: string
  icon: string
  status: 'processing' | 'done' | 'pending' | 'error'
  statusLabel: string
  stage: string       // pipeline stage label for queue panel
  stagePercent: number // percent within current stage
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
  outputPath: string  // path to the generated video file
  thumbnail: string   // base64 data URI of video frame
}

export const useWorkspaceStore = defineStore('workspace', () => {
  const files = ref<VideoFile[]>([])
  const versions = ref<Version[]>([])
  const progress = ref(0)
  const progressText = ref('')
  const isProcessing = ref(false)
  const isExporting = ref(false)

  const encoderName = ref('检测中...')
  const maxParallel = ref(2)
  const encoderDetected = ref(false)

  // ASR model readiness
  const asrModelReady = ref(true) // optimistic default until checked
  const asrModelChecked = ref(false)
  const asrDownloading = ref(false)
  let _asrPollTimer: ReturnType<typeof setInterval> | null = null

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
    // Initial ASR model check
    await refreshAsrStatus()
  }

  async function refreshAsrStatus() {
    try {
      const settings = await loadSettings()
      const engine = (settings.asr_engine as string) || 'faster-whisper'
      const modelSize = (settings.asr_model_size as string) || 'small'
      const status = await checkAsrStatus(engine, modelSize)
      asrModelReady.value = status.ready
      asrModelChecked.value = true

      // If not ready, start polling every 5s until it becomes ready
      if (!status.ready && !_asrPollTimer) {
        _startAsrPoll(engine, modelSize)
      }
      if (status.ready && _asrPollTimer) {
        clearInterval(_asrPollTimer)
        _asrPollTimer = null
      }
    } catch { /* dev mode */ }
  }

  function _startAsrPoll(engine: string, modelSize: string) {
    _asrPollTimer = setInterval(async () => {
      try {
        const status = await checkAsrStatus(engine, modelSize)
        asrModelReady.value = status.ready
        if (status.ready && _asrPollTimer) {
          clearInterval(_asrPollTimer)
          _asrPollTimer = null
        }
      } catch { /* ignore */ }
    }, 5000)
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
          stage: '', stagePercent: 0,
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
      if (fullPath && fullPath !== f.name && (fullPath.startsWith('/') || /^[A-Z]:/i.test(fullPath))) {
        hasRealPaths = true
        if (!files.value.some(vf => vf.path === fullPath)) {
          files.value.push({
            name: f.name, path: fullPath, icon: 'video_library',
            status: 'pending', statusLabel: '待处理',
            stage: '', stagePercent: 0,
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
      file.stage = '排队中'
      file.stagePercent = 0
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
              hashtags: v.tags.map(t => t.startsWith('#') ? t : `#${t}`),
              selected: true,
              outputPath: outputMap.get(v.version_id) ?? '',
              thumbnail: '',
            })
          }
          // Generate thumbnails in background (don't block UI)
          for (const ver of versions.value.filter(vv => vv.videoPath === file.path && !vv.thumbnail)) {
            const videoForThumb = ver.outputPath || file.path
            generateThumbnail(videoForThumb).then(thumb => {
              if (thumb) ver.thumbnail = thumb
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

  async function cancelGenerate() {
    if (!isProcessing.value) return
    await cancelProcessing()
    isProcessing.value = false
    progress.value = 0
    progressText.value = ''
    // Reset any files that were in 'processing' state back to 'pending'
    for (const file of files.value) {
      if (file.status === 'processing') {
        file.status = 'pending'
        file.statusLabel = '已取消'
        file.stage = ''
        file.stagePercent = 0
      }
    }
    const notify = useNotificationStore()
    notify.add('info', '已取消处理', '视频处理已被取消')
  }

  async function exportSelected() {
    const selected = selectedVersions.value
    if (selected.length === 0) return

    isExporting.value = true
    const notify = useNotificationStore()
    try {
      const groups = new Map<string, number[]>()
      for (const v of selected) {
        const ids = groups.get(v.videoPath) ?? []
        ids.push(v.versionId)
        groups.set(v.videoPath, ids)
      }
      let exportCount = 0
      let failCount = 0
      for (const [videoPath, versionIds] of groups) {
        const res = await exportVersions(videoPath, versionIds)
        if (res.success) exportCount += versionIds.length
        else failCount += versionIds.length
      }
      if (exportCount > 0) {
        notify.add('success', '导出完成', `${exportCount} 个版本已导出`)
      }
      if (failCount > 0) {
        notify.add('error', '部分导出失败', `${failCount} 个版本导出失败`)
      }
    } catch (e: any) {
      notify.add('error', '导出异常', e.message || '未知错误')
    } finally {
      isExporting.value = false
    }
  }

  function clear() {
    if (isProcessing.value) return
    if (files.value.length === 0 && versions.value.length === 0) return
    if (!globalThis.confirm('确定要清空所有文件和版本吗？此操作不可撤销。')) return
    files.value = []
    versions.value = []
    progress.value = 0
    progressText.value = ''
  }

  function updateFileProgress(index: number, label: string, percent: number, stage?: string) {
    const f = files.value[index]
    if (f) {
      f.statusLabel = `${label} ${percent}%`
      if (stage) {
        f.stage = stage
        f.stagePercent = percent
      }
    }
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
      const lastSep = Math.max(firstPath.lastIndexOf('/'), firstPath.lastIndexOf('\\'))
      const dir = lastSep > 0 ? firstPath.substring(0, lastSep) : firstPath
      await openFolder(dir)
    }
  }

  const failedFiles = computed(() => files.value.filter(f => f.status === 'error'))

  const generateDisabledReason = computed<string>(() => {
    if (pendingFiles.value.length === 0) return '请先导入视频文件'
    if (!asrModelChecked.value) return ''  // still loading, don't block yet
    if (!asrModelReady.value) return '请先在设置页下载语音模型'
    return ''
  })
  const isBatchMode = computed(() => files.value.length > 1 && (isProcessing.value || files.value.some(f => f.status !== 'pending')))
  const batchDoneCount = computed(() => files.value.filter(f => f.status === 'done').length)
  const batchFailCount = computed(() => files.value.filter(f => f.status === 'error').length)

  async function retryFailed() {
    const failed = failedFiles.value
    if (failed.length === 0 || isProcessing.value) return

    // Reset failed files to pending
    for (const file of failed) {
      file.status = 'processing'
      file.statusLabel = '重试中...'
      file.stage = '排队中'
      file.stagePercent = 0
      file.icon = 'video_library'
    }

    isProcessing.value = true
    progressText.value = `正在重试 ${failed.length} 个失败视频...`
    progress.value = 5

    try {
      const paths = failed.map(f => f.path)
      const results = await processBatch(paths)

      for (let i = 0; i < failed.length; i++) {
        const file = failed[i]!
        const result = results[i]!
        file.result = result

        if (result.success) {
          file.status = 'done'
          file.statusLabel = `${result.versions.length} 个版本`
          const outputMap = new Map<number, string>()
          for (const of_ of (result.output_files ?? [])) {
            if (!outputMap.has(of_.version_id)) outputMap.set(of_.version_id, of_.path)
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
              hashtags: v.tags.map(t => t.startsWith('#') ? t : `#${t}`),
              selected: true,
              outputPath: outputMap.get(v.version_id) ?? '',
              thumbnail: '',
            })
          }
          for (const ver of versions.value.filter(vv => vv.videoPath === file.path && !vv.thumbnail)) {
            const videoForThumb = ver.outputPath || file.path
            generateThumbnail(videoForThumb).then(thumb => { if (thumb) ver.thumbnail = thumb })
          }
        } else {
          file.status = 'error'
          file.statusLabel = result.error || '重试仍失败'
          file.icon = 'error'
        }
      }
      const notify = useNotificationStore()
      const retried = failed.length
      const fixed = failed.filter(f => f.status === 'done').length
      notify.add(fixed === retried ? 'success' : 'error',
        `重试完成: ${fixed}/${retried} 成功`,
        fixed < retried ? `${retried - fixed} 个仍然失败` : '')
    } finally {
      isProcessing.value = false
      progress.value = 0
      progressText.value = ''
    }
  }

  return {
    files, versions, progress, progressText, isProcessing, isExporting,
    encoderName, maxParallel, asrModelReady, generateDisabledReason,
    pendingFiles, failedFiles, isBatchMode, batchDoneCount, batchFailCount,
    selectedVersions, hasFiles, hasVersions,
    detectEncoder, refreshAsrStatus, importFiles, addDroppedFiles, generate,
    cancelGenerate, retryFailed, exportSelected, clear, updateFileProgress,
    preview, openOutputFolder,
  }
})
