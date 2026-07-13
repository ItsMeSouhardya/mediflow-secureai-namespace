import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AuthCard, Input } from './Login'

export default function ResetPassword() {
  const [params] = useSearchParams(); const [password, setPassword] = useState(''); const [message, setMessage] = useState(''); const [error, setError] = useState('')
  const submit = async (event) => { event.preventDefault(); setError(''); const response = await fetch('/api/v1/auth/password-reset/confirm', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: params.get('token') || '', new_password: password }) }); const body = await response.json(); if (!response.ok) setError(body.error?.message || 'Reset link is invalid or expired'); else setMessage('Password updated. You can now sign in.') }
  return <AuthCard title="Choose a new password" subtitle="Reset links are short-lived and can only be used once."><form onSubmit={submit} className="space-y-4"><Input label="New password" type="password" value={password} onChange={setPassword} />{error && <p className="text-sm text-red-600">{error}</p>}{message && <p className="text-sm text-emerald-700">{message} <Link className="font-semibold" to="/login">Sign in</Link></p>}<button className="w-full rounded-xl bg-blue-700 py-3 font-semibold text-white">Update password</button></form></AuthCard>
}
