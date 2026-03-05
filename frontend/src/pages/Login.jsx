import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import api from '../services/api'

export default function Login() {
    const [isRegister, setIsRegister] = useState(false)
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [name, setName] = useState('')
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)
    const navigate = useNavigate()

    const handleSubmit = async (e) => {
        e.preventDefault()
        setError('')
        setLoading(true)

        try {
            const endpoint = isRegister ? '/api/auth/register' : '/api/auth/login'
            const payload = isRegister
                ? { email, password, name }
                : { email, password }

            const res = await api.post(endpoint, payload)
            localStorage.setItem('access_token', res.data.access_token)
            localStorage.setItem('user', JSON.stringify(res.data.user))
            navigate('/dashboard')
        } catch (err) {
            setError(err.response?.data?.detail || 'Something went wrong')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="min-h-screen bg-gray-50 flex items-center justify-center">
            <div className="w-full max-w-sm">
                {/* Logo */}
                <div className="text-center mb-8">
                    <div className="w-14 h-14 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-4">
                        <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                        </svg>
                    </div>
                    <h1 className="text-2xl font-bold text-gray-900">Drive Defender</h1>
                    <p className="text-sm text-gray-500 mt-1">
                        {isRegister ? 'Create your account' : 'Sign in to your account'}
                    </p>
                </div>

                {/* Form */}
                <div className="bg-white rounded-2xl border border-gray-200 p-6">
                    {error && (
                        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-2.5 mb-4">
                            {error}
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-4">
                        {isRegister && (
                            <div>
                                <label className="text-xs font-semibold text-gray-600 mb-1.5 block">Name</label>
                                <input
                                    type="text"
                                    value={name}
                                    onChange={(e) => setName(e.target.value)}
                                    className="w-full px-3.5 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                    placeholder="Your name"
                                    required
                                />
                            </div>
                        )}

                        <div>
                            <label className="text-xs font-semibold text-gray-600 mb-1.5 block">Email</label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="w-full px-3.5 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                placeholder="you@example.com"
                                required
                            />
                        </div>

                        <div>
                            <label className="text-xs font-semibold text-gray-600 mb-1.5 block">Password</label>
                            <input
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="w-full px-3.5 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                placeholder="••••••••"
                                required
                            />
                        </div>

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold text-sm py-2.5 rounded-lg transition-colors disabled:opacity-50"
                        >
                            {loading ? 'Please wait...' : isRegister ? 'Create Account' : 'Sign In'}
                        </button>
                    </form>

                    <div className="mt-4 text-center">
                        <button
                            onClick={() => { setIsRegister(!isRegister); setError('') }}
                            className="text-sm text-blue-600 hover:text-blue-800 font-medium"
                        >
                            {isRegister ? 'Already have an account? Sign in' : "Don't have an account? Register"}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    )
}
