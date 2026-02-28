import React from 'react';
import { Link } from 'react-router-dom';
import { Menu, Bell, Map as MapIcon, Shield } from 'lucide-react';

function Header({ onMenuClick, connected }) {
  return (
    <header className="glass-dark border-b border-white/5 z-30">
      <div className="flex items-center justify-between px-6 py-4">
        {/* Left side */}
        <div className="flex items-center space-x-4">
          <button
            onClick={onMenuClick}
            className="p-2 rounded-lg hover:bg-white/5 transition-colors lg:hidden"
          >
            <Menu className="h-5 w-5 text-gray-400" />
          </button>

          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 bg-lesnar-accent/10 border border-lesnar-accent/20 rounded-xl flex items-center justify-center neo-glow">
              <Shield className="h-6 w-6 text-lesnar-accent" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white tracking-widest uppercase text-glow">
                Lesnar AI
              </h1>
              <p className="text-[10px] text-lesnar-accent/60 font-mono tracking-tighter uppercase">
                Tactical Interface // v1.0.0
              </p>
            </div>
          </div>
        </div>

        {/* Right side */}
        <div className="flex items-center space-x-6">
          {/* Connection status */}
          <div className={`flex items-center space-x-2 px-3 py-1.5 rounded-full border ${connected ? 'border-lesnar-success/20 bg-lesnar-success/5' : 'border-lesnar-danger/20 bg-lesnar-danger/5'
            }`}>
            <div className={`h-2 w-2 rounded-full ${connected ? 'bg-lesnar-success animate-pulse' : 'bg-lesnar-danger'}`} />
            <span className={`text-xs font-mono uppercase tracking-wider ${connected ? 'text-lesnar-success' : 'text-lesnar-danger'}`}>
              {connected ? 'Sync Active' : 'Link Severed'}
            </span>
          </div>

          <div className="h-6 w-[1px] bg-white/10 hidden md:block" />

          {/* Quick buttons */}
          <div className="hidden md:flex items-center space-x-2">
            <button className="p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-white transition-all relative">
              <Bell className="h-5 w-5" />
              <span className="absolute top-2 right-2 h-1.5 w-1.5 bg-lesnar-danger rounded-full shadow-[0_0_5px_rgba(255,0,85,0.8)]"></span>
            </button>

            <Link
              to="/map"
              className="flex items-center space-x-2 px-4 py-2 rounded-lg bg-lesnar-accent/10 border border-lesnar-accent/30 text-lesnar-accent hover:bg-lesnar-accent/20 transition-all group"
            >
              <MapIcon className="h-4 w-4 group-hover:scale-110 transition-transform" />
              <span className="text-xs font-bold uppercase tracking-widest">Tactical Map</span>
            </Link>
          </div>

          {/* User profile */}
          <div className="flex items-center pl-4 border-l border-white/10">
            <div className="group relative cursor-pointer">
              <div className="h-10 w-10 p-[2px] rounded-full bg-gradient-to-tr from-lesnar-accent to-purple-500 hover:rotate-180 transition-all duration-500">
                <div className="h-full w-full bg-navy-black rounded-full flex items-center justify-center overflow-hidden">
                  <span className="text-xs font-bold text-white group-hover:rotate-180 transition-all duration-500">LA</span>
                </div>
              </div>
              <div className="absolute top-0 right-0 h-3 w-3 bg-lesnar-success border-2 border-navy-black rounded-full" />
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}

export default Header;
