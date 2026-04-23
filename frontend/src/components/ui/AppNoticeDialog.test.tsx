import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

import { AppNoticeDialog } from './AppNoticeDialog'

describe('AppNoticeDialog', () => {
  test('renders a blocking notice with a dismiss action', () => {
    const html = renderToStaticMarkup(
      <AppNoticeDialog
        title="删除失败"
        message="当前 Provider 正在被工作流引用。"
        actionLabel="我知道了"
        onClose={() => {}}
      />
    )

    expect(html).toContain('删除失败')
    expect(html).toContain('当前 Provider 正在被工作流引用。')
    expect(html).toContain('我知道了')
    expect(html).toContain('role="dialog"')
  })
})
