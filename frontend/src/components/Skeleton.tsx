/** Full-width shimmer placeholder used while data is loading. */
export default function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`skeleton-shimmer rounded-2xl ${className}`} />;
}