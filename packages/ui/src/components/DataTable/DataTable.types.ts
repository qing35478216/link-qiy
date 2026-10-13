/**
 * DataTable 列/分页类型（独立文件：泛型 script-setup 内声明的导出接口无法引用泛型参数 T，
 * vue-tsc 会报 "Cannot find name 'T'"，故抽到非泛型模块）。
 */
export interface DataTableColumn<T = unknown> {
  prop: string;
  label: string;
  width?: number | string;
  align?: 'left' | 'center' | 'right';
  /** 简单文本渲染；复杂渲染请用 #cell-{prop} 插槽。
   *  method 写法（非属性写法）：保持泛型列类型在 unknown 具化时的双向兼容 */
  formatter?(row: T, index: number): string;
}

export interface DataTablePagination {
  page: number;
  pageSize: number;
  total: number;
}
