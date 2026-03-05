import { Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, Camera, Upload, AlertTriangle, LogOut } from 'lucide-react'

const navItems = [
    { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/cameras', label: 'Cameras', icon: Camera },
    { path: '/upload', label: 'Upload', icon: Upload },
    { path: '/violations', label: 'Violations', icon: AlertTriangle },
]

export default function Navbar() {
    const location = useLocation()
    const user = JSON.parse(localStorage.getItem('user') || 'null')

    const handleLogout = () => {
        localStorage.removeItem('access_token')
        localStorage.removeItem('user')
        window.location.href = '/login'
    }

    return (
        <nav className="bg-white border-b border-gray-200 sticky top-0 z-50">
            <div className="max-w-7xl mx-auto px-6">
                <div className="flex items-center justify-between h-14">
                    {/* Logo */}
                    <Link to="/dashboard" className="flex items-center gap-2.5 no-underline">
                        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                            </svg>
                        </div>
                        <span className="text-lg font-bold text-gray-900">Drive Defender</span>
                    </Link>

                    {/* Nav Links */}
                    <div className="flex items-center gap-1">
                        {navItems.map(({ path, label, icon: Icon }) => {
                            const active = location.pathname === path
                            return (
                                <Link
                                    key={path}
                                    to={path}
                                    className={`
                    flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium
                    transition-colors no-underline
                    ${active
                                            ? 'bg-blue-50 text-blue-700'
                                            : 'text-gray-500 hover:text-gray-800 hover:bg-gray-50'
                                        }
                  `}
                                >
                                    <Icon size={16} />
                                    {label}
                                </Link>
                            )
                        })}
                    </div>

                    {/* User / Logout */}
                    <div className="flex items-center gap-3">
                        {user && (
                            <span className="text-sm text-gray-500">{user.name}</span>
                        )}
                        <button
                            onClick={handleLogout}
                            className="text-gray-400 hover:text-red-500 transition-colors"
                            title="Logout"
                        >
                            <LogOut size={18} />
                        </button>
                    </div>
                </div>
            </div>
        </nav>
    )
}
