<script setup lang="ts">
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import {
  ApiOutlined,
  ToolOutlined,
  AudioOutlined,
  ExportOutlined,
  SafetyCertificateOutlined,
  CopyOutlined,
} from '@ant-design/icons-vue'

// Provider presets
const providers = [
  { id: 'deepseek', name: 'DeepSeek', hint: 'sk-... (platform.deepseek.com)' },
  { id: 'qwen', name: '通义千问 (阿里云百炼)', hint: 'sk-... (bailian.console.aliyun.com)' },
  { id: 'kimi', name: 'Kimi (月之暗面)', hint: 'sk-... (platform.moonshot.cn)' },
  { id: 'minimax', name: 'MiniMax', hint: 'eyJ... (platform.minimaxi.com)' },
  { id: 'zhipu', name: '智谱 ChatGLM', hint: '从 open.bigmodel.cn 获取' },
  { id: 'custom', name: '自定义 (OpenAI 兼容)', hint: '输入 API Key' },
]

// Settings state
const provider = ref('deepseek')
const apiKey = ref('')
const customUrl = ref('')
const customModel = ref('')
const maxVersions = ref(3)
const minSentences = ref(15)
const quality = ref('standard')
const generateFast = ref(true)
const enableHook = ref(false)
const hotwords = ref('')
const outputDir = ref('')

// License
const machineId = ref('2bac81ca39a1b6d2')
const licenseStatus = ref('有效')
const licenseExpiry = ref('2026-12-31')

const currentHint = ref(providers[0]!.hint)
watch(provider, (val) => {
  const p = providers.find(x => x.id === val)
  currentHint.value = p?.hint ?? ''
})

function testConnection() {
  message.loading('测试连接中...', 1.5)
  setTimeout(() => message.success('连接成功'), 1500)
}

function saveSettings() {
  message.success('设置已保存')
}

function copyMachineId() {
  navigator.clipboard.writeText(machineId.value)
  message.success('已复制')
}
</script>

<template>
  <div class="settings-page">
    <div class="page-header">
      <h2>设置</h2>
      <a-button type="primary" @click="saveSettings">保存设置</a-button>
    </div>

    <div class="settings-grid">
      <!-- License -->
      <div class="settings-section">
        <div class="section-title"><SafetyCertificateOutlined /> 授权信息</div>
        <div class="setting-row">
          <label>机器码</label>
          <div style="display: flex; gap: 8px; align-items: center;">
            <a-input :value="machineId" readonly style="font-family: monospace; width: 200px;" />
            <a-button size="small" @click="copyMachineId"><CopyOutlined /></a-button>
          </div>
        </div>
        <div class="setting-row">
          <label>授权状态</label>
          <a-tag color="green">{{ licenseStatus }}</a-tag>
          <span class="hint">到期: {{ licenseExpiry }}</span>
        </div>
      </div>

      <!-- API -->
      <div class="settings-section">
        <div class="section-title"><ApiOutlined /> AI 模型</div>
        <div class="setting-row">
          <label>模型供应商</label>
          <a-select v-model:value="provider" style="width: 280px;">
            <a-select-option v-for="p in providers" :key="p.id" :value="p.id">
              {{ p.name }}
            </a-select-option>
          </a-select>
        </div>
        <div class="setting-row">
          <label>API Key</label>
          <a-input-password v-model:value="apiKey" :placeholder="currentHint" style="width: 280px;" />
          <a-button @click="testConnection">测试连接</a-button>
        </div>
        <template v-if="provider === 'custom'">
          <div class="setting-row">
            <label>API 地址</label>
            <a-input v-model:value="customUrl" placeholder="https://..." style="width: 280px;" />
          </div>
          <div class="setting-row">
            <label>模型名称</label>
            <a-input v-model:value="customModel" placeholder="model-name" style="width: 280px;" />
          </div>
        </template>
      </div>

      <!-- Processing -->
      <div class="settings-section">
        <div class="section-title"><ToolOutlined /> 处理设置</div>
        <div class="setting-row">
          <label>版本数量</label>
          <a-input-number v-model:value="maxVersions" :min="1" :max="5" />
        </div>
        <div class="setting-row">
          <label>最少句数</label>
          <a-input-number v-model:value="minSentences" :min="5" :max="50" />
          <span class="hint">少于此句数的视频会跳过</span>
        </div>
        <div class="setting-row">
          <label>视频质量</label>
          <a-select v-model:value="quality" style="width: 200px;">
            <a-select-option value="draft">快速预览 (draft)</a-select-option>
            <a-select-option value="standard">标准 (standard)</a-select-option>
            <a-select-option value="high">高质量 (high)</a-select-option>
          </a-select>
        </div>
        <div class="setting-row">
          <label>选项</label>
          <a-checkbox v-model:checked="generateFast">生成 1.25x 加速版</a-checkbox>
          <a-checkbox v-model:checked="enableHook">Hook 文字叠加</a-checkbox>
        </div>
      </div>

      <!-- ASR -->
      <div class="settings-section">
        <div class="section-title"><AudioOutlined /> 语音识别</div>
        <div class="setting-row">
          <label>热词</label>
          <a-input v-model:value="hotwords" placeholder="产品名 品牌名 (空格分隔)" style="width: 320px;" />
        </div>
        <span class="hint">提高品牌名/产品名的识别准确率</span>
      </div>

      <!-- Output -->
      <div class="settings-section">
        <div class="section-title"><ExportOutlined /> 输出</div>
        <div class="setting-row">
          <label>默认输出目录</label>
          <a-input v-model:value="outputDir" placeholder="不设置则输出到视频同目录" style="width: 320px;" />
          <a-button>选择</a-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-page { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: center; }
.page-header h2 { margin: 0; font-size: 20px; }

.settings-grid { display: flex; flex-direction: column; gap: 20px; overflow-y: auto; }

.settings-section {
  background: var(--bg-card);
  border-radius: 10px;
  padding: 20px;
  border: 1px solid var(--border);
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.setting-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.setting-row label {
  width: 100px;
  flex-shrink: 0;
  font-size: 13px;
  color: var(--text-secondary);
  text-align: right;
}

.hint {
  font-size: 11px;
  color: var(--text-muted);
}
</style>
