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
  Zap,
  Activity
} from 'lucide-react';

const navigation = [
  { name: 'Dashboard', href: '/', icon: Home },
  { name: 'Tactical Map', href: '/map', icon: Map },
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
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <div className={`
        fixed top-0 left-0 h-full w-64 bg-navy-black/80 backdrop-blur-xl border-r border-white/5 transform transition-transform duration-500 ease-in-out z-50
        lg:translate-x-0 lg:static lg:inset-0
        ${isOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        {/* Header */}
        <div className="flex items-center justify-between p-6 mb-4">
          <div className="flex items-center space-x-3">
            <div className="h-8 w-8 bg-lesnar-accent/10 border border-lesnar-accent/20 rounded-lg flex items-center justify-center neo-glow">
              <Zap className="h-5 w-5 text-lesnar-accent" />
            </div>
            <span className="text-lg font-bold text-white tracking-widest uppercase text-glow">
              LESNAR.AI
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md hover:bg-white/5 lg:hidden"
          >
            <X className="h-5 w-5 text-gray-500" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="px-4 space-y-2">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href;
            return (
              <NavLink
                key={item.name}
                to={item.href}
                onClick={() => window.innerWidth < 1024 && onClose()}
                className={`
                  group flex items-center px-4 py-3 text-xs font-bold uppercase tracking-[0.2em] rounded-xl transition-all duration-300
                  ${isActive
                    ? 'bg-lesnar-accent/10 text-lesnar-accent border border-lesnar-accent/20 neo-glow'
                    : 'text-gray-500 hover:text-gray-300 hover:bg-white/5'
                  }
                `}
              >
                <item.icon className={`
                  mr-4 flex-shrink-0 h-4 w-4 transition-colors
                  ${isActive ? 'text-lesnar-accent' : 'text-gray-500 group-hover:text-gray-300'}
                `} />
                {item.name}
              </NavLink>
            );
          })}
        </nav>

        {/* Status section */}
        <div className="absolute bottom-8 left-0 right-0 px-6">
          <div className="p-4 rounded-2xl bg-white/5 border border-white/10 glass">
            <div className="flex items-center mb-3">
              <div className="h-2 w-2 bg-lesnar-success rounded-full animate-pulse mr-2 shadow-[0_0_5px_rgba(0,255,148,0.8)]"></div>
              <span className="text-[10px] font-mono text-lesnar-success uppercase tracking-widest">Core Active</span>
            </div>

            <div className="space-y-2">
              <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
                <div className="h-full w-[85%] bg-lesnar-accent shadow-[0_0_5px_rgba(0,245,255,0.5)]"></div>
              </div>
              <div className="flex justify-between text-[10px] font-mono text-gray-500 uppercase tracking-tighter">
                <span>Load</span>
                <span>85%</span>
              </div>
            </div>

            <div className="mt-4 pt-4 border-t border-white/5 flex items-center text-[10px] font-mono text-gray-600">
              <Activity className="h-3 w-3 mr-2 text-lesnar-accent" />
              <span>UPTIME: 14:22:05</span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

export default Sidebar;
