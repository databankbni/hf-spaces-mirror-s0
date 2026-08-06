/** Small decorative section divider. Server component; color via prop. */
export function Divider({ color, className }: { color: string; className?: string }) {
  return (
    <div className={`flex items-center justify-center gap-3 ${className ?? ''}`} aria-hidden>
      <span className="h-px w-10 sm:w-16" style={{ backgroundColor: color, opacity: 0.5 }} />
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
        <path
          d="M12 3c1.5 3 4 4.5 7 5-3 .5-5.5 2-7 5-1.5-3-4-4.5-7-5 3-.5 5.5-2 7-5z"
          fill={color}
          opacity={0.8}
        />
      </svg>
      <span className="h-px w-10 sm:w-16" style={{ backgroundColor: color, opacity: 0.5 }} />
    </div>
  );
}
