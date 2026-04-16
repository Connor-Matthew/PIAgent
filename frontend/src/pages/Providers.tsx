import { useEffect, useMemo, useState } from 'react'
import { providerApi } from '../services/api'
import type { Provider, ProviderTypeInfo } from '../types/provider'

export default function ProvidersPage() {
  const [providers, setProviders] = useState<Provider[]>([])
  const [types, setTypes] = useState<ProviderTypeInfo[]>([])
  const [typesLoading, setTypesLoading] = useState(false)
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState({
    category: 'llm' as 'llm' | 'tts',
    type: '',
    name: '',
    api_key: '',
    base_url: '',
    enabled: true,
    selected_models: [] as string[],
  })
  const [formError, setFormError] = useState<string | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const [testStatus, setTestStatus] = useState<{ msg: string; ok: boolean } | null>(null)
  const [modelsLoading, setModelsLoading] = useState(false)
  const [cachedModels, setCachedModels] = useState<string[] | null>(null)
  const [cachedAt, setCachedAt] = useState<string | null>(null)

  const fetchProviders = async () => {
    setLoading(true)
    try {
      const data = await providerApi.list()
      setProviders(data)
    } catch (e: any) {
      // ignore list errors
    } finally {
      setLoading(false)
    }
  }

  const fetchTypes = async () => {
    setTypesLoading(true)
    try {
      const data = await providerApi.types()
      setTypes(data)
    } catch (e: any) {
      console.error('fetchTypes error', e)
    } finally {
      setTypesLoading(false)
    }
  }

  useEffect(() => {
    fetchProviders()
    fetchTypes()
  }, [])

  const selectedType = useMemo(
    () => types.find((t) => t.type === form.type) || null,
    [types, form.type]
  )

  const availableTypes = useMemo(
    () => types.filter((t) => t.category === form.category),
    [types, form.category]
  )

  const openCreate = () => {
    setEditingId(null)
    const defaultCategory: 'llm' | 'tts' = 'llm'
    const categoryTypes = types.filter((t) => t.category === defaultCategory)
    const defaultType = categoryTypes[0]?.type || ''
    setForm({
      category: defaultCategory,
      type: defaultType,
      name: '',
      api_key: '',
      base_url: defaultType
        ? (categoryTypes.find((t) => t.type === defaultType)?.default_base_url || '')
        : '',
      enabled: true,
      selected_models: [],
    })
    setFormError(null)
    setTestStatus(null)
    setCachedModels(null)
    setCachedAt(null)
    setModalOpen(true)
    if (types.length === 0) {
      fetchTypes()
    }
  }

  const openEdit = (p: Provider) => {
    setEditingId(p.id)
    setForm({
      category: p.category,
      type: p.type,
      name: p.name,
      api_key: '',
      base_url: p.base_url || '',
      enabled: p.enabled,
      selected_models: p.selected_models || [],
    })
    setFormError(null)
    setTestStatus(null)
    setCachedModels(p.extra_config?.cached_models || null)
    setCachedAt(p.extra_config?.cached_at || null)
    setModalOpen(true)
  }

  const closeModal = () => {
    setModalOpen(false)
    setEditingId(null)
    setFormError(null)
    setTestStatus(null)
    setCachedModels(null)
    setCachedAt(null)
  }

  const validate = () => {
    if (!form.type) return '请选择类型'
    if (!form.name.trim()) return '名称不能为空'
    if (editingId === null && !form.api_key.trim()) return 'API Key 不能为空'
    if (selectedType?.requires_base_url && !form.base_url.trim()) {
      return `类型 ${selectedType.type} 需要填写 Base URL`
    }
    return null
  }

  const [listCategory, setListCategory] = useState<'all' | 'llm' | 'tts'>('all')
  const filteredProviders = useMemo(() => {
    if (listCategory === 'all') return providers
    return providers.filter((p) => p.category === listCategory)
  }, [providers, listCategory])

  const getErrorMessage = (e: any): string => {
    const detail = e?.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (detail && typeof detail === 'object') {
      return detail.error || detail.message || JSON.stringify(detail)
    }
    return e?.message || '操作失败'
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const err = validate()
    if (err) {
      setFormError(err)
      return
    }
    setFormError(null)
    try {
      const payload: any = {
        type: form.type,
        category: form.category,
        name: form.name.trim(),
        enabled: form.enabled,
      }
      if (selectedType?.requires_base_url) {
        payload.base_url = form.base_url.trim()
      }
      if (form.api_key.trim()) {
        payload.api_key = form.api_key.trim()
      }
      if (editingId !== null) {
        payload.selected_models = form.selected_models
        await providerApi.update(editingId, payload)
      } else {
        await providerApi.create(payload)
      }
      await fetchProviders()
      closeModal()
    } catch (e: any) {
      setFormError(getErrorMessage(e))
    }
  }

  const handleToggleEnabled = async (p: Provider) => {
    try {
      await providerApi.update(p.id, { enabled: !p.enabled })
      await fetchProviders()
    } catch (e: any) {
      alert(getErrorMessage(e))
    }
  }

  const handleTest = async () => {
    if (editingId === null) return
    setTestStatus(null)
    try {
      const res = await providerApi.test(editingId)
      setTestStatus({ msg: res.status || '连接成功', ok: true })
    } catch (e: any) {
      setTestStatus({ msg: getErrorMessage(e), ok: false })
    }
  }

  const handleRefreshModels = async () => {
    if (editingId === null) return
    setModelsLoading(true)
    try {
      const res = await providerApi.models(editingId, true)
      setCachedModels(res.models)
      setCachedAt(res.cached_at || null)
    } catch (e: any) {
      setFormError(getErrorMessage(e))
    } finally {
      setModelsLoading(false)
    }
  }

  const handleDelete = async () => {
    if (confirmDeleteId === null) return
    try {
      await providerApi.delete(confirmDeleteId)
      setConfirmDeleteId(null)
      await fetchProviders()
    } catch (e: any) {
      alert(getErrorMessage(e))
      if (e?.response?.status !== 409) {
        setConfirmDeleteId(null)
      }
    }
  }

  return (
    <div className="min-h-screen bg-slate-900 text-slate-200 p-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-semibold text-slate-100">Provider 管理</h1>
          <button
            onClick={openCreate}
            className="bg-blue-500 text-white text-sm px-4 py-2 rounded-md hover:bg-blue-600"
          >
            ➕ 新增 Provider
          </button>
        </div>

        <div className="flex items-center gap-2 mb-4">
          {(['all', 'llm', 'tts'] as const).map((c) => (
            <button
              key={c}
              onClick={() => setListCategory(c)}
              className={`px-3 py-1.5 rounded-md text-sm transition-colors ${
                listCategory === c
                  ? 'bg-slate-700 text-slate-100'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              {c === 'all' ? '全部' : c.toUpperCase()}
            </button>
          ))}
        </div>

        <div className="bg-slate-800 border border-slate-700 rounded-md overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-850 border-b border-slate-700">
              <tr>
                <th className="px-4 py-3 font-medium text-slate-400">名称</th>
                <th className="px-4 py-3 font-medium text-slate-400">分类</th>
                <th className="px-4 py-3 font-medium text-slate-400">类型</th>
                <th className="px-4 py-3 font-medium text-slate-400">Base URL</th>
                <th className="px-4 py-3 font-medium text-slate-400">API Key</th>
                <th className="px-4 py-3 font-medium text-slate-400">状态</th>
                <th className="px-4 py-3 font-medium text-slate-400 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredProviders.map((p) => (
                <tr key={p.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                  <td className="px-4 py-3 text-slate-200">{p.name}</td>
                  <td className="px-4 py-3 text-slate-300 uppercase text-xs">{p.category}</td>
                  <td className="px-4 py-3 text-slate-300">{p.type}</td>
                  <td className="px-4 py-3 text-slate-400">{p.base_url || '-'}</td>
                  <td className="px-4 py-3 text-slate-400 font-mono">{p.api_key}</td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleToggleEnabled(p)}
                      className={`inline-flex items-center px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                        p.enabled
                          ? 'bg-green-500/20 text-green-300 hover:bg-green-500/30'
                          : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                      }`}
                    >
                      {p.enabled ? '已启用' : '已禁用'}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-2">
                      <button
                        onClick={() => openEdit(p)}
                        className="text-xs px-2.5 py-1.5 rounded bg-slate-700 text-slate-200 hover:bg-slate-600"
                      >
                        编辑
                      </button>
                      <button
                        onClick={() => setConfirmDeleteId(p.id)}
                        className="text-xs px-2.5 py-1.5 rounded bg-red-500/20 text-red-300 hover:bg-red-500/30"
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filteredProviders.length === 0 && !loading && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                    暂无 Provider，点击右上角新增
                  </td>
                </tr>
              )}
              {loading && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                    加载中...
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="bg-slate-800 border border-slate-700 rounded-md w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="px-5 py-4 border-b border-slate-700 flex items-center justify-between">
              <h2 className="text-base font-semibold text-slate-100">
                {editingId !== null ? '编辑 Provider' : '新增 Provider'}
              </h2>
              <button
                onClick={closeModal}
                className="text-slate-400 hover:text-slate-200"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSubmit} className="px-5 py-4 space-y-4">
              {formError && (
                <div className="bg-red-500/10 border border-red-500/30 text-red-300 px-3 py-2 rounded text-sm">
                  {formError}
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <label className="block">
                  <span className="text-xs text-slate-400 block mb-1">分类</span>
                  <select
                    value={form.category}
                    disabled={!!editingId}
                    onChange={(e) => {
                      const category = e.target.value as 'llm' | 'tts'
                      const catTypes = types.filter((t) => t.category === category)
                      const firstType = catTypes[0]?.type || ''
                      setForm((f) => ({
                        ...f,
                        category,
                        type: firstType,
                        base_url: firstType
                          ? (catTypes.find((t) => t.type === firstType)?.default_base_url || '')
                          : '',
                      }))
                    }}
                    className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-200 disabled:opacity-50"
                  >
                    <option value="llm">LLM</option>
                    <option value="tts">TTS</option>
                  </select>
                </label>

                <label className="block">
                  <span className="text-xs text-slate-400 block mb-1">类型</span>
                  <select
                    value={form.type}
                    disabled={typesLoading || availableTypes.length === 0}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        type: e.target.value,
                        base_url:
                          availableTypes.find((t) => t.type === e.target.value)?.default_base_url || '',
                      }))
                    }
                    className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-200 disabled:opacity-50"
                  >
                    <option value="">
                      {typesLoading ? '加载中...' : availableTypes.length === 0 ? '暂无可用类型' : '请选择'}
                    </option>
                    {availableTypes.map((t) => (
                      <option key={t.type} value={t.type}>
                        {t.type}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <label className="block">
                <span className="text-xs text-slate-400 block mb-1">名称</span>
                <input
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-200"
                  placeholder="例如 OpenAI 官方"
                />
              </label>

              <label className="block">
                <span className="text-xs text-slate-400 block mb-1">
                  API Key {editingId !== null && '（留空表示不修改）'}
                </span>
                <input
                  type="password"
                  value={form.api_key}
                  onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
                  className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-200"
                  placeholder="sk-..."
                />
              </label>

              {selectedType?.requires_base_url && (
                <label className="block">
                  <span className="text-xs text-slate-400 block mb-1">
                    Base URL <span className="text-red-400">*</span>
                  </span>
                  <input
                    value={form.base_url}
                    onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
                    className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-200"
                    placeholder="https://api.example.com/v1"
                  />
                </label>
              )}

              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
                  className="rounded border-slate-600 bg-slate-900"
                />
                <span className="text-sm text-slate-300">启用</span>
              </label>

              {editingId !== null && (
                <div className="pt-2 border-t border-slate-700 space-y-3">
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={handleTest}
                      className="text-xs px-3 py-1.5 rounded bg-blue-500/20 text-blue-300 hover:bg-blue-500/30"
                    >
                      🔌 测试连接
                    </button>
                    {testStatus && (
                      <span
                        className={`text-xs ${
                          testStatus.ok ? 'text-green-400' : 'text-red-400'
                        }`}
                      >
                        {testStatus.msg}
                      </span>
                    )}
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs text-slate-400">模型列表</span>
                      <button
                        type="button"
                        onClick={handleRefreshModels}
                        disabled={modelsLoading}
                        className="text-xs px-2.5 py-1 rounded bg-slate-700 text-slate-200 hover:bg-slate-600 disabled:opacity-50"
                      >
                        {modelsLoading ? '刷新中...' : '🔄 刷新'}
                      </button>
                    </div>
                    {cachedModels && cachedModels.length > 0 ? (
                      <div className="bg-slate-900 border border-slate-700 rounded-md p-2 max-h-40 overflow-y-auto">
                        <div className="flex items-center justify-between mb-1">
                          <button
                            type="button"
                            onClick={() => setForm((f) => ({ ...f, selected_models: cachedModels }))}
                            className="text-[10px] text-blue-300 hover:text-blue-200"
                          >
                            全选
                          </button>
                          <button
                            type="button"
                            onClick={() => setForm((f) => ({ ...f, selected_models: [] }))}
                            className="text-[10px] text-slate-400 hover:text-slate-300"
                          >
                            清空
                          </button>
                        </div>
                        <ul className="space-y-1">
                          {cachedModels.map((m) => (
                            <li key={m} className="flex items-center gap-2">
                              <input
                                type="checkbox"
                                checked={form.selected_models.includes(m)}
                                onChange={(e) => {
                                  const next = e.target.checked
                                    ? [...form.selected_models, m]
                                    : form.selected_models.filter((x) => x !== m)
                                  setForm((f) => ({ ...f, selected_models: next }))
                                }}
                                className="rounded border-slate-600 bg-slate-900"
                              />
                              <span className="text-xs text-slate-300 font-mono">{m}</span>
                            </li>
                          ))}
                        </ul>
                        {cachedAt && (
                          <div className="mt-2 text-[10px] text-slate-500">
                            缓存于 {new Date(cachedAt).toLocaleString()}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-xs text-slate-500">
                        暂无模型缓存，点击刷新获取
                      </div>
                    )}

                    {form.selected_models.length > 0 && (
                      <div className="pt-2 border-t border-slate-700">
                        <div className="text-[10px] text-slate-400 mb-1">已选中的模型（节点配置可见）</div>
                        <div className="flex flex-wrap gap-1">
                          {form.selected_models.map((m) => (
                            <span
                              key={m}
                              className="inline-flex items-center gap-1 text-[10px] bg-blue-500/20 text-blue-300 px-1.5 py-0.5 rounded"
                            >
                              {m}
                              <button
                                type="button"
                                onClick={() =>
                                  setForm((f) => ({
                                    ...f,
                                    selected_models: f.selected_models.filter((x) => x !== m),
                                  }))
                                }
                                className="text-blue-300 hover:text-blue-200"
                                title="移除"
                              >
                                ×
                              </button>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={closeModal}
                  className="px-4 py-2 text-sm rounded-md bg-slate-700 text-slate-200 hover:bg-slate-600"
                >
                  取消
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 text-sm rounded-md bg-blue-500 text-white hover:bg-blue-600"
                >
                  保存
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirm */}
      {confirmDeleteId !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="bg-slate-800 border border-slate-700 rounded-md w-full max-w-sm p-5">
            <h3 className="text-base font-semibold text-slate-100 mb-2">确认删除</h3>
            <p className="text-sm text-slate-400 mb-4">
              删除后无法恢复，是否继续？
            </p>
            <div className="flex items-center justify-end gap-3">
              <button
                onClick={() => setConfirmDeleteId(null)}
                className="px-4 py-2 text-sm rounded-md bg-slate-700 text-slate-200 hover:bg-slate-600"
              >
                取消
              </button>
              <button
                onClick={handleDelete}
                className="px-4 py-2 text-sm rounded-md bg-red-500 text-white hover:bg-red-600"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
