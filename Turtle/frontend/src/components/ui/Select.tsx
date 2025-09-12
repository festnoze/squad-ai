import { forwardRef, SelectHTMLAttributes } from 'react'
import { clsx } from 'clsx'

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  variant?: 'default' | 'outline'
  size?: 'sm' | 'md' | 'lg'
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, variant = 'default', size = 'md', ...props }, ref) => {
    return (
      <select
        ref={ref}
        className={clsx(
          'rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500',
          {
            'h-8 px-2 text-xs': size === 'sm',
            'h-10 px-3 text-sm': size === 'md',
            'h-12 px-4 text-base': size === 'lg',
            'border-gray-300': variant === 'default',
            'border-gray-300 bg-transparent': variant === 'outline',
          },
          className
        )}
        {...props}
      />
    )
  }
)

Select.displayName = 'Select'