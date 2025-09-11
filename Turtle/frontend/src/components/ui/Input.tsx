import { InputHTMLAttributes, SelectHTMLAttributes, forwardRef } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  helperText?: string
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  helperText?: string
  children: React.ReactNode
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helperText, className = '', ...props }, ref) => {
    return (
      <div className="space-y-1">
        {label && (
          <label className="label">
            {label}
          </label>
        )}
        <input
          ref={ref}
          className={`input ${error ? 'border-red-500 focus:ring-red-500' : ''} ${className}`}
          {...props}
        />
        {error && (
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        )}
        {helperText && !error && (
          <p className="text-sm text-gray-500 dark:text-gray-400">{helperText}</p>
        )}
      </div>
    )
  }
)

Input.displayName = 'Input'

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, helperText, className = '', children, ...props }, ref) => {
    return (
      <div className="space-y-1">
        {label && (
          <label className="label">
            {label}
          </label>
        )}
        <select
          ref={ref}
          className={`select ${error ? 'border-red-500 focus:ring-red-500' : ''} ${className}`}
          {...props}
        >
          {children}
        </select>
        {error && (
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        )}
        {helperText && !error && (
          <p className="text-sm text-gray-500 dark:text-gray-400">{helperText}</p>
        )}
      </div>
    )
  }
)

Select.displayName = 'Select'

export function NumberInput({ label, error, helperText, className = '', ...props }: InputProps) {
  return (
    <Input
      type="number"
      label={label}
      error={error}
      helperText={helperText}
      className={className}
      {...props}
    />
  )
}