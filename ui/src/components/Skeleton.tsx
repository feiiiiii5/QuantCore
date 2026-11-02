export interface SkeletonProps {
  rows?: number;
  height?: number | string;
  width?: number | string;
  circle?: boolean;
  variant?: "text" | "tile" | "row";
  className?: string;
  ariaLabel?: string;
}

/** Loading placeholder; respects reduced-motion through the global rule. */
export default function Skeleton({ rows = 3, height, width, circle, variant = "text", className, ariaLabel }: SkeletonProps) {
  const style = (index: number) => {
    if (circle) return { width: height ?? 32, height: height ?? 32, borderRadius: "50%" } as const;
    const h = height ?? (variant === "text" ? 12 : variant === "row" ? 32 : 96);
    const w = width ?? (variant === "text" ? `${100 - index * 8}%` : "100%");
    return { height: h, width: w } as const;
  };
  return (
    <div className="skeleton-stack" role="status" aria-label={ariaLabel ?? "加载中"} aria-busy="true">
      {Array.from({ length: Math.max(rows, 1) }, (_, index) => (
        <span key={index} className={className ? `skeleton ${className}` : "skeleton"} style={style(index)} />
      ))}
    </div>
  );
}
