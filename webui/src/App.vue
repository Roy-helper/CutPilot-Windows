<script setup lang="ts">
import { ref } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import {
  SettingOutlined,
  HistoryOutlined,
  ScissorOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'

const router = useRouter()
const selectedKey = ref(['workspace'])
const collapsed = ref(false)

const menuItems = [
  { key: 'workspace', icon: ScissorOutlined, label: '工作台', path: '/' },
  { key: 'history', icon: HistoryOutlined, label: '历史记录', path: '/history' },
  { key: 'settings', icon: SettingOutlined, label: '设置', path: '/settings' },
]

function onMenuClick(item: any) {
  const found = menuItems.find(m => m.key === item.key)
  if (found) router.push(found.path)
}
</script>

<template>
  <a-layout style="height: 100vh">
    <a-layout-sider
      v-model:collapsed="collapsed"
      :trigger="null"
      collapsible
      :width="200"
      :collapsed-width="64"
    >
      <div class="logo-area" @click="collapsed = !collapsed">
        <ThunderboltOutlined class="logo-icon" />
        <span v-show="!collapsed" class="logo-text">CutPilot</span>
      </div>

      <a-menu
        v-model:selectedKeys="selectedKey"
        theme="light"
        mode="inline"
        @click="onMenuClick"
      >
        <a-menu-item v-for="item in menuItems" :key="item.key">
          <component :is="item.icon" />
          <span>{{ item.label }}</span>
        </a-menu-item>
      </a-menu>

      <div v-show="!collapsed" class="version-tag">v0.2.0</div>
    </a-layout-sider>

    <a-layout>
      <a-layout-content class="main-content">
        <RouterView />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<style scoped>
.logo-area {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 24px 16px;
  cursor: pointer;
}

.logo-icon {
  font-size: 24px;
  color: #6c5ce7;
}

.logo-text {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.main-content {
  padding: 24px;
  overflow-y: auto;
}

.version-tag {
  position: absolute;
  bottom: 16px;
  left: 0;
  width: 100%;
  text-align: center;
  font-size: 11px;
  color: #999;
}
</style>
