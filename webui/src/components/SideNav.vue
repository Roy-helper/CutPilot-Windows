<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useWorkspaceStore } from '@/stores/workspace'

const route = useRoute()
const router = useRouter()
const store = useWorkspaceStore()
const showAccountMenu = ref(false)

const navItems = [
  { path: '/', label: '工作台', icon: 'edit_square' },
  { path: '/history', label: '历史记录', icon: 'history' },
  { path: '/settings', label: '设置', icon: 'settings' },
]

async function handleNewProject() {
  if (route.path !== '/') await router.push('/')
  // Small delay to ensure WorkspaceView is mounted
  setTimeout(() => store.importFiles(), 100)
}
</script>

<template>
  <aside class="fixed left-0 top-0 h-full flex flex-col py-6 px-4 bg-[#2e3132] w-64 z-50">
    <div class="mb-10 px-4">
      <h1 class="text-xl font-bold text-white tracking-tighter">CutPilot</h1>
      <p class="text-[10px] text-slate-400 font-medium uppercase tracking-widest mt-1">AI Video Editor</p>
    </div>

    <nav class="flex-1 space-y-2">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="flex items-center gap-3 px-4 py-3 rounded-lg transition-all"
        :class="route.path === item.path
          ? 'text-white bg-[#4f46e5] shadow-md'
          : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'"
      >
        <span
          class="material-symbols-outlined"
          :style="route.path === item.path ? `font-variation-settings: 'FILL' 1;` : ''"
        >{{ item.icon }}</span>
        <span class="font-medium text-sm">{{ item.label }}</span>
        <!-- Processing indicator on workspace tab -->
        <span
          v-if="item.path === '/' && store.isProcessing && route.path !== '/'"
          class="ml-auto w-2 h-2 rounded-full bg-blue-400 animate-pulse"
        ></span>
      </router-link>
    </nav>

    <div class="mt-auto px-2 space-y-4">
      <button
        class="w-full bg-primary-container text-white py-3 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 hover:opacity-90 transition-transform active:scale-95"
        @click="handleNewProject"
      >
        <span class="material-symbols-outlined text-sm">video_call</span>
        导入视频
      </button>

      <!-- Account area -->
      <div class="relative">
        <button
          class="w-full flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-white/5 transition-colors"
          @click="showAccountMenu = !showAccountMenu"
        >
          <div class="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center">
            <span class="material-symbols-outlined text-slate-400 text-sm">person</span>
          </div>
          <div class="overflow-hidden flex-1 text-left">
            <p class="text-xs font-bold text-white truncate">管理员账户</p>
            <p class="text-[10px] text-slate-500">专业版已激活</p>
          </div>
          <span class="material-symbols-outlined text-slate-500 text-sm transition-transform" :class="{ 'rotate-180': showAccountMenu }">expand_more</span>
        </button>

        <!-- Account dropdown -->
        <Transition name="fade">
          <div
            v-if="showAccountMenu"
            class="absolute bottom-full left-0 w-full mb-2 bg-[#3a3d3e] rounded-xl shadow-xl border border-white/5 overflow-hidden"
          >
            <router-link
              to="/settings"
              class="flex items-center gap-3 px-4 py-3 text-slate-300 hover:bg-white/5 transition-colors text-sm"
              @click="showAccountMenu = false"
            >
              <span class="material-symbols-outlined text-sm">manage_accounts</span>
              账户管理
            </router-link>
            <router-link
              to="/settings"
              class="flex items-center gap-3 px-4 py-3 text-slate-300 hover:bg-white/5 transition-colors text-sm"
              @click="showAccountMenu = false"
            >
              <span class="material-symbols-outlined text-sm">card_membership</span>
              订阅套餐
            </router-link>
            <div class="border-t border-white/5">
              <button class="flex items-center gap-3 px-4 py-3 text-slate-400 hover:text-red-400 hover:bg-white/5 transition-colors text-sm w-full text-left">
                <span class="material-symbols-outlined text-sm">logout</span>
                退出登录
              </button>
            </div>
          </div>
        </Transition>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.15s, transform 0.15s;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
</style>
