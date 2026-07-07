import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

/** @typedef {'user' | 'admin'} LoginMode */

export default function Login() {
  const navigate = useNavigate()
  const { auth, loginAsUser, loginAsAdmin } = useAuth()
  const [mode, setMode] = useState(/** @type {LoginMode} */ ('user'))
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (auth) {
    return null
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return

    setError('')
    setSubmitting(true)
    try {
      if (mode === 'user') {
        await loginAsUser(trimmed)
        navigate('/home', { replace: true })
      } else {
        await loginAsAdmin(trimmed)
        navigate('/admin', { replace: true })
      }
    } catch (err) {
      setError(err.message || '登录失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-gray-900">展示墙</h1>
          <p className="mt-2 text-sm text-gray-400">请选择身份登录进入</p>
        </div>

        <div className="mb-6 flex rounded-lg bg-gray-100 p-1">
          <button
            type="button"
            onClick={() => {
              setMode('user')
              setName('')
              setError('')
            }}
            className={`flex-1 rounded-md py-2.5 text-sm font-medium transition-colors ${
              mode === 'user'
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            用户登录
          </button>
          <button
            type="button"
            onClick={() => {
              setMode('admin')
              setName('')
              setError('')
            }}
            className={`flex-1 rounded-md py-2.5 text-sm font-medium transition-colors ${
              mode === 'admin'
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            管理员登录
          </button>
        </div>

        <form onSubmit={handleSubmit} className="rounded-xl bg-white p-6 shadow-sm">
          <label className="mb-1 block text-sm font-medium text-gray-700">
            {mode === 'user' ? '用户昵称' : '管理员名称'}
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => {
              setName(e.target.value)
              setError('')
            }}
            placeholder={mode === 'user' ? '请输入昵称' : '请输入管理员名称'}
            className="mb-2 w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400"
            autoFocus
          />
          <p className="mb-4 text-xs text-gray-400">
            {mode === 'user' ? '可用用户：张三、李四' : '可用管理员：管理员'}
          </p>

          {error && (
            <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
          )}

          <button
            type="submit"
            disabled={!name.trim() || submitting}
            className={`w-full rounded-lg py-2.5 text-sm font-medium text-white transition-colors disabled:opacity-50 ${
              mode === 'user'
                ? 'bg-blue-600 hover:bg-blue-700'
                : 'bg-gray-800 hover:bg-gray-900'
            }`}
          >
            {submitting ? '登录中…' : `进入${mode === 'user' ? '用户端' : '管理后台'}`}
          </button>
          <p className="mt-3 text-center text-xs text-gray-400">暂未启用密码验证</p>
        </form>
      </div>
    </div>
  )
}
