import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center gap-2 rounded-md border border-transparent bg-clip-padding text-[0.9375rem] font-semibold tracking-[-0.01em] whitespace-nowrap outline-none select-none transition-[transform,background-color,border-color,color,box-shadow,opacity] duration-100 ease-out motion-reduce:transition-none focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:ring-offset-2 focus-visible:ring-offset-background active:scale-[0.98] disabled:pointer-events-none disabled:opacity-45 disabled:active:scale-100 aria-invalid:border-destructive aria-invalid:ring-2 aria-invalid:ring-destructive/20 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-none hover:bg-primary-hover",
        prompt:
          "h-auto min-h-9 justify-start whitespace-normal rounded-md border-border bg-background px-3 py-2 text-left text-xs font-medium leading-relaxed text-muted-foreground hover:border-primary/35 hover:bg-accent hover:text-foreground",
        outline:
          "border-border bg-background text-foreground hover:bg-secondary hover:text-foreground aria-expanded:bg-secondary",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-[color-mix(in_srgb,var(--secondary)_80%,var(--primary))] aria-expanded:bg-secondary",
        ghost:
          "text-foreground hover:bg-secondary hover:text-foreground aria-expanded:bg-secondary",
        destructive:
          "bg-destructive/10 text-destructive hover:bg-destructive/15 focus-visible:ring-destructive/25",
        link:
          "h-auto min-h-6 rounded-none border-0 bg-transparent p-0 font-semibold text-primary underline-offset-4 hover:underline active:scale-100",
      },
      size: {
        default: "min-h-11 px-4",
        xs: "h-7 gap-1 rounded-lg px-2 text-xs font-medium [&_svg:not([class*='size-'])]:size-3",
        sm: "h-9 gap-1.5 rounded-md px-3 text-sm font-semibold [&_svg:not([class*='size-'])]:size-3.5",
        lg: "min-h-12 gap-2 rounded-md px-5 text-base",
        icon: "size-11 rounded-md",
        "icon-xs": "size-7 rounded-md [&_svg:not([class*='size-'])]:size-3.5",
        "icon-sm": "size-9 rounded-md",
        "icon-lg": "size-12 rounded-md",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      data-variant={variant}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
