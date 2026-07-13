import { useState } from 'react'
import { AuthCard, Input } from './Login'

export default function ForgotPassword() {
  const [identifier, setIdentifier] = useState(''); const [message, setMessage] = useState('')
  const submit = async (event) => { event.preventDefault(); await fetch('/api/v1/auth/password-reset/request', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ identifier }) }); setMessage('If that account exists, reset instructions have been issued.') }
  return <AuthCard title="Reset password" subtitle="For privacy, the response is the same whether an account exists or not."><form onSubmit={submit} className="space-y-4"><Input label="Email or phone" value={identifier} onChange={setIdentifier} />{message && <p className="text-sm text-emerald-700">{message}</p>}<button className="w-full rounded-xl bg-blue-700 py-3 font-semibold text-white">Request reset</button></form></AuthCard>
}
