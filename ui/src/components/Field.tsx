import type { ReactNode } from "react";
import clsx from "clsx";

export interface FieldProps {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  htmlFor?: string;
  className?: string;
  children: ReactNode;
}

/** One form row: label + control + hint/error (DESIGN-SPEC §4.1). */
export default function Field({ label, hint, error, required, htmlFor, className, children }: FieldProps) {
  return (
    <div className={clsx("field", className)}>
      {label != null ? (
        <label className="field-label" htmlFor={htmlFor}>
          {label}
          {required ? <span className="required">*</span> : null}
        </label>
      ) : null}
      {children}
      {error != null && error !== "" ? <span className="field-error" role="alert">{error}</span> : hint != null ? <span className="field-hint">{hint}</span> : null}
    </div>
  );
}
