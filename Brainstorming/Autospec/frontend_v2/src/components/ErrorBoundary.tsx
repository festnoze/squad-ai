import { Component, type ReactNode } from "react";

interface State {
  error: Error | null;
}

/** Last line of defence: an unexpected response shape shows a message instead of a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: unknown): State {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <section className="card" role="alert" aria-labelledby="crash-title">
        <h1 id="crash-title">Cette page a rencontré une erreur</h1>
        <p className="mono">{error.message}</p>
        <a href="#/">Retour aux projets</a>
      </section>
    );
  }
}
