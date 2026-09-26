<template>
  <section class="page" data-module="casting">
    <header class="page-head">
      <div>
        <h2>角色选角管理</h2>
        <p class="page-desc">维护角色，围绕角色编号、角色名称、角色类型、候选演员做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记角色</button>
        <button class="btn" type="button" @click="exportRows">导出角色选角清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>选角状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ displayValue(row, column) }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无符合条件的角色选角数据，可调整筛选条件或先登记角色</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条角色选角记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Stats = Record<string, number>

const ENDPOINT = '/api/casting'
const columns = ["角色编号", "角色名称", "角色类型", "候选演员", "试镜日期", "片酬区间", "签约状态", "角色说明"]
const actions = ["安排试镜", "确认定角", "更换演员"]
const statuses = ["待试镜", "试镜中", "已定角", "已换角"]
// 查询、列表与导出共用的筛选项：加上试镜日期、候选演员与状态后，条件才能真正生效
const filterFields = ["角色编号", "角色名称", "角色类型", "候选演员", "试镜日期"]
const statLabels = [
  { label: "待定角色", key: "待定角色" },
  { label: "已定角角色", key: "已定角角色" },
  { label: "试镜中角色", key: "试镜中角色" },
]

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<Stats>({})
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})

const statCards = computed(() =>
  statLabels.map(({ label, key }) => ({ label, value: stats.value[key] ?? 0 })),
)

function activeFilters() {
  return Object.fromEntries(
    Object.entries(filters.value).map(([key, value]) => [key, value.trim()]).filter(([, value]) => value),
  )
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  // 与列表查询同一条件：直接复用当前筛选参数，导出不再混入未筛选的候选演员
  const query = new URLSearchParams(activeFilters()).toString()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function openCreate() {
  errorMessage.value = '角色登记入口尚未接入审批流'
}

function displayValue(row: Row, column: string): string {
  if (column === '候选演员' && (row.status === '已定角' || row.status === '已换角') && row['选中演员']) {
    return String(row['选中演员'])
  }
  const value = row[column]
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  // 把整行已有内容（含角色说明、试镜日期、候选演员）回传，失败重试时不会丢失
  const payload = { values: { ...row, action } }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    const result = await response.json().catch(() => null)
    if (!response.ok || !result?.ok) {
      throw new Error(result?.message || '角色选角动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '角色选角操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(activeFilters()).toString()
  try {
    const response = await request(`${ENDPOINT}${query ? `?${query}` : ''}`)
    if (!response.ok) {
      throw new Error('角色列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    stats.value = payload.stats ?? {}
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '角色选角列表读取失败'
  }
}

onMounted(reload)
</script>
