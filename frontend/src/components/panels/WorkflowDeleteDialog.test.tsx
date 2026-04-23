import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

import { WorkflowDeleteDialog } from './WorkflowDeleteDialog'

describe('WorkflowDeleteDialog', () => {
  test('renders confirmation copy and destructive actions', () => {
    const html = renderToStaticMarkup(
      <WorkflowDeleteDialog
        mode="confirm"
        workflowName="未命名工作流"
        isDeleting={false}
        onCancel={() => {}}
        onConfirm={() => {}}
      />
    )

    expect(html).toContain('确认删除')
    expect(html).toContain('未命名工作流')
    expect(html).toContain('此操作不可撤销')
    expect(html).toContain('取消')
    expect(html).toContain('删除')
  })

  test('shows a loading state while deletion is in flight', () => {
    const html = renderToStaticMarkup(
      <WorkflowDeleteDialog
        mode="confirm"
        workflowName="工作流 A"
        isDeleting
        onCancel={() => {}}
        onConfirm={() => {}}
      />
    )

    expect(html).toContain('删除中...')
    expect(html).toContain('disabled')
  })

  test('renders a blocking error dialog with acknowledgement action', () => {
    const html = renderToStaticMarkup(
      <WorkflowDeleteDialog
        mode="error"
        workflowName="工作流 A"
        errorMessage="删除失败，请稍后重试。"
        onClose={() => {}}
      />
    )

    expect(html).toContain('删除失败')
    expect(html).toContain('删除失败，请稍后重试。')
    expect(html).toContain('我知道了')
  })
})
