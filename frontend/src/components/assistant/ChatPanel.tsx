import { useMemo, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useAssistantStore } from '../../stores/assistantStore'

interface ChatPanelProps {
  workflowId: string | null
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0 leading-6">{children}</p>,
        ul: ({ children }) => <ul className="mb-2 list-disc pl-5 last:mb-0">{children}</ul>,
        ol: ({ children }) => <ol className="mb-2 list-decimal pl-5 last:mb-0">{children}</ol>,
        li: ({ children }) => <li className="mb-1 last:mb-0">{children}</li>,
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noreferrer" className="text-blue-600 underline">
            {children}
          </a>
        ),
        code: ({ className, children, ...props }) => {
          const isInline = !className
          if (isInline) {
            return (
              <code className="rounded bg-gray-200 px-1 py-0.5 text-xs text-gray-800" {...props}>
                {children}
              </code>
            )
          }
          return (
            <pre className="my-2 overflow-x-auto rounded bg-gray-900 p-3 text-xs text-gray-100">
              <code className={className} {...props}>{children}</code>
            </pre>
          )
        },
        h1: ({ children }) => <h1 className="mb-2 text-base font-bold">{children}</h1>,
        h2: ({ children }) => <h2 className="mb-2 text-sm font-bold">{children}</h2>,
        h3: ({ children }) => <h3 className="mb-1 text-sm font-semibold">{children}</h3>,
        blockquote: ({ children }) => (
          <blockquote className="mb-2 border-l-4 border-gray-300 pl-3 text-gray-600 italic">
            {children}
          </blockquote>
        ),
        table: ({ children }) => (
          <table className="my-2 w-full border-collapse text-xs">
            {children}
          </table>
        ),
        thead: ({ children }) => <thead className="bg-gray-200">{children}</thead>,
        th: ({ children }) => (
          <th className="border border-gray-300 px-2 py-1 text-left font-semibold">{children}</th>
        ),
        td: ({ children }) => (
          <td className="border border-gray-300 px-2 py-1">{children}</td>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  )
}

export function ChatPanel({ workflowId }: ChatPanelProps) {
  const [draft, setDraft] = useState('')
  const isOpen = useAssistantStore((s) => s.isOpen)
  const isStreaming = useAssistantStore((s) => s.isStreaming)
  const closePanel = useAssistantStore((s) => s.closePanel)
  const sendMessage = useAssistantStore((s) => s.sendMessage)
  const toggleTrace = useAssistantStore((s) => s.toggleTrace)
  const messagesByWorkflow = useAssistantStore((s) => s.messagesByWorkflow)

  const messages = useMemo(
    () => (workflowId ? messagesByWorkflow[workflowId] ?? [] : []),
    [messagesByWorkflow, workflowId]
  )

  if (!isOpen) return null

  const canSend = Boolean(workflowId) && draft.trim().length > 0 && !isStreaming

  const submit = async (event?: FormEvent) => {
    event?.preventDefault()
    if (!workflowId || !canSend) return
    const text = draft
    setDraft('')
    await sendMessage(workflowId, text)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void submit()
    }
  }

  return (
    <aside
      className="absolute right-4 top-4 bottom-20 z-20 flex w-[400px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden border border-black bg-white shadow-2xl"
      onMouseDown={(event) => event.stopPropagation()}
      onClick={(event) => event.stopPropagation()}
    >
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3"
      >
        <div>
          <div className="text-sm font-semibold text-gray-900">工作流助手</div>
          <div className="text-xs text-gray-500">
            {workflowId ? '当前 workflow 会话' : '先保存或打开一个 workflow'}
          </div>
        </div>
        <button
          type="button"
          onClick={closePanel}
          className="h-8 w-8 border border-gray-200 text-gray-700 hover:bg-gray-50"
          title="关闭"
        >
          ×
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4"
      >
        {messages.length === 0 && (
          <div className="border border-dashed border-gray-300 px-3 py-4 text-sm text-gray-500">
            问我当前工作流的节点、provider、知识库或运行记录。
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={message.role === 'user' ? 'flex justify-end' : 'flex justify-start'}
          >
            <div
              className={
                message.role === 'user'
                  ? 'max-w-[86%] bg-black px-3 py-2 text-sm text-white'
                  : 'max-w-[92%] bg-gray-100 px-3 py-2 text-sm text-gray-900 ring-1 ring-gray-200'
              }
            >
              {message.toolTraces && message.toolTraces.length > 0 && (
                <div className="mb-2 space-y-1">
                  {message.toolTraces.map((trace) => (
                    <button
                      key={trace.callId}
                      type="button"
                      onClick={() => workflowId && toggleTrace(workflowId, message.id, trace.callId)}
                      className="block w-full border border-gray-200 bg-white px-2 py-1 text-left text-xs text-gray-700 hover:bg-gray-50"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate">调用 {trace.tool}</span>
                        <span>{trace.isOpen ? '收起' : '展开'}</span>
                      </div>
                      {trace.isOpen && (
                        <pre className="mt-2 max-h-36 overflow-auto whitespace-pre-wrap break-words text-[11px] text-gray-500">
                          {JSON.stringify({ args: trace.args, result: trace.summary }, null, 2)}
                        </pre>
                      )}
                    </button>
                  ))}
                </div>
              )}
              {message.role === 'assistant' ? (
                <div className="break-words leading-6">
                  {message.content ? (
                    <MarkdownContent content={message.content} />
                  ) : (
                    '思考中...'
                  )}
                </div>
              ) : (
                <div className="whitespace-pre-wrap break-words leading-6">
                  {message.content}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <form onSubmit={submit} className="border-t border-gray-200 p-3"
      >
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          disabled={!workflowId || isStreaming}
          rows={3}
          className="block min-h-20 w-full resize-none border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 outline-none placeholder:text-gray-400 focus:border-black"
          placeholder={workflowId ? '问问这个 workflow...' : '请先选择 workflow'}
        />
        <div className="mt-2 flex items-center justify-end">
          <button
            type="submit"
            disabled={!canSend}
            className="h-9 bg-black px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400"
          >
            {isStreaming ? '发送中' : '发送'}
          </button>
        </div>
      </form>
    </aside>
  )
}
