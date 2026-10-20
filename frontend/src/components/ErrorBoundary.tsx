import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  what: string
}

/** Keeps one failing part (e.g. the map) from blanking the whole app. */
export class ErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`${this.props.what} crashed`, error, info.componentStack)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="notice notice--warning" role="alert">
        <p>The {this.props.what} stopped working.</p>
        <button type="button" className="button button--small" onClick={() => window.location.reload()}>
          Reload
        </button>
      </div>
    )
  }
}
