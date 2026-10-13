<script setup lang="ts" generic="T">
/**
 * DataTable —— 列表页表格（docs/04 2.3）。
 * 统一空/加载中/分页/批量选择；单元格可用 #cell-{prop} 插槽覆写。
 */
import type { PropType } from 'vue';

export interface DataTableColumn {
  prop: string;
  label: string;
  width?: number | string;
  align?: 'left' | 'center' | 'right';
  /** 简单文本渲染；复杂渲染请用 #cell-{prop} 插槽 */
  formatter?: (row: T, index: number) => string;
}

export interface DataTablePagination {
  page: number;
  pageSize: number;
  total: number;
}

defineProps<{
  columns: DataTableColumn[];
  rows: T[];
  rowKey: string;
  loading?: boolean;
  selectable?: boolean;
  emptyText?: string;
  pagination?: DataTablePagination;
}>();

const emit = defineEmits<{
  (e: 'selection-change', rows: T[]): void;
  (e: 'page-change', page: number): void;
  (e: 'size-change', pageSize: number): void;
}>();
</script>

<template>
  <div class="lk-data-table">
    <div v-if="$slots.toolbar" class="lk-data-table__toolbar">
      <slot name="toolbar" />
    </div>

    <el-table
      :data="rows"
      :row-key="rowKey"
      v-loading="loading"
      class="lk-data-table__table"
      @selection-change="(rows: T[]) => emit('selection-change', rows)"
    >
      <el-table-column v-if="selectable" type="selection" width="44" />
      <el-table-column
        v-for="column in columns"
        :key="column.prop"
        :prop="column.prop"
        :label="column.label"
        :width="column.width"
        :align="column.align ?? 'left'"
      >
        <template #default="{ row, $index }">
          <slot :name="`cell-${column.prop}`" :row="row" :index="$index">
            {{ column.formatter ? column.formatter(row, $index) : (row as Record<string, unknown>)[column.prop] }}
          </slot>
        </template>
      </el-table-column>
      <template #empty>
        <slot name="empty">
          <p class="lk-data-table__empty">{{ emptyText ?? '暂无数据' }}</p>
        </slot>
      </template>
    </el-table>

    <div v-if="pagination" class="lk-data-table__pagination">
      <el-pagination
        :current-page="pagination.page"
        :page-size="pagination.pageSize"
        :total="pagination.total"
        layout="total, prev, pager, next"
        background
        @current-change="(page: number) => emit('page-change', page)"
        @size-change="(size: number) => emit('size-change', size)"
      />
    </div>
  </div>
</template>

<style scoped>
.lk-data-table {
  display: flex;
  flex-direction: column;
  gap: var(--lk-space-3);
}

.lk-data-table__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--lk-space-2);
}

.lk-data-table__table {
  border-radius: var(--lk-radius-card);
  border: 0.5px solid var(--lk-border-color);
  background: var(--lk-bg-card);
}

.lk-data-table__empty {
  margin: 0;
  padding: var(--lk-space-8) 0;
  font-size: var(--lk-font-size-sm);
  color: var(--lk-text-weak);
}

.lk-data-table__pagination {
  display: flex;
  justify-content: flex-end;
}
</style>
