import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

interface Props { children: ReactNode }
interface State { error: Error | null }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // Deliberately no console.error: the UI renders the error and keeps console clean.
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="state-panel error" role="alert">
          <AlertTriangle size={20} />
          <strong>页面渲染失败</strong>
          <span className="muted">{this.state.error.message}</span>
          <button className="btn" onClick={() => { this.setState({ error: null }); window.location.reload(); }}>
            <RotateCcw size={15} /> 重新加载
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
