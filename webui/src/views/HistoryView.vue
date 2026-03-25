<script setup lang="ts">
import { ref } from 'vue'
import { DeleteOutlined, FolderOpenOutlined } from '@ant-design/icons-vue'

const history = ref([
  { time: '2026-03-25 11:03', name: '产品介绍_01.mp4', success: true, versions: 3, tags: '痛点解决, 价格冲击, 外观颜值' },
  { time: '2026-03-25 10:45', name: '直播切片_02.mp4', success: true, versions: 2, tags: '使用场景, 人群锁定' },
  { time: '2026-03-24 16:20', name: '新品上架_03.mp4', success: false, versions: 0, tags: '素材太短' },
])

const columns = [
  { title: '时间', dataIndex: 'time', width: 160 },
  { title: '视频名称', dataIndex: 'name' },
  { title: '状态', dataIndex: 'success', width: 80 },
  { title: '版本数', dataIndex: 'versions', width: 80 },
  { title: '切入角度', dataIndex: 'tags' },
  { title: '操作', key: 'action', width: 100 },
]
</script>

<template>
  <div class="history-page">
    <div class="page-header">
      <h2>处理历史</h2>
      <a-button danger size="small">
        <DeleteOutlined /> 清空历史
      </a-button>
    </div>

    <a-table
      :dataSource="history"
      :columns="columns"
      :pagination="{ pageSize: 20 }"
      row-key="time"
      size="middle"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'success'">
          <a-tag :color="record.success ? 'green' : 'red'">
            {{ record.success ? '成功' : '失败' }}
          </a-tag>
        </template>
        <template v-if="column.key === 'action'">
          <a-button type="link" size="small">
            <FolderOpenOutlined /> 打开
          </a-button>
        </template>
      </template>
    </a-table>
  </div>
</template>

<style scoped>
.history-page { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: center; }
.page-header h2 { margin: 0; font-size: 20px; }
</style>
