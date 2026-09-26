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
      <article v-for="item in stats" :key="item.label" class="stat-card">
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
        <span>状态</span>
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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openEdit(row)">编辑</button>
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
          <td :colspan="columns.length + 1" class="empty-state">暂无角色选角数据，可先登记角色</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条角色选角记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="dialogOpen" class="modal-mask" @click.self="closeDialog">
      <div class="modal-card">
        <h3 class="modal-title">{{ editingId === null ? '登记角色' : '编辑角色' }}</h3>
        <div class="modal-grid">
          <label v-for="field in formFields" :key="field" class="modal-field">
            <span>{{ field }}<em v-if="requiredFields.includes(field)">*</em></span>
            <input v-model="form[field]" :placeholder="`请输入${field}`" />
          </label>
        </div>
        <p v-if="dialogError" class="error-text">{{ dialogError }}</p>
        <div class="modal-foot">
          <button class="btn ghost" type="button" @click="closeDialog">取消</button>
          <button class="btn primary" type="button" @click="submitForm">保存</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/casting'
const columns = ["角色编号", "角色名称", "角色类型", "候选演员", "试镜日期", "片酬区间", "签约状态", "角色说明"]
// 可参与筛选的字段，与后端 FILTER_FIELDS 保持一致；状态单独用下拉框。
const filterFields = ["角色编号", "角色名称", "角色类型", "候选演员", "试镜日期"]
const requiredFields = ["角色编号", "角色名称", "角色类型"]
const formFields = columns
const actions = ["安排试镜", "确认定角", "更换演员"]
const statuses = ["待试镜", "试镜中", "已定角", "已换角"]
const stats = [{"label": "待定角色", "value": 0}, {"label": "已定角角色", "value": 0}, {"label": "试镜中角色", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})

const dialogOpen = ref(false)
const editingId = ref<number | null>(null)
const form = ref<Record<string, string>>({})
const dialogError = ref('')

function currentQuery() {
  // 列表与导出复用同一查询串，保证看到什么就导出什么。
  return new URLSearchParams(filters.value).toString()
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export?${currentQuery()}`, '_blank')
}

function blankForm() {
  return Object.fromEntries(formFields.map((field) => [field, '']))
}

function openCreate() {
  editingId.value = null
  form.value = blankForm()
  dialogError.value = ''
  dialogOpen.value = true
}

function openEdit(row: Row) {
  editingId.value = Number(row.id)
  // 用原记录预填，留空字段由后端按非破坏性合并处理，重试不会冲掉角色说明。
  form.value = Object.fromEntries(formFields.map((field) => [field, String(row[field] ?? '')]))
  dialogError.value = ''
  dialogOpen.value = true
}

function closeDialog() {
  dialogOpen.value = false
  dialogError.value = ''
}

async function submitForm() {
  dialogError.value = ''
  errorMessage.value = ''
  const isEdit = editingId.value !== null
  const url = isEdit ? `${ENDPOINT}/${editingId.value}` : ENDPOINT
  try {
    // 失败时不关闭弹窗、不清表单：已填的角色说明等保留下来供继续重试。
    const response = await request(url, {
      method: isEdit ? 'PUT' : 'POST',
      body: JSON.stringify({ values: form.value }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      dialogError.value = payload.message || '角色保存未成功，请检查必填项后重试'
      return
    }
    closeDialog()
    await reload()
  } catch (error) {
    dialogError.value = error instanceof Error ? error.message : '角色保存失败，原记录未改动'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '角色选角动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '角色选角操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}?${currentQuery()}`)
    if (!response.ok) {
      throw new Error('角色列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '角色选角列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  width: 560px;
  max-width: calc(100vw - 32px);
  background: #fff;
  border-radius: 8px;
  padding: 16px 18px;
  border: 1px solid var(--border);
}
.modal-title { margin: 0 0 12px; font-size: 15px; }
.modal-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 14px;
}
.modal-field span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.modal-field em { color: #b42318; font-style: normal; margin-left: 2px; }
.modal-field input { width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
.modal-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
</style>
