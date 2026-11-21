import * as React from "react"
import { cn } from "@/lib/utils"

function Textarea({ className, value, ...props }: React.ComponentProps<"textarea">) {
  const inputRef = React.useRef<HTMLTextAreaElement | null>(null)
  const { ref, ...textareaProps } = props

  React.useImperativeHandle(ref, () => inputRef.current!)

  React.useLayoutEffect(() => {
    const textarea = inputRef.current
    if (!textarea) return
    const fit = () => {
      textarea.style.height = "auto"
      textarea.style.height = `${textarea.scrollHeight}px`
    }
    fit()
    const parent = textarea.parentElement
    if (!parent || typeof ResizeObserver === "undefined") return
    let width = Math.round(parent.getBoundingClientRect().width)
    const observer = new ResizeObserver(() => {
      const next = Math.round(parent.getBoundingClientRect().width)
      if (next === width) return
      width = next
      fit()
    })
    observer.observe(parent)
    return () => observer.disconnect()
  }, [value])

  return (
    <textarea
      data-slot="textarea"
      value={value}
      ref={inputRef}
      className={cn(
        "flex min-h-11 max-h-[40svh] w-full resize-none rounded-xl border-0 bg-transparent px-2.5 py-2.5 text-base font-normal leading-snug text-foreground outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-55 aria-invalid:text-destructive",
        className
      )}
      {...textareaProps}
    />
  )
}

export { Textarea }
