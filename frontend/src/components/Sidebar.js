import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  Home,
  Map,
  Rocket,
  Navigation,
  BarChart3,
  Settings,
  X,
  Zap
} from 'lucide-react';

const navigation = [
  { name: 'Dashboard', href: '/', icon: Home },
  { name: 'Live Map', href: '/map', icon: Map },
  { name: 'Drone Fleet', href: '/drones', icon: Rocket },
  { name: 'Mission Control', href: '/missions', icon: Navigation },
  { name: 'Analytics', href: '/analytics', icon: BarChart3 },
  { name: 'Settings', href: '/settings', icon: Settings },
];

function Sidebar({ isOpen, onClose }) {
  const location = useLocation();

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <div className={`
        fixed top-0 left-0 h-full w-64 bg-gray-900 transform transition-transform duration-300 ease-in-out z-50
        lg:translate-x-0 lg:static lg:inset-0
        ${isOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div className="flex items-center">
            <div className="h-8 w-8 bg-gradient-to-r from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
              <Zap className="h-5 w-5 text-white" />
            </div>
            <span className="ml-2 text-lg font-semibold text-white">
              Lesnar AI
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md hover:bg-gray-800 lg:hidden"
          >
            <X className="h-5 w-5 text-gray-400" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="mt-5 px-2">
          <div className="space-y-1">
            {navigation.map((item) => {
              const isActive = location.pathname === item.href;
              return (
                <NavLink
                  key={item.name}
                  to={item.href}
                  onClick={() => window.innerWidth < 1024 && onClose()}
                  className={`
                    group flex items-center px-2 py-2 text-sm font-medium rounded-md transition-colors
                    ${isActive
                      ? 'bg-gray-800 text-white'
                      : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                    }
                  `}
                >
                  <item.icon className={`
                    mr-3 flex-shrink-0 h-5 w-5
                    ${isActive ? 'text-white' : 'text-gray-400 group-hover:text-gray-300'}
                  `} />
                  {item.name}
                </NavLink>
              );
            })}
          </div>
        </nav>

        {/* Status section */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-700">
          <div className="bg-gray-800 rounded-lg p-3">
            <div className="flex items-center">
              <div className="h-3 w-3 bg-green-400 rounded-full animate-pulse"></div>
              <span className="ml-2 text-sm text-gray-300">System Active</span>
            </div>
            <div className="mt-2 text-xs text-gray-400">
              © 2026 Lesnar AI Ltd.
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

export default Sidebar;
