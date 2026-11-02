import type { ReactNode } from "react";
import { num, signedPct } from "../lib/format";

export interface QuoteRowProps {
  code: string;
  name: string;
  price?: number | null;
  changePct?: number | null;
  amount?: number | null;
  badge?: ReactNode;
  active?: boolean;
  loading?: boolean;
  onClick?: () => void;
  className?: string;
}

/** One security quote row (watchlist / index / search results). */
export default function QuoteRow({ code, name, price, changePct, amount, badge, active, loading, onClick, className }: QuoteRowProps) {
  const classes = ["quote-row"];
  if (active) classes.push("active");
  if (className) classes.push(className);
  const tone = changePct == null ? "flat" : changePct > 0 ? "up" : changePct < 0 ? "down" : "flat";
  const content = (
    <>
      <span className="quote-row-main">
        <span className="quote-row-code">{code}</span>
        <span className="quote-row-name" title={name}>{name}</span>
      </span>
      <span className="quote-row-price">{loading ? "…" : num(price)}</span>
      <span className={`quote-row-change ${tone}`}>{loading ? "" : signedPct(changePct == null ? null : changePct / 100)}</span>
      {badge ? <span>{badge}</span> : null}
      {amount != null ? <span className="quote-row-change muted">{num(amount, 0)}</span> : null}
    </>
  );
  if (!onClick) return <div className={classes.join(" ")}>{content}</div>;
  return (
    <button type="button" className={classes.join(" ")} onClick={onClick} aria-pressed={active}>
      {content}
    </button>
  );
}
