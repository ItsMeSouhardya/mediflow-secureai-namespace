import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AuthCard } from './Login'

export default function ActivateAccount() {
  const [params] = useSearchParams(); const [state, setState] = useState('Verifying your activation link…')
  useEffect(() => { fetch('/api/v1/auth/activation/confirm', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: params.get('token') || '' }) }).then(async (response) => { const body = await response.json(); if (!response.ok) throw new Error(body.error?.message || 'Activation link is invalid or expired'); setState('Your email has been verified.') }).catch((error) => setState(error.message)) }, [params])
  return <AuthCard title="Account activation" subtitle={state}><Link className="inline-block rounded-xl bg-blue-700 px-5 py-3 font-semibold text-white" to="/login">Continue to sign in</Link></AuthCard>
}
