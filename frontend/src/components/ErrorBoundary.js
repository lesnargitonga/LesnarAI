import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('[ErrorBoundary] Uncaught error:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full p-12 text-center space-y-6">
          <div className="p-4 rounded-2xl bg-lesnar-danger/10 border border-lesnar-danger/30">
            <AlertTriangle className="h-10 w-10 text-lesnar-danger" />
          </div>
          <div>
            <h2 className="text-lg font-black text-white uppercase tracking-tighter mb-2">
              System Fault Detected
            </h2>
            <p className="text-xs font-mono text-gray-500 uppercase tracking-widest max-w-md">
              A component encountered an unrecoverable error. The rest of the application remains operational.
            </p>
          </div>
          <button
            onClick={this.handleReset}
            className="btn-primary flex items-center space-x-2 px-6 py-3"
          >
            <RefreshCw className="h-4 w-4" />
            <span>Reinitialize Module</span>
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
