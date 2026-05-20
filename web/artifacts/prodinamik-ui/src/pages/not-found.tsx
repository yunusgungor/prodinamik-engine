import { Link } from "wouter";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-foreground p-4">
      <div className="text-center">
        <div className="text-7xl font-bold font-mono text-muted-foreground mb-4">404</div>
        <h1 className="text-2xl font-semibold mb-2">Page Not Found</h1>
        <p className="text-muted-foreground mb-6 text-sm">
          This page doesn't exist or hasn't been created yet.
        </p>
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-sm text-primary hover:text-primary/80 transition-colors"
        >
          ← Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
