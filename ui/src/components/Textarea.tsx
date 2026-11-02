import { forwardRef, type TextareaHTMLAttributes } from "react";
import clsx from "clsx";

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}

const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { invalid, className, ...rest },
  ref,
) {
  return <textarea ref={ref} className={clsx("textarea", className)} aria-invalid={invalid || undefined} {...rest} />;
});

Textarea.displayName = "Textarea";
export default Textarea;
